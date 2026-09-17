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
`acknowledge_down_time` / `resolve_down_time` / `close_down_time`. A resolved
ticket can also bounce `resolved -> ongoing` via `reject_resolution` when a
production agent finds the fix didn't actually restore production; the
ticket then goes through `resolve_down_time` again before it can close.
Every transition (`acknowledge_down_time` / `resolve_down_time` /
`reject_resolution`) publishes a best-effort `JobType.NOTIFY_DOWN_TIME_UPDATE`
job after its Firestore write succeeds — see `_publish_down_time_update`.
Tickets whose `down_time_type` is "close-only" (see
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
resulting `can_acknowledge`/`can_resolve`/`can_close`/`can_reject`/
`can_delete` flags.

`close_down_time` / `delete_down_time` are also where the escalation chain
ends: each reads the issue's `escalation_task_id` (absent on legacy
documents that predate the field — read defensively) and calls
`core.escalation.cancel_escalation`, clearing the field on the same update
so a stale id never lingers pointing at a cancelled/nonexistent task.
Cancellation is best-effort — `cancel_escalation` already swallows its own
errors, and the close/delete transition itself must never fail because of
it; the `escalate_down_time` async handler's own `closed`/missing-issue
branches are the belt-and-braces fallback if a cancel call doesn't land.
"""

import logging
import uuid
from datetime import date as date_cls, datetime, time, timedelta
from typing import Any, Optional
from fastapi import HTTPException, status

from src.app.gcp import get_pubsub_publisher
from src.app.core.archiving import is_active
from src.app.core.down_time_conflict import DownTimeConflict, find_blocking_conflict
from src.app.core.escalation import cancel_escalation
from src.app.core.firestore import (
    NAMESPACE_COLLECTION,
    PRODUCTION_LINE_COLLECTION,
    UAP_COLLECTION,
    USERS_COLLECTION,
    WORKSTATION_COLLECTION,
)
from src.app.core.shift_time import parse_hhmm, window_length_minutes
from src.app.core.timezone import namespace_timezone
from src.app.gcp import get_firestore_client
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import (
    CLOSE_ONLY_DOWNTIME_TYPES,
    DownTimeStatus,
    DownTimeType,
    JobType,
    ProductionScope,
    Role,
)

logger = logging.getLogger(__name__)

from src.app.routers.down_time.modelsIn import CreateDownTimeIn
from src.app.routers.down_time.modelsOut import (
    DownTimeAckOut,
    DownTimeGanttOut,
    DownTimeOut,
    DownTimePageOut,
    DownTimeStatusSummaryOut,
    DownTimeSummaryOut,
    GanttIntervalOut,
    GanttLineRowOut,
    GanttShiftOut,
    GanttUapRowOut,
    GanttWindowOut,
    GanttWorkStationRowOut,
)

# `kpi.services` owns the shift-window / planned-time / location-hierarchy
# primitives the gantt reuses (namespace-timezone convention, configured
# -shifts parsing, dominant-location-level pick) — imported as a module, not
# individual private names, to make every reuse site below explicit about
# where it's borrowing from. No cycle: `kpi.services` never imports
# `down_time.services`.
from src.app.routers.kpi import services as kpi_services

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

_ACTOR_FIELDS = (
    "created_by", "acknowledged_by", "resolved_by", "closed_by", "rejected_by"
)


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
    if not uap or uap.get("namespace_id") != namespace_id or not is_active(uap):
        # An archived UAP is rejected the same way as a nonexistent one —
        # see `_validate_workstation` below for why.
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
    if not line or line.get("namespace_id") != namespace_id or not is_active(line):
        # An archived production line is rejected the same way as a
        # nonexistent one — see `_validate_workstation` below for why.
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
    if (
        not station
        or station.get("namespace_id") != namespace_id
        or not is_active(station)
    ):
        # An archived workstation is rejected the same way as a nonexistent
        # one: no new downtime ticket can target it, but its already-logged
        # tickets still count in the KPIs.
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


# How each blocking level is named in the 409 messages: (English, French).
_CONFLICT_LEVEL_LABELS: dict[str, tuple[str, str]] = {
    ProductionScope.PLANT.value: ("the plant", "l'usine"),
    ProductionScope.UAP.value: ("this UAP", "cette UAP"),
    ProductionScope.PRODUCTION_LINE.value: (
        "this production line",
        "cette ligne de production",
    ),
    ProductionScope.WORK_STATION.value: ("this workstation", "ce poste de travail"),
}


def _conflict_detail(conflict: DownTimeConflict) -> dict[str, Any]:
    """The structured 409 body for a blocked declaration (§4): `code` is a
    stable token clients switch on, `blocking_scope` the level the blocking
    ticket was declared at, and `message_fr` / `message_en` the same
    user-facing sentence in each supported language. The mobile app shows
    the one matching the device language as-is, so both must read as a
    finished sentence addressed to the person declaring.

    `blocking_ticket_id` is ALWAYS the blocking ticket's id (spec §4). The
    `_is_visible` gating this used to carry is provably unreachable:
    declaring a downtime is restricted to `production agent`
    (`_down_time_report_scope`), and `production agent` is in
    `_FULL_VISIBILITY_ROLES`, so the only caller that can ever receive this
    409 already sees every ticket of its namespace. Coupling to watch: if
    the declaring role set ever widens beyond the full-visibility roles,
    this visibility question comes back and the gating must be
    reintroduced."""
    label_en, label_fr = _CONFLICT_LEVEL_LABELS.get(
        conflict.down_time_scope, ("this resource", "cette ressource")
    )

    return {
        "code": "downtime_already_open",
        "blocking_scope": conflict.down_time_scope,
        "blocking_ticket_id": conflict.issue_id,
        "message_fr": (
            f"Un arrêt est déjà ouvert sur {label_fr} (ticket "
            f"{conflict.issue_id}). Mettez à jour le ticket existant au lieu "
            "d'en déclarer un nouveau."
        ),
        "message_en": (
            f"A downtime is already open on {label_en} (ticket "
            f"{conflict.issue_id}). Update the existing ticket instead of "
            "declaring a new one."
        ),
    }


def create_down_time(
    payload: CreateDownTimeIn, current: dict[str, Any]
) -> DownTimeAckOut:
    _require_non_blank(payload.uap_id, "uap_id")
    _require_non_blank(payload.production_line_id, "production_line_id")
    _require_non_blank(payload.workstation_id, "workstation_id")

    namespace_id = current["namespace_id"]
    created_by = current["id"]
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

    # §4 — one open downtime per resource. The above validations already
    # loaded/checked the full id chain, so it's passed through here to spare
    # `find_blocking_conflict` its own ancestor-resolution reads (see its
    # docstring).
    conflict = find_blocking_conflict(
        client,
        namespace_id,
        payload.production_scope.value,
        uap_id=payload.uap_id,
        production_line_id=payload.production_line_id,
        workstation_id=payload.workstation_id,
    )
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_conflict_detail(conflict),
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


def _resolve_issue_resource_ref(
    issue: dict[str, Any]
) -> Optional[tuple[str, str]]:
    """The `(collection, resource_id)` pair an issue's downtime resource
    resolves to, following the same "most specific id wins" convention the
    rest of the codebase uses (`workstation_id` over `production_line_id`
    over `uap_id`). `None` for a `plant`-scope issue, which carries no
    resource id at all and therefore can never be hidden by archiving."""
    if issue.get("workstation_id"):
        return WORKSTATION_COLLECTION, issue["workstation_id"]
    if issue.get("production_line_id"):
        return PRODUCTION_LINE_COLLECTION, issue["production_line_id"]
    if issue.get("uap_id"):
        return UAP_COLLECTION, issue["uap_id"]
    return None


def _filter_archived_resource_issues(
    client: FirestoreClient, issues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Drop every issue whose resource (the most specific of
    `workstation_id` / `production_line_id` / `uap_id` — see
    `_resolve_issue_resource_ref`) has been archived (`is_active`, see
    `src.app.core.archiving`). A ticket on an archived resource must stop
    showing up as work to do; its downtime still counts in the KPIs, which
    read Firestore directly rather than through this function.

    Bounded I/O: at most one `get_documents` round-trip per resource
    collection referenced (workstation / production line / uap — so at most
    three calls total, regardless of how many issues or how many distinct
    resources they reference), never one read per issue.

    A resource id that doesn't resolve to a document (deleted rather than
    archived — not something the product does today, but Firestore enforces
    nothing here) is treated as hidden, the same conservative posture as
    absent: "no such active resource" either way.
    """
    refs_by_issue_id: dict[str, tuple[str, str]] = {}
    ids_by_collection: dict[str, set[str]] = {}
    for issue in issues:
        ref = _resolve_issue_resource_ref(issue)
        if ref is None:
            continue
        refs_by_issue_id[issue["id"]] = ref
        collection, resource_id = ref
        ids_by_collection.setdefault(collection, set()).add(resource_id)

    resources_by_collection: dict[str, dict[str, dict[str, Any]]] = {
        collection: client.get_documents(collection, list(ids))
        for collection, ids in ids_by_collection.items()
    }

    def _issue_is_visible(issue: dict[str, Any]) -> bool:
        ref = refs_by_issue_id.get(issue["id"])
        if ref is None:
            return True
        collection, resource_id = ref
        resource = resources_by_collection.get(collection, {}).get(resource_id)
        return resource is not None and is_active(resource)

    return [issue for issue in issues if _issue_is_visible(issue)]


def _fetch_visible_issues(
    client: FirestoreClient, namespace_id: str, role: Optional[str]
) -> list[dict[str, Any]]:
    """Fetch every issue in the namespace, filtered to those visible to
    `role` (see `_is_visible`) and with every issue whose resource has been
    archived excluded (see `_filter_archived_resource_issues`) — one
    behaviour for every caller, deliberately not role-dependent."""
    issues = client.find_subdocuments(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION
    )
    if role not in _FULL_VISIBILITY_ROLES:
        process = _process_for_role(role or "")
        issues = [issue for issue in issues if issue.get("process") == process]
    return _filter_archived_resource_issues(client, issues)


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
) -> tuple[bool, bool, bool, bool, bool]:
    """Compute `(can_acknowledge, can_resolve, can_close, can_reject,
    can_delete)` for `current` on `issue`, per the per-issue permission
    rules.

    Close-only issues (see `_is_close_only`) skip acknowledge/resolve/reject
    entirely: `can_acknowledge`/`can_resolve`/`can_reject` are always False.
    `can_close` only requires the caller to be a production agent and the
    ticket to not already be `closed` — deliberately status-tolerant (not
    `pending`-only) because Firestore has no migrations: a ticket created
    before its type became close-only may already be sitting in
    `ongoing`/`resolved`, and it must still be closable from there or it
    strands forever and corrupts the `ongoing`/`resolved` KPI buckets. A
    deliberate consequence: for the ticket's own creator while it's still
    `pending`, `can_close` and `can_delete` can both be True at once —
    closing records a real stop for the KPIs, deleting retracts a
    mis-declaration; either is a valid action. `can_reject` mirrors
    `can_close`'s role restriction (production agent only) but requires the
    ticket to currently be `resolved` — the resolution is what's being sent
    back.
    """
    role = current.get("role")
    process = issue.get("process")
    issue_status = issue.get("status")
    close_only = _is_close_only(issue)

    can_delete = (
        role == Role.PRODUCTION_AGENT.value
        and issue_status == DownTimeStatus.PENDING.value
        and issue.get("created_by") == current.get("id")
    )

    if close_only:
        can_acknowledge = False
        can_resolve = False
        can_close = (
            role == Role.PRODUCTION_AGENT.value
            and issue_status != DownTimeStatus.CLOSED.value
        )
        can_reject = False
        return can_acknowledge, can_resolve, can_close, can_reject, can_delete

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
    can_reject = (
        role == Role.PRODUCTION_AGENT.value
        and issue_status == DownTimeStatus.RESOLVED.value
    )
    return can_acknowledge, can_resolve, can_close, can_reject, can_delete


def _full_name(user: Optional[dict[str, Any]]) -> Optional[str]:
    if not user:
        return None
    name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
    return name or None


# Entry-timestamp field per status, for `_time_in_status_seconds`. `ongoing`
# is intentionally absent here: a rejected ticket re-enters `ongoing` at
# `rejected_at`, not `acknowledged_at`, so its entry timestamp needs the
# rejection-aware `_ongoing_entry_at` below rather than a single fixed field.
_STATUS_ENTRY_FIELD = {
    DownTimeStatus.PENDING.value: "created_at",
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


def _ongoing_entry_at(issue: dict[str, Any]) -> Optional[datetime]:
    """The timestamp `issue` most recently entered `ongoing`. Normally
    `acknowledged_at` — but a ticket whose resolution was rejected
    re-entered `ongoing` at `rejected_at` instead (`rejected_at` is always
    >= `acknowledged_at` by construction, so taking the later of the two
    when both parse is equivalent to preferring `rejected_at` whenever it's
    present and valid). Falls back to `acknowledged_at` alone when
    `rejected_at` is absent/unparsable — the case for every legacy document,
    which predates the reject-resolution feature."""
    acknowledged_at = _parse_iso(issue.get("acknowledged_at"))
    rejected_at = _parse_iso(issue.get("rejected_at"))
    if acknowledged_at is not None and rejected_at is not None:
        return max(acknowledged_at, rejected_at)
    return acknowledged_at


def _time_in_status_seconds(
    issue: dict[str, Any], now: datetime
) -> Optional[float]:
    """Seconds elapsed since `issue` entered its current status, measured
    against `now` (the current time in the namespace's timezone); `None`
    when the entry timestamp is missing/unparsable. `ongoing` uses the
    rejection-aware `_ongoing_entry_at`; every other status uses the fixed
    field from `_STATUS_ENTRY_FIELD`."""
    issue_status = issue.get("status")
    if issue_status == DownTimeStatus.ONGOING.value:
        entry_dt = _ongoing_entry_at(issue)
    else:
        entry_field = _STATUS_ENTRY_FIELD.get(issue_status)
        entry_dt = _parse_iso(issue.get(entry_field)) if entry_field else None
    if entry_dt is None:
        return None
    return (now - entry_dt).total_seconds()


def _batch_fetch_actor_names(
    client: FirestoreClient, issues: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """One `get_documents` round-trip across every actor id referenced by
    `issues` (see `_ACTOR_FIELDS`)."""
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
    can_acknowledge, can_resolve, can_close, can_reject, can_delete = _permission_flags(
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
        rejected_at=issue.get("rejected_at"),
        rejected_by=issue.get("rejected_by"),
        rejected_by_name=_full_name(users_by_id.get(issue.get("rejected_by"))),
        rejection_count=issue.get("rejection_count") or 0,
        can_acknowledge=can_acknowledge,
        can_resolve=can_resolve,
        can_close=can_close,
        can_reject=can_reject,
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
    `limit`/`offset`. `total` is the full count of visible (filtered) issues
    — visible meaning both role-process-visible (see `_is_visible`) and not
    on an archived resource (see `_fetch_visible_issues` /
    `_filter_archived_resource_issues`): the filter runs before pagination,
    so `total` and the page contents always agree with each other."""
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
    across the visibility boundary.

    Deliberately NOT filtered on its resource's archived state, unlike
    `list_down_times` / `get_down_time_summary` — a deep link or push
    notification sent just before the resource gets archived must keep
    resolving to a 200, not an error screen. Only the lists and the summary
    hide an archived-resource ticket."""
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
    """Mirrors `_time_in_status_seconds`'s `ongoing` branch: measured from
    `_ongoing_entry_at` (rejection-aware — `rejected_at` when the ticket
    re-entered `ongoing` via a rejection, `acknowledged_at` otherwise), not
    unconditionally from `acknowledged_at`, so a rejected ticket's time
    sitting in `resolved` isn't double-counted into the `ongoing` average."""
    entry_dt = _ongoing_entry_at(issue)
    if entry_dt is None:
        return None
    return (now - entry_dt).total_seconds()


def _resolved_duration(issue: dict[str, Any], now: datetime) -> Optional[float]:
    """`resolved_at - acknowledged_at`: deliberately NOT rejection-aware —
    this measures the whole response cycle (from the original acknowledge to
    the resolution being sent for validation), which is unaffected by
    whether a *prior* resolution on this same cycle was rejected (rejection
    resets `resolved_at`/`resolved_by`, so a ticket only reaches `resolved`
    again once re-resolved, at which point this is exactly the interval the
    KPI wants)."""
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


def _now_for_namespace(client: FirestoreClient, namespace_id: str) -> datetime:
    """Current time in the namespace's timezone — used for every elapsed-time
    computation (time_in_status_seconds, summary averages) so durations are
    measured against the tenant's local now. Timezone resolution itself is
    `src.app.core.timezone.namespace_timezone` — the single shared
    implementation both this router and the async job layer import."""
    namespace = client.get_document(NAMESPACE_COLLECTION, namespace_id)
    tz = namespace_timezone(namespace_id, namespace)
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


def _publish_down_time_update(
    down_time_id: str,
    namespace_id: str,
    event: str,
    actor_id: str,
    rejected_resolver_id: Optional[str] = None,
) -> None:
    """Best-effort publish of `JobType.NOTIFY_DOWN_TIME_UPDATE` after a
    lifecycle transition's Firestore write has already succeeded. A publish
    failure must never fail the caller's transition — the status change is
    already committed, and losing a notification is far better than 500-ing
    an otherwise-successful acknowledge/resolve/reject — so this only logs at
    error level on failure, never raises."""
    job_payload = {
        "down_time_id": down_time_id,
        "event": event,
        "actor_id": actor_id,
        "rejected_resolver_id": rejected_resolver_id,
    }
    try:
        get_pubsub_publisher().publish_job(
            JobType.NOTIFY_DOWN_TIME_UPDATE,
            namespace_id,
            job_payload,
            job_id=str(uuid.uuid4()),
        )
    except Exception:
        logger.error(
            "down_time.services: failed to publish NOTIFY_DOWN_TIME_UPDATE "
            f"for down_time_id={down_time_id} event={event}.",
            exc_info=True,
        )


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
    _publish_down_time_update(issue_id, namespace_id, "acknowledged", current["id"])

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
    _publish_down_time_update(issue_id, namespace_id, "resolved", current["id"])

    users_by_id = _batch_fetch_actor_names(client, [issue])
    return _to_down_time_out(issue, current, users_by_id, now)


def reject_resolution(issue_id: str, current: dict[str, Any]) -> DownTimeOut:
    """Reject a resolved downtime ticket's resolution, sending it back
    `resolved` -> `ongoing` (`DownTimeStatus.ONGOING`). Restricted to
    production agents; 403 when the ticket's `down_time_type` is close-only
    (see `CLOSE_ONLY_DOWNTIME_TYPES`) — checked before the status check so
    the caller sees the real reason rather than a misleading 409 (close-only
    tickets never pass through `resolved`, so this is belt-and-braces); 409
    unless the ticket is currently `resolved`.

    Retracts the resolution (`resolved_at`/`resolved_by` -> `None`,
    capturing the prior `resolved_by` as `rejected_resolver_id` for the
    notification job) and records the rejection (`rejected_at`/`rejected_by`
    plus an incremented `rejection_count`). Deliberately leaves
    `acknowledged_at`/`acknowledged_by` untouched — the ticket stays within
    the same response cycle it was already in, and resetting those would
    corrupt the acknowledge-SLA KPI."""
    client = get_firestore_client()
    namespace_id = current["namespace_id"]
    issue = _get_issue_or_404(client, namespace_id, issue_id)

    if current.get("role") != Role.PRODUCTION_AGENT.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a production agent may reject this ticket's resolution.",
        )
    if _is_close_only(issue):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This downtime type has no resolution step to reject.",
        )
    if issue.get("status") != DownTimeStatus.RESOLVED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ticket is not resolved.",
        )

    rejected_resolver_id = issue.get("resolved_by")

    now = _now_for_namespace(client, namespace_id)
    now_iso = now.isoformat()
    updates = {
        "status": DownTimeStatus.ONGOING.value,
        "resolved_at": None,
        "resolved_by": None,
        "rejected_at": now_iso,
        "rejected_by": current["id"],
        "rejection_count": (issue.get("rejection_count") or 0) + 1,
        "updated_at": now_iso,
    }
    client.update_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, issue_id, updates
    )
    issue.update(updates)
    _publish_down_time_update(
        issue_id,
        namespace_id,
        "rejected",
        current["id"],
        rejected_resolver_id=rejected_resolver_id,
    )

    users_by_id = _batch_fetch_actor_names(client, [issue])
    return _to_down_time_out(issue, current, users_by_id, now)


def _cancel_escalation_best_effort(issue: dict[str, Any]) -> None:
    """Cancel the issue's currently-scheduled escalation Cloud Task, if any.

    Reads `escalation_task_id` defensively (absent on every legacy document
    — Firestore has no migrations) and delegates to
    `core.escalation.cancel_escalation`, which is itself best-effort and
    never raises. Wrapped in a try/except anyway (belt-and-braces on top of
    belt-and-braces) so nothing this function does can ever turn a
    successful close/delete into a 500 — if cancellation doesn't land, the
    `escalate_down_time` async handler's own `closed`/missing-issue branches
    are the real safety net that stops the chain."""
    try:
        cancel_escalation(issue.get("escalation_task_id"))
    except Exception:
        logger.warning(
            "down_time.services: escalation cancellation raised unexpectedly "
            f"for down_time_id={issue.get('id')}.",
            exc_info=True,
        )


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
    ticket reachable.

    Closing is the terminal state: after the status update succeeds, the
    scheduled escalation Cloud Task (if any) is cancelled and
    `escalation_task_id` is cleared in the same update (see
    `_cancel_escalation_best_effort` / module docstring) so no further
    escalation can fire on this ticket."""
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
        "escalation_task_id": None,
    }
    client.update_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, issue_id, updates
    )
    _cancel_escalation_best_effort(issue)
    issue.update(updates)

    users_by_id = _batch_fetch_actor_names(client, [issue])
    return _to_down_time_out(issue, current, users_by_id, now)


def delete_down_time(issue_id: str, current: dict[str, Any]) -> DownTimeOut:
    """Delete a still-pending downtime ticket. Restricted to the production
    agent who opened it (`created_by`); 409 unless the ticket is currently
    `pending`.

    A deleted ticket leaves the workflow entirely, so its scheduled
    escalation Cloud Task (if any) is cancelled before the document is
    deleted — otherwise the task would still fire 30 minutes later, find no
    issue, and log noise every cycle (see `_cancel_escalation_best_effort` /
    module docstring)."""
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

    _cancel_escalation_best_effort(issue)
    client.delete_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, issue_id
    )
    return result



# --------------------------------------------------------------------------
# GET /down-times/gantt — see `.claude/specs/downtime-gantt.md` §2.
# --------------------------------------------------------------------------


def _project_shift(
    shift_number: str, shift: dict[str, Any], day: date_cls, tz: Any
) -> GanttShiftOut:
    """Projects one configured shift's clock window (and optional break) onto
    absolute datetimes of `day`, in `tz` (§2.2). Midnight-wrap aware via
    plain `timedelta` arithmetic from `day`'s own local midnight — a shift
    (or its break) whose length pushes past 24h naturally lands on the next
    calendar day, no separate wrap branch needed. `_configured_shifts`
    (`kpi.services`) only ever returns shifts whose own window already
    parses, so `start_time`/`end_time` are trusted here.

    B1 (review finding): an equal start/end clock pair is ambiguous between
    "0 minutes" and "24h" (see `core.shift_time.window_length_minutes`'s own
    docstring, which explicitly leaves the choice to the caller). The KPI
    planned-time computation resolves it as a full 24h shift; the gantt
    deliberately resolves it as a zero-length, unusable shift instead, so a
    misconfigured shift degrades `_gantt_window` to its calendar-day
    fallback rather than silently producing a full-day window nobody
    configured.

    W4 (review finding): the break is validated via `kpi.services._valid_break`
    — the SAME rule the KPI layer applies (non-zero length, falls inside its
    own shift window) — rather than a bare clock parse, so a corrupted OR
    out-of-window break is ignored here exactly as the KPIs ignore it. Two
    layers reading the same namespace's planned time must never disagree on
    what counts as a valid break."""
    day_start = datetime.combine(day, time.min, tzinfo=tz)
    start_minutes = parse_hhmm(shift["start_time"])
    end_minutes = parse_hhmm(shift["end_time"])
    length_minutes = (
        0
        if end_minutes == start_minutes
        else window_length_minutes(start_minutes, end_minutes)
    )
    start_dt = day_start + timedelta(minutes=start_minutes)
    end_dt = start_dt + timedelta(minutes=length_minutes)

    break_start_dt: Optional[datetime] = None
    break_end_dt: Optional[datetime] = None
    valid_break = kpi_services._valid_break(shift)
    if valid_break is not None:
        break_start_minutes, _break_end_minutes, break_length_minutes = valid_break
        offset_minutes = (break_start_minutes - start_minutes) % (24 * 60)
        break_start_dt = start_dt + timedelta(minutes=offset_minutes)
        break_end_dt = break_start_dt + timedelta(minutes=break_length_minutes)

    return GanttShiftOut(
        shift=shift_number,
        start=start_dt.isoformat(),
        end=end_dt.isoformat(),
        break_start=break_start_dt.isoformat() if break_start_dt else None,
        break_end=break_end_dt.isoformat() if break_end_dt else None,
    )


def _gantt_window(
    settings: dict[str, Any], day: date_cls, tz: Any
) -> tuple[datetime, datetime, list[GanttShiftOut]]:
    """`(window_start, window_end, shifts)` for `day` (§2.2). Reuses
    `kpi.services._configured_shifts` for the "configured shift" notion
    (`shift_number`, parsable clock windows, optional break) so the gantt
    never re-derives what counts as a usable shift. Falls back to the
    calendar day `[00:00, 24:00)`, `shifts: []`, when the namespace has no
    usable shift configuration at all (no settings document, or no shift
    carries a parsable window).

    B1 (review finding): `window_start`/`window_end` are the `min`/`max` of
    the PROJECTED shift datetimes, NEVER `shifts[0]`/`shifts[-1]` of
    declaration order — a namespace that numbers a later shift `shift_1`
    (e.g. the night shift) must not get a truncated/zero-length window just
    because `shift_1` isn't the chronologically first shift. `shifts[]` is
    returned in chronological (projected-start) order, regardless of
    declaration order, for the same reason. Whenever the computed window
    isn't strictly ordered (`window_end` not strictly after `window_start`
    — e.g. every configured shift degenerate, see `_project_shift`'s
    zero-length guard), falls back to the calendar day the same way the "no
    usable shift configuration" case does, while still returning the
    projected `shifts[]` (unlike that case, which has none to return)."""
    configured = kpi_services._configured_shifts(settings)
    if not configured:
        window_start = datetime.combine(day, time.min, tzinfo=tz)
        window_end = window_start + timedelta(days=1)
        return window_start, window_end, []

    projected = [
        _project_shift(shift_number, shift, day, tz)
        for shift_number, shift in configured
    ]
    starts = [datetime.fromisoformat(p.start) for p in projected]
    ends = [datetime.fromisoformat(p.end) for p in projected]

    window_start = min(starts)
    window_end = max(ends)
    shifts = [p for _, p in sorted(zip(starts, projected), key=lambda pair: pair[0])]

    if window_end <= window_start:
        window_start = datetime.combine(day, time.min, tzinfo=tz)
        window_end = window_start + timedelta(days=1)

    return window_start, window_end, shifts


def _issue_segments(
    issue: dict[str, Any], window_end: datetime
) -> list[tuple[datetime, datetime, str]]:
    """The raw (unclamped) `(start, end, state)` segments a single issue
    contributes (§2.3), derived purely from its own stored timestamps —
    never from `status` — so this only needs whatever combination of
    `created_at`/`resolved_at`/`closed_at` the document actually carries:

    - Never resolved (`resolved_at` absent): one open `down` segment,
      `created_at -> window_end`. This is ALSO the shape of a rejected
      resolution: `reject_resolution` nulls `resolved_at`/`resolved_by` back
      to `None` when production sends a fix back (see
      `services.reject_resolution`), so a rejected ticket is
      indistinguishable, at the stored-document level, from one that was
      simply never resolved — it therefore renders as ONE continuous `down`
      bar from `created_at` to `window_end`, the conservative and honest
      rendering since production itself said the resource was not back
      (§2.3, developer ruling 2026-09-11).
    - Resolved: `down` runs `created_at -> resolved_at`. The `unconfirmed`
      tail that follows ends at `closed_at` (normal close), or stays open to
      `window_end` when the ticket was never closed.

    Deliberately no `rejected_at`-aware branch: with `resolved_at` always
    cleared by a rejection, the resolved -> rejected `unconfirmed` slice
    that preceded it is not recoverable from the stored document, and the
    application never writes a document carrying both `resolved_at` and
    `rejected_at` together — a branch trying to recover it would be dead
    code no real seed could ever reach (review finding, `reject_resolution`
    nulling `resolved_at`; see
    `test_rejected_resolution_renders_one_continuous_down_bar`, which is the
    only legitimate seed shape for a rejected ticket)."""
    created_at = _parse_iso(issue.get("created_at"))
    if created_at is None:
        return []

    resolved_at = _parse_iso(issue.get("resolved_at"))
    if resolved_at is None:
        return [(created_at, window_end, "down")]

    closed_at = _parse_iso(issue.get("closed_at"))
    unconfirmed_end = closed_at if closed_at is not None else window_end
    return [
        (created_at, resolved_at, "down"),
        (resolved_at, unconfirmed_end, "unconfirmed"),
    ]


def _clamp_interval(
    start: datetime, end: datetime, window_start: datetime, window_end: datetime
) -> Optional[tuple[datetime, datetime]]:
    """Clamps `[start, end)` to `[window_start, window_end]` (§2.3); `None`
    when the clamped interval is empty (entirely outside the window)."""
    clamped_start = max(start, window_start)
    clamped_end = min(end, window_end)
    if clamped_start >= clamped_end:
        return None
    return clamped_start, clamped_end


def _merge_intervals(
    intervals: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    """Merges overlapping OR TOUCHING intervals (§2.3) — `end == next start`
    counts as touching, so two segments sharing a boundary merge into one."""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda pair: pair[0])
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _subtract_intervals(
    targets: list[tuple[datetime, datetime]],
    cuts: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """`targets` with every interval in `cuts` removed from it, splitting a
    target into up to two pieces per overlapping cut (§2.3 — `down` wins
    over `unconfirmed`). `cuts`/`targets` are each assumed already merged
    (non-overlapping among themselves)."""
    result = list(targets)
    for cut_start, cut_end in cuts:
        next_result: list[tuple[datetime, datetime]] = []
        for start, end in result:
            if cut_end <= start or cut_start >= end:
                next_result.append((start, end))
                continue
            if cut_start > start:
                next_result.append((start, cut_start))
            if cut_end < end:
                next_result.append((cut_end, end))
        result = next_result
    return result


def _row_intervals(
    issues: list[dict[str, Any]], window_start: datetime, window_end: datetime
) -> list[GanttIntervalOut]:
    """The final, sorted `down_times[]` for one resource row (§2.3): every
    issue's raw segments, clamped to the window, merged per state, then
    `down` subtracted from any overlapping `unconfirmed` (a confirmed stop
    beats an unsure availability). Empty when nothing survives clamping —
    the caller drops the row in that case (§2.1 "only if it has at least one
    interval")."""
    down_raw: list[tuple[datetime, datetime]] = []
    unconfirmed_raw: list[tuple[datetime, datetime]] = []
    for issue in issues:
        for start, end, state in _issue_segments(issue, window_end):
            clamped = _clamp_interval(start, end, window_start, window_end)
            if clamped is None:
                continue
            (down_raw if state == "down" else unconfirmed_raw).append(clamped)

    down_merged = _merge_intervals(down_raw)
    unconfirmed_merged = _subtract_intervals(
        _merge_intervals(unconfirmed_raw), down_merged
    )

    combined = [(s, e, "down") for s, e in down_merged] + [
        (s, e, "unconfirmed") for s, e in unconfirmed_merged
    ]
    combined.sort(key=lambda triple: triple[0])
    return [
        GanttIntervalOut(start_time=s.isoformat(), end_time=e.isoformat(), state=state)
        for s, e, state in combined
    ]


def _own_scope_groups(
    issues: list[dict[str, Any]]
) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
    list[dict[str, Any]],
]:
    """`(by_station, by_line, by_uap, plant_issues)` — `issues` bucketed by
    their own most-specific stored id (§2.4: "a ticket scoped uap/line/
    workstation appears only on its own resource row — no propagation"), or
    `plant_issues` when the ticket carries none of the three (a `plant`
    -scope ticket, which names no resource)."""
    by_station: dict[str, list[dict[str, Any]]] = {}
    by_line: dict[str, list[dict[str, Any]]] = {}
    by_uap: dict[str, list[dict[str, Any]]] = {}
    plant_issues: list[dict[str, Any]] = []
    for issue in issues:
        if issue.get("workstation_id"):
            by_station.setdefault(issue["workstation_id"], []).append(issue)
        elif issue.get("production_line_id"):
            by_line.setdefault(issue["production_line_id"], []).append(issue)
        elif issue.get("uap_id"):
            by_uap.setdefault(issue["uap_id"], []).append(issue)
        else:
            plant_issues.append(issue)
    return by_station, by_line, by_uap, plant_issues


def _uap_rows(
    groups: dict[str, list[dict[str, Any]]],
    uaps: dict[str, dict[str, Any]],
    window_start: datetime,
    window_end: datetime,
) -> list[GanttUapRowOut]:
    rows = []
    for uap_id, issues in groups.items():
        uap = uaps.get(uap_id)
        if uap is None:
            continue
        down_times = _row_intervals(issues, window_start, window_end)
        if not down_times:
            continue
        rows.append(
            GanttUapRowOut(uap_id=uap_id, name=uap.get("name", ""), down_times=down_times)
        )
    rows.sort(key=lambda row: row.uap_id)
    return rows


def _line_rows(
    groups: dict[str, list[dict[str, Any]]],
    lines: dict[str, dict[str, Any]],
    window_start: datetime,
    window_end: datetime,
) -> list[GanttLineRowOut]:
    rows = []
    for line_id, issues in groups.items():
        line = lines.get(line_id)
        if line is None:
            continue
        down_times = _row_intervals(issues, window_start, window_end)
        if not down_times:
            continue
        rows.append(
            GanttLineRowOut(
                line_id=line_id, name=line.get("name", ""), down_times=down_times
            )
        )
    rows.sort(key=lambda row: row.line_id)
    return rows


def _station_rows(
    groups: dict[str, list[dict[str, Any]]],
    stations: dict[str, dict[str, Any]],
    window_start: datetime,
    window_end: datetime,
) -> list[GanttWorkStationRowOut]:
    rows = []
    for station_id, issues in groups.items():
        station = stations.get(station_id)
        if station is None:
            continue
        down_times = _row_intervals(issues, window_start, window_end)
        if not down_times:
            continue
        rows.append(
            GanttWorkStationRowOut(
                workstation_id=station_id,
                name=station.get("name", ""),
                type=kpi_services._station_type(station),
                down_times=down_times,
            )
        )
    rows.sort(key=lambda row: row.workstation_id)
    return rows


def _unfiltered_gantt_rows(
    hierarchy: dict[str, Any],
    by_station: dict[str, list[dict[str, Any]]],
    by_line: dict[str, list[dict[str, Any]]],
    by_uap: dict[str, list[dict[str, Any]]],
    plant_issues: list[dict[str, Any]],
    window_start: datetime,
    window_end: datetime,
) -> tuple[list[GanttUapRowOut], list[GanttLineRowOut], list[GanttWorkStationRowOut]]:
    """§2.4, no `type` filter: each resource's own-scope issues, plus — for
    the dominant location level only (`kpi.services._pick_location_kind`,
    reused so this never drifts from the dashboard's `by_location` rule) —
    every `plant`-scope issue spread onto EVERY ACTIVE resource of that
    level.

    W3 (review finding): the spread is restricted to active resources
    (`core.archiving.is_active`) — an archived UAP/line/station must not
    receive a bar for a plant-wide ticket it never lived through. This does
    not contradict §2.6: a resource's OWN-scope tickets (`by_station`/
    `by_line`/`by_uap` above) are never filtered by archiving, so an
    archived resource carrying a ticket of its own still appears."""
    uap_groups = {uap_id: list(issues) for uap_id, issues in by_uap.items()}
    line_groups = {line_id: list(issues) for line_id, issues in by_line.items()}
    station_groups = {sid: list(issues) for sid, issues in by_station.items()}

    if plant_issues:
        kind = kpi_services._pick_location_kind(hierarchy)
        if kind == "uap":
            for uap_id, uap in hierarchy["uaps"].items():
                if is_active(uap):
                    uap_groups.setdefault(uap_id, []).extend(plant_issues)
        elif kind == "line":
            for line_id, line in hierarchy["lines"].items():
                if is_active(line):
                    line_groups.setdefault(line_id, []).extend(plant_issues)
        else:
            for station_id, station in hierarchy["stations"].items():
                if is_active(station):
                    station_groups.setdefault(station_id, []).extend(plant_issues)

    return (
        _uap_rows(uap_groups, hierarchy["uaps"], window_start, window_end),
        _line_rows(line_groups, hierarchy["lines"], window_start, window_end),
        _station_rows(station_groups, hierarchy["stations"], window_start, window_end),
    )


def _type_filtered_station_rows(
    type_filter: str,
    hierarchy: dict[str, Any],
    by_station: dict[str, list[dict[str, Any]]],
    by_line: dict[str, list[dict[str, Any]]],
    by_uap: dict[str, list[dict[str, Any]]],
    plant_issues: list[dict[str, Any]],
    window_start: datetime,
    window_end: datetime,
) -> list[GanttWorkStationRowOut]:
    """§2.5 — every workstation of the namespace whose `type` matches
    `type_filter`, wherever it hangs, with its own tickets UNIONED with its
    ancestors' (line/UAP/plant) — ancestor downtime propagates down in this
    mode, unlike the unfiltered §2.4 "own row only" rule. `plant_issues`
    apply unconditionally here (every matching station, regardless of the
    namespace's dominant location level — a different rule from the
    unfiltered spread in `_unfiltered_gantt_rows`)."""
    rows = []
    for station_id, station in hierarchy["stations"].items():
        if kpi_services._station_type(station) != type_filter:
            continue

        line_id = hierarchy["station_to_line"].get(station_id)
        uap_id = hierarchy["line_to_uap"].get(line_id) if line_id else None

        issues = list(by_station.get(station_id, []))
        if line_id:
            issues += by_line.get(line_id, [])
        if uap_id:
            issues += by_uap.get(uap_id, [])
        issues += plant_issues

        down_times = _row_intervals(issues, window_start, window_end)
        if not down_times:
            continue
        rows.append(
            GanttWorkStationRowOut(
                workstation_id=station_id,
                name=station.get("name", ""),
                type=kpi_services._station_type(station),
                down_times=down_times,
            )
        )
    rows.sort(key=lambda row: row.workstation_id)
    return rows


def _fetch_gantt_issues(
    client: FirestoreClient,
    namespace_id: str,
    window_start: datetime,
    window_end: datetime,
) -> list[dict[str, Any]]:
    """The namespace's downtime issues that can possibly overlap `window`
    (§2.3's "every issue whose downtime overlaps window") — bounded, unlike
    the naive "read the whole subcollection" it replaces (review finding
    W2). Mirrors `kpi.services._fetch_tickets`'s bounded-query-union
    convention: three independent, parallelized (`kpi_services._run_parallel`)
    queries, de-duplicated by id afterward, rather than one Firestore field
    filter per issue:

    1. `created_at` inside `[window_start, window_end]` — issues that
       started during the window.
    2. `status` in the open set (pending/ongoing/resolved) — an issue
       created before the window that is still live may still overlap it
       (an open-ended `down`/`unconfirmed` tail, §2.3).
    3. `closed_at >= window_start` — an issue created before the window
       whose CLOSE happened inside/after it; `closed_at` is always the
       latest timestamp a document can carry, so this is the only
       closed-issue case that can still overlap `window` (a `closed_at`
       before `window_start` means every one of its segments already ended
       before the window, per `_issue_segments`/`_clamp_interval`).

    Every issue this excludes is `created_at`-before-`window_start` AND
    (not `status`-open AND (no `closed_at`, or `closed_at` before
    `window_start`)) — i.e. every one of its `_issue_segments` necessarily
    ends before `window_start`, so `_clamp_interval` would drop it anyway;
    the result set is therefore identical to the unbounded read, just
    without paying to fetch the tenant's whole ticket history for a
    one-day view."""
    created_in_window, still_open, closed_after_window_start = kpi_services._run_parallel(
        [
            lambda: client.find_subdocuments(
                DOWN_TIME_COLLECTION,
                namespace_id,
                ISSUES_SUBCOLLECTION,
                params={
                    "created_at": [
                        (">=", window_start.isoformat()),
                        ("<=", window_end.isoformat()),
                    ]
                },
            ),
            lambda: client.find_subdocuments(
                DOWN_TIME_COLLECTION,
                namespace_id,
                ISSUES_SUBCOLLECTION,
                params={"status": [("in", kpi_services._OPEN_STATUSES)]},
            ),
            lambda: client.find_subdocuments(
                DOWN_TIME_COLLECTION,
                namespace_id,
                ISSUES_SUBCOLLECTION,
                params={"closed_at": [(">=", window_start.isoformat())]},
            ),
        ]
    )
    by_id: dict[str, dict[str, Any]] = {}
    for issue in (*created_in_window, *still_open, *closed_after_window_start):
        issue_id = issue.get("id")
        if issue_id:
            by_id[issue_id] = issue
    return list(by_id.values())


def get_down_time_gantt(
    day: Optional[date_cls],
    type_filter: Optional[str],
    current: dict[str, Any],
) -> DownTimeGanttOut:
    """`GET /down-times/gantt` (§2 of the BOM). Tenant-scoped to the caller's
    namespace; no role-based process narrowing beyond the endpoint's own
    role scope (§2.6) — every issue of the namespace is a candidate,
    including ones on an archived resource (unlike `list_down_times`)."""
    client = get_firestore_client()
    namespace_id = current["namespace_id"]

    _namespace, tz, settings = kpi_services._namespace_context(client, namespace_id)
    resolved_day = day or datetime.now(tz).date()
    window_start, window_end, shifts = _gantt_window(settings, resolved_day, tz)

    issues = _fetch_gantt_issues(client, namespace_id, window_start, window_end)
    by_station, by_line, by_uap, plant_issues = _own_scope_groups(issues)
    hierarchy = kpi_services._location_hierarchy(client, namespace_id)

    if type_filter is None:
        uaps, lines, work_stations = _unfiltered_gantt_rows(
            hierarchy,
            by_station,
            by_line,
            by_uap,
            plant_issues,
            window_start,
            window_end,
        )
    else:
        uaps, lines = [], []
        work_stations = _type_filtered_station_rows(
            type_filter,
            hierarchy,
            by_station,
            by_line,
            by_uap,
            plant_issues,
            window_start,
            window_end,
        )

    return DownTimeGanttOut(
        day=resolved_day.isoformat(),
        window=GanttWindowOut(start=window_start.isoformat(), end=window_end.isoformat()),
        shifts=shifts,
        uaps=uaps,
        lines=lines,
        work_stations=work_stations,
    )


def get_down_time_summary(current: dict[str, Any]) -> DownTimeSummaryOut:
    """Aggregate counts + average elapsed time per status, over the caller's
    visible issues (see module docstring for the per-status average
    definitions) — visible issues excludes archived-resource tickets the
    same way `list_down_times` does, via the shared `_fetch_visible_issues`,
    so the two stay consistent with each other."""
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
