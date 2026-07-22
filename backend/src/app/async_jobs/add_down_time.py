"""`add_down_time` async job handler.

Declares a new downtime ticket ("issue") under
`down_time/{namespace_id}/issues/{job_id}` and notifies the online process
agents (e.g. "maintenance agent") responsible for it via push notification.

Trigger: published (job_type=`JobType.ADD_DOWN_TIME`) by the downtime-ticket
creation endpoint (owned by the api sub-factory) once a workstation/line/UAP
stop is declared.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import backoff

from src.app.core.firestore import NAMESPACE_COLLECTION, USERS_COLLECTION
from src.app.core.push import send_push_notifications
from src.app.gcp import get_firestore_client
from src.app.globals.enum import (
    DOWNTIME_TYPE_PROCESS,
    DownTimeStatus,
    DownTimeType,
    Process,
)

from .exceptions import FunctionalJobError

logger = logging.getLogger(__name__)

DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"

_REQUIRED_FIELDS = (
    "created_by",
    "production_scope",
    "down_time_type",
)


def _resolve_timezone(namespace_id: str, namespace: dict | None) -> ZoneInfo:
    """Resolve the namespace's IANA timezone, defaulting to UTC when missing,
    blank, or unknown."""
    tz_name = (namespace or {}).get("timezone") or "UTC"
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning(
            f"add_down_time: unknown timezone '{tz_name}' for namespace "
            f"'{namespace_id}', defaulting to UTC."
        )
        return ZoneInfo("UTC")


def _resolve_process(down_time_type: DownTimeType, department: str | None) -> Process:
    """Resolve the process/department that owns this downtime ticket."""
    if down_time_type == DownTimeType.SETUP_CHANGEOVER:
        if not department:
            raise FunctionalJobError(
                "add_down_time: 'department' is required when "
                "down_time_type is Setup / Changeover."
            )
        try:
            return Process(department)
        except ValueError as e:
            raise FunctionalJobError(
                f"add_down_time: invalid 'department' value '{department}'."
            ) from e

    return DOWNTIME_TYPE_PROCESS[down_time_type]


def _notify_process_agents(firestore, namespace_id: str, process: Process, job_id: str) -> None:
    """Best-effort push notification to every online agent of the given
    process (e.g. "maintenance agent") in this namespace."""
    role = f"{process.value} agent"

    users = firestore.find_documents(
        USERS_COLLECTION, {"namespace_id": namespace_id, "role": role}
    )
    # Absent `online` defaults to True (documented default: users may not
    # have this field yet, schemaless collection).
    online_users = [u for u in users if u.get("online", True)]
    tokens = [u["push_token"] for u in online_users if u.get("push_token")]

    if not tokens:
        logger.info(
            f"add_down_time: no online '{role}' with a push token to notify "
            f"in namespace '{namespace_id}' for issue '{job_id}'."
        )
        return

    send_push_notifications(
        tokens,
        title="New downtime ticket",
        body=f"A new {process.value} downtime ticket needs attention.",
        data={"down_time_id": job_id, "process": process.value},
    )


def _on_giveup(details: dict) -> None:
    """Log when a job exhausts its retries. `raise_on_giveup=False` means the
    handler then returns normally, so the worker route still acks OK to the
    broker (a job that keeps failing must not be requeued forever)."""
    logger.error(
        f"add_down_time: gave up after {details.get('tries')} attempt(s): "
        f"{details.get('exception')}"
    )


@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=3,
    on_giveup=_on_giveup,
    raise_on_giveup=False,
)
def add_down_time(namespace_id: str, payload: dict, job_id: str) -> dict:
    """
    Declare a new downtime ticket and notify the responsible process agents.

    Retry model (per `.claude/skills/async`): the body is wrapped in
    `try/except`. A `FunctionalJobError` (invalid input / business rule) is
    logged and returns an OK result — it is NOT retried. Any other
    (system/external/transient) failure propagates to the `backoff` decorator,
    which retries up to 3 times; on exhaustion `_on_giveup` logs and the handler
    returns (OK to the broker). The handler is idempotent (keyed on `job_id`).

    Returns:
        A small result dict (`{status, ...}`) describing the outcome, which the
        worker route returns to the broker.
    """
    try:
        return _run_add_down_time(namespace_id, payload, job_id)
    except FunctionalJobError as e:
        logger.warning(
            f"add_down_time: functional failure (job_id={job_id}): {e}. "
            "Logged and acked — no retry."
        )
        return {"status": "skipped", "reason": str(e), "down_time_id": job_id}


def _run_add_down_time(namespace_id: str, payload: dict, job_id: str) -> dict:
    """The actual work. Raises `FunctionalJobError` for invalid input /
    business-rule violations (caught and acked by `add_down_time`); lets any
    system/transient error propagate to the retry decorator."""
    if not namespace_id:
        raise FunctionalJobError("add_down_time: 'namespace_id' is required.")
    if not job_id:
        raise FunctionalJobError("add_down_time: 'job_id' is required.")

    missing = [f for f in _REQUIRED_FIELDS if not payload.get(f)]
    if missing:
        raise FunctionalJobError(
            f"add_down_time: missing required payload field(s): {missing}."
        )

    firestore = get_firestore_client()

    # --- Idempotency: if this issue was already written, this job was
    # already processed (at-least-once delivery) — nothing more to do. ---
    existing = firestore.get_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, job_id
    )
    if existing is not None:
        logger.info(
            f"add_down_time: issue '{job_id}' already exists in namespace "
            f"'{namespace_id}', skipping (idempotent replay)."
        )
        return {"status": "skipped", "reason": "already processed", "down_time_id": job_id}

    try:
        down_time_type = DownTimeType(payload["down_time_type"])
    except ValueError as e:
        raise FunctionalJobError(
            f"add_down_time: invalid 'down_time_type' value "
            f"'{payload.get('down_time_type')}'."
        ) from e

    process = _resolve_process(down_time_type, payload.get("department"))

    # The namespace must exist — never create a downtime issue under an unknown
    # tenant (guards against forged/stale job messages writing orphan
    # `down_time/{namespace_id}` subcollections).
    namespace = firestore.get_document(NAMESPACE_COLLECTION, namespace_id)
    if namespace is None:
        raise FunctionalJobError(
            f"add_down_time: no namespace '{namespace_id}' — refusing to create "
            "a downtime for an unknown tenant."
        )

    tz = _resolve_timezone(namespace_id, namespace)
    now_iso = datetime.now(tz).isoformat()

    is_setup_changeover = down_time_type == DownTimeType.SETUP_CHANGEOVER

    issue_data = {
        "id": job_id,
        "namespace_id": namespace_id,
        "created_at": now_iso,
        "updated_at": now_iso,
        "down_time_scope": payload["production_scope"],
        "uap_id": payload.get("uap_id"),
        "production_line_id": payload.get("production_line_id"),
        "workstation_id": payload.get("workstation_id"),
        "down_time_type": payload["down_time_type"],
        "department": payload.get("department") if is_setup_changeover else None,
        "process": process.value,
        "status": DownTimeStatus.PENDING.value,
        "created_by": payload["created_by"],
    }

    firestore.create_subdocument(
        DOWN_TIME_COLLECTION,
        namespace_id,
        ISSUES_SUBCOLLECTION,
        issue_data,
        document_id=job_id,
    )

    _notify_process_agents(firestore, namespace_id, process, job_id)

    return {"status": "created", "down_time_id": job_id}
