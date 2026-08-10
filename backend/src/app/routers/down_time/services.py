"""Business logic for the `down-times` router.

`create_down_time` (POST) validates the declared scope (uap / production
line / workstation) against the caller's namespace and the cascading
parent/child relationships between them, then hands off ticket creation to
the async layer: this endpoint never writes the downtime ticket itself, it
only dispatches the `ADD_DOWN_TIME` job (today in-process, tomorrow a real
Pub/Sub publish — see the single dispatch call site below).

The read side (`list_down_times`, `get_down_time`, `get_down_time_summary`)
reads the `down_time/{namespace_id}/issues/{issue_id}` subcollection written
by the `add_down_time` async job (see
`src.app.async_jobs.add_down_time.DOWN_TIME_COLLECTION` /
`ISSUES_SUBCOLLECTION`) and applies the role-based visibility + per-issue
permission-flag rules documented on each function below.

Lifecycle: most tickets go `pending -> ongoing -> resolved -> closed` via
`acknowledge_down_time` / `resolve_down_time` / `close_down_time`. Tickets
whose `down_time_type` is "close-only" (see
`src.app.globals.enum.CLOSE_ONLY_DOWNTIME_TYPES` — currently a WIP
shortage or an unclassified/"others" stop) skip acknowledge and resolve
entirely: nobody "repairs" those in the OptiFlow sense, so forcing them
through ack/resolve would pollute MTTR-style KPIs with meaningless
timestamps. `acknowledge_down_time` / `resolve_down_time` reject a
close-only ticket with 403 regardless of role/status. `close_down_time`
allows a close-only ticket to close from *any* non-`closed` status (still
restricted to production agents), not just `pending` — because Firestore has
no migrations, a ticket created before its type became close-only may
already be sitting in `ongoing`/`resolved`, and with ack/resolve forbidden it
would otherwise have no legal transition left and would strand there
forever, corrupting the `ongoing`/`resolved` KPI buckets. See
`_is_close_only` / `_permission_flags` for the exact predicate and the
resulting `can_acknowledge`/`can_resolve`/`can_close`/`can_delete` flags.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status

from src.app.gcp import get_pubsub_publisher
from src.app.core.firestore import (
    NAMESPACE_COLLECTION,
    PRODUCTION_LINE_COLLECTION,
    UAP_COLLECTION,
    USERS_COLLECTION,
    WORKSTATION_COLLECTION,
)
from src.app.gcp import get_firestore_client
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import (
    CLOSE_ONLY_DOWNTIME_TYPES,
    DownTimeStatus,
    DownTimeType,
    JobType,
    Role,
)

logger = logging.getLogger(__name__)

from src.app.routers.down_time.modelsIn import CreateDownTimeIn
from src.app.routers.down_time.modelsOut import (
    DownTimeAckOut,
    DownTimeOut,
    DownTimePageOut,
    DownTimeStatusSummaryOut,
    DownTimeSummaryOut,
)

# Same literals `add_down_time` stores the issue under — kept in sync with
# `src.app.async_jobs.add_down_time.DOWN_TIME_COLLECTION` / `ISSUES_SUBCOLLECTION`.
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"

# Pagination bounds for list_down_times.
_DEFAULT_PAGE_LIMIT = 20
_MAX_PAGE_LIMIT = 100

# Roles that see every issue in their namespace, regardless of process.
_FULL_VISIBILITY_ROLES = {
    Role.OWNER.value,
    Role.ADMIN.value,
    Role.MANAGER.value,
    Role.PRODUCTION_SUPERVISOR.value,
    Role.PRODUCTION_AGENT.value,
}

_ACTOR_FIELDS = ("created_by", "acknowledged_by", "resolved_by", "closed_by")


def _require_non_blank(value: Optional[str], field_name: str) -> None:
    """Never let a blank id reach the Firestore SDK (`.document("")` would
    otherwise blow up unhandled)."""
    if value is not None and not value.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name}: must not be blank.",
        )


def _validate_uap(client: FirestoreClient, namespace_id: str, uap_id: str) -> dict[str, Any]:
    uap = client.get_document(UAP_COLLECTION, uap_id)
    if not uap or uap.get("namespace_id") != namespace_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="uap_id: no such production area in this namespace.",
        )
    return uap


def _validate_production_line(
    client: FirestoreClient,
    namespace_id: str,
    production_line_id: str,
    uap_id: Optional[str],
) -> dict[str, Any]:
    line = client.get_document(PRODUCTION_LINE_COLLECTION, production_line_id)
    if not line or line.get("namespace_id") != namespace_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="production_line_id: no such production line in this namespace.",
        )

    line_uap_id = line.get("uap_id")
    if uap_id is not None:
        if line_uap_id != uap_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="production_line_id: does not belong to the given uap_id.",
            )
    else:
        if line_uap_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "production_line_id: belongs to a UAP, but no uap_id "
                    "was given."
                ),
            )
    return line


def _validate_workstation(
    client: FirestoreClient,
    namespace_id: str,
    workstation_id: str,
    production_line_id: Optional[str],
) -> dict[str, Any]:
    station = client.get_document(WORKSTATION_COLLECTION, workstation_id)
    if not station or station.get("namespace_id") != namespace_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="workstation_id: no such workstation in this namespace.",
        )

    station_line_id = station.get("production_line_id")
    if production_line_id is not None:
        if station_line_id != production_line_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "workstation_id: does not belong to the given "
                    "production_line_id."
                ),
            )
    else:
        if station_line_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "workstation_id: belongs to a production line, but no "
                    "production_line_id was given."
                ),
            )
    return station


def create_down_time(
    payload: CreateDownTimeIn, namespace_id: str, created_by: str
) -> DownTimeAckOut:
    _require_non_blank(payload.uap_id, "uap_id")
    _require_non_blank(payload.production_line_id, "production_line_id")
    _require_non_blank(payload.workstation_id, "workstation_id")

    client = get_firestore_client()

    if payload.uap_id is not None:
        _validate_uap(client, namespace_id, payload.uap_id)

    if payload.production_line_id is not None:
        _validate_production_line(
            client, namespace_id, payload.production_line_id, payload.uap_id
        )

    if payload.workstation_id is not None:
        _validate_workstation(
            client, namespace_id, payload.workstation_id, payload.production_line_id
        )

    job_id = str(uuid.uuid4())
    job_payload = {
        "created_by": created_by,
        "production_scope": payload.production_scope.value,
        "uap_id": payload.uap_id,
        "production_line_id": payload.production_line_id,
        "workstation_id": payload.workstation_id,
        "down_time_type": payload.down_time_type.value,
        "department": payload.department.value if payload.department else None,
    }

    # Publish the job — the endpoint never runs the handler in-process. The
    # worker route (`POST /cloud_job`) receives the push and dispatches it.
    get_pubsub_publisher().publish_job(
        JobType.ADD_DOWN_TIME, namespace_id, job_payload, job_id=job_id
    )

    return DownTimeAckOut(job_id=job_id)


# --------------------------------------------------------------------------
# Read side: GET /down-times, GET /down-times/{issue_id}, GET /down-times/summary
# --------------------------------------------------------------------------


def _process_for_role(role: str) -> str:
    """Derive the process a non-full-visibility role owns by stripping the
    trailing " agent"/" supervisor" (e.g. "maintenance agent" -> "maintenance").
    """
    for suffix in (" agent", " supervisor"):
        if role.endswith(suffix):
            return role[: -len(suffix)]
    return role


def _is_visible(issue: dict[str, Any], role: Optional[str]) -> bool:
    """Whether `issue` is visible to a caller with this role, per the
    visibility rule: full-visibility roles see everything in their
    namespace; every other role only sees issues in their own process."""
    if role in _FULL_VISIBILITY_ROLES:
        return True
    return issue.get("process") == _process_for_role(role or "")


def _fetch_visible_issues(
    client: FirestoreClient, namespace_id: str, role: Optional[str]
) -> list[dict[str, Any]]:
    """Fetch every issue in the namespace, filtered to those visible to
    `role` (see `_is_visible`)."""
    issues = client.find_subdocuments(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION
    )
    if role in _FULL_VISIBILITY_ROLES:
        return issues
    process = _process_for_role(role or "")
    return [issue for issue in issues if issue.get("process") == process]


def _is_close_only(issue: dict[str, Any]) -> bool:
    """Whether `issue` belongs to a "close-only" `down_time_type` (see
    `CLOSE_ONLY_DOWNTIME_TYPES`) — its lifecycle skips acknowledge/resolve and
    goes straight `pending -> closed`. Tolerant of a missing/unknown stored
    value: never raises on a malformed document, just returns False."""
    try:
        return DownTimeType(issue.get("down_time_type")) in CLOSE_ONLY_DOWNTIME_TYPES
    except ValueError:
        return False


def _permission_flags(
    issue: dict[str, Any], current: dict[str, Any]
) -> tuple[bool, bool, bool, bool]:
    """Compute `(can_acknowledge, can_resolve, can_close, can_delete)` for
    `current` on `issue`, per the per-issue permission rules.

    Close-only issues (see `_is_close_only`) skip acknowledge/resolve
    entirely: `can_acknowledge`/`can_resolve` are always False. `can_close`
    only requires the caller to be a production agent and the ticket to not
    already be `closed` — deliberately status-tolerant (not `pending`-only)
    because Firestore has no migrations: a ticket created before its type
    became close-only may already be sitting in `ongoing`/`resolved`, and it
    must still be closable from there or it strands forever and corrupts the
    `ongoing`/`resolved` KPI buckets. A deliberate consequence: for the
    ticket's own creator while it's still `pending`, `can_close` and
    `can_delete` can both be True at once — closing records a real stop for
    the KPIs, deleting retracts a mis-declaration; either is a valid action.
    """
    role = current.get("role")
    process = issue.get("process")
    issue_status = issue.get("status")

    can_delete = (
        role == Role.PRODUCTION_AGENT.value
        and issue_status == DownTimeStatus.PENDING.value
        and issue.get("created_by") == current.get("id")
    )

    if _is_close_only(issue):
        can_acknowledge = False
        can_resolve = False
        can_close = (
            role == Role.PRODUCTION_AGENT.value
            and issue_status != DownTimeStatus.CLOSED.value
        )
        return can_acknowledge, can_resolve, can_close, can_delete

    can_acknowledge = (
        role == f"{process} agent" and issue_status == DownTimeStatus.PENDING.value
    )
    can_resolve = (
        role == f"{process} agent" and issue_status == DownTimeStatus.ONGOING.value
    )
    can_close = (
        role == Role.PRODUCTION_AGENT.value
        and issue_status == DownTimeStatus.RESOLVED.value
    )
    return can_acknowledge, can_resolve, can_close, can_delete


def _full_name(user: Optional[dict[str, Any]]) -> Optional[str]:
    if not user:
        return None
    name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
    return name or None


_STATUS_ENTRY_FIELD = {
    DownTimeStatus.PENDING.value: "created_at",
    DownTimeStatus.ONGOING.value: "acknowledged_at",
    DownTimeStatus.RESOLVED.value: "resolved_at",
    DownTimeStatus.CLOSED.value: "closed_at",
}


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _time_in_status_seconds(
    issue: dict[str, Any], now: datetime
) -> Optional[float]:
    """Seconds elapsed since `issue` entered its current status (see
    `_STATUS_ENTRY_FIELD`), measured against `now` (the current time in the
    namespace's timezone); `None` when the entry timestamp is missing/
    unparsable."""
    entry_field = _STATUS_ENTRY_FIELD.get(issue.get("status"))
    if entry_field is None:
        return None
    entry_dt = _parse_iso(issue.get(entry_field))
    if entry_dt is None:
        return None
    return (now - entry_dt).total_seconds()


def _batch_fetch_actor_names(
    client: FirestoreClient, issues: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """One `get_documents` round-trip across every actor id referenced by
    `issues` (created_by/acknowledged_by/resolved_by/closed_by)."""
    ids = {
        issue[field]
        for issue in issues
        for field in _ACTOR_FIELDS
        if issue.get(field)
    }
    if not ids:
        return {}
    return client.get_documents(USERS_COLLECTION, list(ids))


def _to_down_time_out(
    issue: dict[str, Any],
    current: dict[str, Any],
    users_by_id: dict[str, dict[str, Any]],
    now: datetime,
) -> DownTimeOut:
    can_acknowledge, can_resolve, can_close, can_delete = _permission_flags(
        issue, current
    )
    return DownTimeOut(
        id=issue["id"],
        namespace_id=issue.get("namespace_id"),
        created_at=issue.get("created_at"),
        updated_at=issue.get("updated_at"),
        down_time_scope=issue.get("down_time_scope"),
        uap_id=issue.get("uap_id"),
        production_line_id=issue.get("production_line_id"),
        workstation_id=issue.get("workstation_id"),
        down_time_type=issue.get("down_time_type"),
        process=issue.get("process"),
        status=issue.get("status"),
        created_by=issue.get("created_by"),
        created_by_name=_full_name(users_by_id.get(issue.get("created_by"))),
        acknowledged_at=issue.get("acknowledged_at"),
        acknowledged_by=issue.get("acknowledged_by"),
        acknowledged_by_name=_full_name(users_by_id.get(issue.get("acknowledged_by"))),
        resolved_at=issue.get("resolved_at"),
        resolved_by=issue.get("resolved_by"),
        resolved_by_name=_full_name(users_by_id.get(issue.get("resolved_by"))),
        closed_at=issue.get("closed_at"),
        closed_by=issue.get("closed_by"),
        closed_by_name=_full_name(users_by_id.get(issue.get("closed_by"))),
        can_acknowledge=can_acknowledge,
        can_resolve=can_resolve,
        can_close=can_close,
        can_delete=can_delete,
        time_in_status_seconds=_time_in_status_seconds(issue, now),
    )


def list_down_times(
    current: dict[str, Any],
    status_filter: Optional[str] = None,
    limit: int = _DEFAULT_PAGE_LIMIT,
    offset: int = 0,
) -> DownTimePageOut:
    """List the downtime issues visible to `current` in their namespace,
    newest first, optionally filtered to a single `status`, paginated with
    `limit`/`offset`. `total` is the full count of visible (filtered) issues."""
    limit = max(1, min(limit, _MAX_PAGE_LIMIT))
    offset = max(0, offset)

    client = get_firestore_client()
    namespace_id = current["namespace_id"]
    issues = _fetch_visible_issues(client, namespace_id, current.get("role"))

    if status_filter is not None:
        issues = [issue for issue in issues if issue.get("status") == status_filter]

    issues.sort(key=lambda issue: issue.get("created_at") or "", reverse=True)

    total = len(issues)
    page = issues[offset : offset + limit]

    now = _now_for_namespace(client, namespace_id)
    users_by_id = _batch_fetch_actor_names(client, page)
    items = [_to_down_time_out(issue, current, users_by_id, now) for issue in page]
    return DownTimePageOut(items=items, total=total, limit=limit, offset=offset)


def get_down_time(issue_id: str, current: dict[str, Any]) -> DownTimeOut:
    """Fetch a single downtime issue by id, scoped to the caller's namespace
    and visibility. Returns 404 (not 403) when the issue doesn't exist in the
    namespace or isn't visible to the caller, so existence isn't leaked
    across the visibility boundary."""
    client = get_firestore_client()
    namespace_id = current["namespace_id"]

    issue = client.get_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, issue_id
    )
    if not issue or not _is_visible(issue, current.get("role")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Downtime ticket not found.",
        )

    now = _now_for_namespace(client, namespace_id)
    users_by_id = _batch_fetch_actor_names(client, [issue])
    return _to_down_time_out(issue, current, users_by_id, now)


def _pending_duration(issue: dict[str, Any], now: datetime) -> Optional[float]:
    created_at = _parse_iso(issue.get("created_at"))
    if created_at is None:
        return None
    return (now - created_at).total_seconds()


def _ongoing_duration(issue: dict[str, Any], now: datetime) -> Optional[float]:
    acknowledged_at = _parse_iso(issue.get("acknowledged_at"))
    if acknowledged_at is None:
        return None
    return (now - acknowledged_at).total_seconds()


def _resolved_duration(issue: dict[str, Any], now: datetime) -> Optional[float]:
    acknowledged_at = _parse_iso(issue.get("acknowledged_at"))
    resolved_at = _parse_iso(issue.get("resolved_at"))
    if acknowledged_at is None or resolved_at is None:
        return None
    return (resolved_at - acknowledged_at).total_seconds()


def _closed_duration(issue: dict[str, Any], now: datetime) -> Optional[float]:
    resolved_at = _parse_iso(issue.get("resolved_at"))
    closed_at = _parse_iso(issue.get("closed_at"))
    if resolved_at is None or closed_at is None:
        return None
    return (closed_at - resolved_at).total_seconds()


def _status_summary(
    issues: list[dict[str, Any]],
    status_value: str,
    duration_fn,
    now: datetime,
) -> DownTimeStatusSummaryOut:
    matching = [issue for issue in issues if issue.get("status") == status_value]
    durations = [
        d for d in (duration_fn(issue, now) for issue in matching) if d is not None
    ]
    average_seconds = sum(durations) / len(durations) if durations else None
    return DownTimeStatusSummaryOut(count=len(matching), average_seconds=average_seconds)


def _resolve_timezone(namespace_id: str, namespace: Optional[dict[str, Any]]) -> ZoneInfo:
    """Resolve the namespace's IANA timezone, defaulting to UTC when missing,
    blank, or unknown. Mirrors `add_down_time._resolve_timezone` (kept local
    to this router — no import across the async boundary)."""
    tz_name = (namespace or {}).get("timezone") or "UTC"
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning(
            f"down_time.services: unknown timezone '{tz_name}' for namespace "
            f"'{namespace_id}', defaulting to UTC."
        )
        return ZoneInfo("UTC")


def _now_for_namespace(client: FirestoreClient, namespace_id: str) -> datetime:
    """Current time in the namespace's timezone — used for every elapsed-time
    computation (time_in_status_seconds, summary averages) so durations are
    measured against the tenant's local now."""
    namespace = client.get_document(NAMESPACE_COLLECTION, namespace_id)
    tz = _resolve_timezone(namespace_id, namespace)
    return datetime.now(tz)


def _now_iso_for_namespace(client: FirestoreClient, namespace_id: str) -> str:
    return _now_for_namespace(client, namespace_id).isoformat()


def _get_issue_or_404(
    client: FirestoreClient, namespace_id: str, issue_id: str
) -> dict[str, Any]:
    issue = client.get_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, issue_id
    )
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Downtime ticket not found.",
        )
    return issue


def acknowledge_down_time(issue_id: str, current: dict[str, Any]) -> DownTimeOut:
    """Acknowledge a pending downtime ticket (`pending` -> `ongoing`).
    Restricted to the process's own agent (e.g. "maintenance agent" for a
    maintenance ticket); 409 unless the ticket is currently `pending`. 403
    when the ticket's `down_time_type` is close-only (see
    `CLOSE_ONLY_DOWNTIME_TYPES`) — those tickets skip acknowledge entirely."""
    client = get_firestore_client()
    namespace_id = current["namespace_id"]
    issue = _get_issue_or_404(client, namespace_id, issue_id)

    if _is_close_only(issue):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This downtime type is closed directly and cannot be acknowledged.",
        )
    if current.get("role") != f"{issue.get('process')} agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owning process's agent may acknowledge this ticket.",
        )
    if issue.get("status") != DownTimeStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ticket is not pending.",
        )

    now = _now_for_namespace(client, namespace_id)
    now_iso = now.isoformat()
    updates = {
        "status": DownTimeStatus.ONGOING.value,
        "acknowledged_at": now_iso,
        "acknowledged_by": current["id"],
        "updated_at": now_iso,
    }
    client.update_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, issue_id, updates
    )
    issue.update(updates)

    users_by_id = _batch_fetch_actor_names(client, [issue])
    return _to_down_time_out(issue, current, users_by_id, now)


def resolve_down_time(issue_id: str, current: dict[str, Any]) -> DownTimeOut:
    """Resolve an ongoing downtime ticket (`ongoing` -> `resolved`).
    Restricted to the process's own agent; 409 unless the ticket is currently
    `ongoing`. 403 when the ticket's `down_time_type` is close-only (see
    `CLOSE_ONLY_DOWNTIME_TYPES`) — those tickets skip resolve entirely."""
    client = get_firestore_client()
    namespace_id = current["namespace_id"]
    issue = _get_issue_or_404(client, namespace_id, issue_id)

    if _is_close_only(issue):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This downtime type is closed directly and cannot be resolved.",
        )
    if current.get("role") != f"{issue.get('process')} agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owning process's agent may resolve this ticket.",
        )
    if issue.get("status") != DownTimeStatus.ONGOING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ticket is not ongoing.",
        )

    now = _now_for_namespace(client, namespace_id)
    now_iso = now.isoformat()
    updates = {
        "status": DownTimeStatus.RESOLVED.value,
        "resolved_at": now_iso,
        "resolved_by": current["id"],
        "updated_at": now_iso,
    }
    client.update_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, issue_id, updates
    )
    issue.update(updates)

    users_by_id = _batch_fetch_actor_names(client, [issue])
    return _to_down_time_out(issue, current, users_by_id, now)


def close_down_time(issue_id: str, current: dict[str, Any]) -> DownTimeOut:
    """Close a downtime ticket. Restricted to production agents. For a
    close-only `down_time_type` (see `CLOSE_ONLY_DOWNTIME_TYPES`) the ticket
    may be closed from any status except `closed` itself (409 only when
    already closed); for every other type the normal `resolved -> closed`
    transition applies (409 unless currently `resolved`).

    The close-only branch is deliberately status-tolerant rather than
    `pending`-only: Firestore has no migrations, so a ticket created before
    its type became close-only may already be `ongoing`/`resolved`. Requiring
    `pending` there would deadlock it — acknowledge/resolve are already
    forbidden for close-only types, so it could never legally transition
    again, and it would permanently inflate the `ongoing`/`resolved` KPI
    buckets. Allowing close from any non-closed status keeps every legacy
    ticket reachable."""
    client = get_firestore_client()
    namespace_id = current["namespace_id"]
    issue = _get_issue_or_404(client, namespace_id, issue_id)

    if current.get("role") != Role.PRODUCTION_AGENT.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a production agent may close this ticket.",
        )
    if _is_close_only(issue):
        if issue.get("status") == DownTimeStatus.CLOSED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ticket is already closed.",
            )
    else:
        if issue.get("status") != DownTimeStatus.RESOLVED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ticket is not resolved.",
            )

    now = _now_for_namespace(client, namespace_id)
    now_iso = now.isoformat()
    updates = {
        "status": DownTimeStatus.CLOSED.value,
        "closed_at": now_iso,
        "closed_by": current["id"],
        "updated_at": now_iso,
    }
    client.update_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, issue_id, updates
    )
    issue.update(updates)

    users_by_id = _batch_fetch_actor_names(client, [issue])
    return _to_down_time_out(issue, current, users_by_id, now)


def delete_down_time(issue_id: str, current: dict[str, Any]) -> DownTimeOut:
    """Delete a still-pending downtime ticket. Restricted to the production
    agent who opened it (`created_by`); 409 unless the ticket is currently
    `pending`."""
    client = get_firestore_client()
    namespace_id = current["namespace_id"]
    issue = _get_issue_or_404(client, namespace_id, issue_id)

    if (
        current.get("role") != Role.PRODUCTION_AGENT.value
        or issue.get("created_by") != current.get("id")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the production agent who opened this ticket may delete it.",
        )
    if issue.get("status") != DownTimeStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ticket is not pending.",
        )

    now = _now_for_namespace(client, namespace_id)
    users_by_id = _batch_fetch_actor_names(client, [issue])
    result = _to_down_time_out(issue, current, users_by_id, now)

    client.delete_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, issue_id
    )
    return result


def get_down_time_summary(current: dict[str, Any]) -> DownTimeSummaryOut:
    """Aggregate counts + average elapsed time per status, over the caller's
    visible issues (see module docstring for the per-status average
    definitions)."""
    client = get_firestore_client()
    namespace_id = current["namespace_id"]
    issues = _fetch_visible_issues(client, namespace_id, current.get("role"))
    now = _now_for_namespace(client, namespace_id)

    return DownTimeSummaryOut(
        pending=_status_summary(
            issues, DownTimeStatus.PENDING.value, _pending_duration, now
        ),
        ongoing=_status_summary(
            issues, DownTimeStatus.ONGOING.value, _ongoing_duration, now
        ),
        resolved=_status_summary(
            issues, DownTimeStatus.RESOLVED.value, _resolved_duration, now
        ),
        closed=_status_summary(
            issues, DownTimeStatus.CLOSED.value, _closed_duration, now
        ),
    )
