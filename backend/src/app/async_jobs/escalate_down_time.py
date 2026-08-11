"""`escalate_down_time` async job handler.

The 30-minute management-escalation chain for an unresolved downtime ticket
(see `src.app.core.escalation`). Each run is one cycle of a self-rescheduling
Cloud Task: it re-evaluates the ticket's current status and, unless the
ticket is closed, notifies the relevant people and schedules the next cycle
`ESCALATION_DELAY_SECONDS` later.

Trigger: scheduled (job_type=`JobType.ESCALATE_DOWN_TIME`) via
`core.escalation.schedule_escalation` — first from `add_down_time` (when
`should_escalate` is true for the newly created ticket), then re-scheduled by
this handler itself on every cycle that doesn't end the chain.

Behavior per current ticket status:
  * `closed` — terminal. No notification, no reschedule. Clears
    `escalation_task_id` (safety net if a `cancel_escalation` call upstream
    failed to delete the pending task).
  * `resolved` — the fix is applied but production hasn't confirmed it back
    to normal yet. Notifies only the online production agents (push only,
    no email, no management alert of any kind), then reschedules.
  * `pending` / `ongoing` — still unresolved. Escalates to management (push +
    email) — manager, owner, production supervisor, and the ticket's own
    process supervisor, deduplicated by user id — then reschedules.
  * missing issue (deleted ticket) — stops the chain without rescheduling;
    this is the normal/expected end of the chain for a deleted ticket, not an
    error, so it's logged at info.

A missing issue and a `closed` status are both terminal outcomes reached
without going through `FunctionalJobError` (which would log at warning) —
these are ordinary, expected ends of the chain, not invalid input.
"""

from __future__ import annotations

import logging
from datetime import datetime

import backoff

from src.app.core.email import send_down_time_escalation_email
from src.app.core.escalation import schedule_escalation
from src.app.core.firestore import NAMESPACE_COLLECTION, USERS_COLLECTION
from src.app.core.notifications import (
    escalation_notification,
    format_duration,
    resolution_reminder_notification,
)
from src.app.core.push import send_push_notifications
from src.app.core.timezone import namespace_timezone
from src.app.gcp import get_firestore_client
from src.app.globals.enum import DownTimeStatus, Process, Role, language_of

from ._common import DOWN_TIME_COLLECTION, ISSUES_SUBCOLLECTION, resolve_location
from .exceptions import FunctionalJobError

logger = logging.getLogger(__name__)

# Roles always alerted on a management escalation, regardless of the
# ticket's process (the ticket's own process supervisor role, e.g.
# "maintenance supervisor", is added to this set at call time).
_ALWAYS_ESCALATE_ROLES = frozenset(
    {Role.MANAGER.value, Role.OWNER.value, Role.PRODUCTION_SUPERVISOR.value}
)


def _duration_since(
    timestamp_iso: str | None, namespace: dict | None, namespace_id: str, language
) -> str | None:
    """Best-effort elapsed-time-since-`timestamp_iso` string. Returns `None`
    (never raises) when the timestamp is missing/unparsable, so the caller
    can fall back gracefully rather than ever rendering "None"."""
    if not timestamp_iso:
        return None
    try:
        ts = datetime.fromisoformat(timestamp_iso)
    except (TypeError, ValueError):
        logger.warning(
            f"escalate_down_time: unparsable timestamp '{timestamp_iso}' for "
            f"issue in namespace '{namespace_id}', omitting duration."
        )
        return None

    tz = namespace_timezone(namespace_id, namespace)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=tz)
    now = datetime.now(tz)
    elapsed_seconds = (now - ts).total_seconds()
    return format_duration(elapsed_seconds, language)


def _notify_production_agents_awaiting_confirmation(
    firestore,
    namespace_id: str,
    issue: dict,
    namespace: dict | None,
    language,
    location: str,
    down_time_id: str,
) -> None:
    """Push-only reminder to every online production agent that a resolved
    ticket is waiting on their confirmation/rejection. Same recipient rule
    `add_down_time._notify_process_agents` uses (absent `online` defaults to
    True, tokens filtered) — but scoped to `Role.PRODUCTION_AGENT` only,
    never the process agents of the ticket's own process."""
    role = Role.PRODUCTION_AGENT.value

    users = firestore.find_documents(
        USERS_COLLECTION, {"namespace_id": namespace_id, "role": role}
    )
    online_users = [u for u in users if u.get("online", True)]
    tokens = [u["push_token"] for u in online_users if u.get("push_token")]

    if not tokens:
        logger.info(
            f"escalate_down_time: no online production agent with a push "
            f"token to notify in namespace '{namespace_id}' for issue "
            f"'{down_time_id}'."
        )
        return

    duration = _duration_since(issue.get("resolved_at"), namespace, namespace_id, language)
    title, body = resolution_reminder_notification(
        language, location, duration or format_duration(0, language)
    )
    send_push_notifications(
        tokens,
        title=title,
        body=body,
        data={"down_time_id": down_time_id, "event": "resolution_reminder"},
    )


def _notify_management(
    firestore,
    namespace_id: str,
    issue: dict,
    namespace: dict | None,
    language,
    location: str,
    down_time_id: str,
) -> None:
    """Push + email alert to management: manager, owner, production
    supervisor, and the ticket's own process supervisor. Deduplicated by user
    id — for a production-process ticket the production supervisor and the
    process supervisor are the same role, and nobody should get two copies.

    Deliberately does NOT filter on `online`, unlike the agent notifications:
    this is a management escalation and must reach them regardless of
    presence — same product decision already made for the `OTHERS`
    production-supervisor alert in `add_down_time` (mirrored here)."""
    roles = set(_ALWAYS_ESCALATE_ROLES)
    try:
        process = Process(issue.get("process"))
    except ValueError:
        process = None
    if process is not None:
        roles.add(f"{process.value} supervisor")

    recipients: dict[str, dict] = {}
    for role in roles:
        users = firestore.find_documents(
            USERS_COLLECTION, {"namespace_id": namespace_id, "role": role}
        )
        for user in users:
            uid = user.get("id")
            if uid:
                recipients[uid] = user

    if not recipients:
        logger.info(
            f"escalate_down_time: no management recipients to notify in "
            f"namespace '{namespace_id}' for issue '{down_time_id}'."
        )
        return

    duration = _duration_since(issue.get("created_at"), namespace, namespace_id, language)
    title, body = escalation_notification(
        language, location, duration or format_duration(0, language)
    )

    tokens = [u["push_token"] for u in recipients.values() if u.get("push_token")]
    if tokens:
        send_push_notifications(
            tokens,
            title=title,
            body=body,
            data={"down_time_id": down_time_id, "event": "escalation"},
        )

    for user in recipients.values():
        email = user.get("email")
        if not email:
            continue
        try:
            send_down_time_escalation_email(
                email, language, location, duration or format_duration(0, language)
            )
        except Exception as e:
            # Best-effort, per-recipient: one bad address must never skip the
            # rest of the fan-out. Log the user id, never the email address.
            logger.warning(
                f"escalate_down_time: failed to send escalation email to "
                f"user '{user.get('id')}' for issue '{down_time_id}': {e}"
            )


def _reschedule(
    firestore, namespace_id: str, namespace: dict | None, issue: dict, down_time_id: str
) -> None:
    """Schedule the next escalation cycle and persist its id (replacing the
    stale one) plus bookkeeping fields on the issue. Best-effort:
    `schedule_escalation` never raises; if it returns `None` (Cloud Tasks
    outage), the chain silently ends here — no id to persist, nothing more we
    can do (mirrors `core.escalation`'s own best-effort posture)."""
    new_task_id = schedule_escalation(
        namespace_id, down_time_id, (namespace or {}).get("timezone")
    )
    if not new_task_id:
        return

    tz = namespace_timezone(namespace_id, namespace)
    escalation_count = (issue.get("escalation_count") or 0) + 1
    firestore.update_subdocument(
        DOWN_TIME_COLLECTION,
        namespace_id,
        ISSUES_SUBCOLLECTION,
        down_time_id,
        {
            "escalation_task_id": new_task_id,
            "escalated_at": datetime.now(tz).isoformat(),
            "escalation_count": escalation_count,
        },
    )


def _on_giveup(details: dict) -> None:
    """Log when a job exhausts its retries. `raise_on_giveup=False` means the
    handler then returns normally, so the worker route still acks OK to the
    broker (a job that keeps failing must not be requeued forever)."""
    logger.error(
        f"escalate_down_time: gave up after {details.get('tries')} attempt(s): "
        f"{details.get('exception')}"
    )


@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=3,
    on_giveup=_on_giveup,
    raise_on_giveup=False,
)
def escalate_down_time(namespace_id: str, payload: dict, job_id: str) -> dict:
    """
    Run one cycle of a downtime ticket's management-escalation chain.

    Retry model (per `.claude/skills/async`): the body is wrapped in
    `try/except`. A `FunctionalJobError` (invalid input / unknown namespace)
    is logged and returns an OK result — it is NOT retried. Any other
    (system/external/transient) failure propagates to the `backoff`
    decorator, which retries up to 3 times; on exhaustion `_on_giveup` logs
    and the handler returns (OK to the broker).

    Idempotency: a redelivered run re-reads the issue's *current* status
    fresh, so a `closed` ticket is always a safe no-op on replay. A
    redelivered `resolved`/`pending`/`ongoing` run may re-send a duplicate
    notification and mint an extra Cloud Task before this run's own new
    `escalation_task_id` is persisted — an accepted, signed-off deviation
    from strict once-only delivery, identical in nature and reasoning to
    `notify_down_time_update`'s documented non-dedupe decision (push
    delivery is already best-effort/at-least-once end-to-end, and Cloud
    Tasks' own per-task-name execution guarantee makes true duplicates rare
    in practice).

    Returns:
        A small result dict (`{status, ...}`) describing the outcome, which
        the worker route returns to the broker.
    """
    try:
        return _run_escalate_down_time(namespace_id, payload, job_id)
    except FunctionalJobError as e:
        logger.warning(
            f"escalate_down_time: functional failure (job_id={job_id}): {e}. "
            "Logged and acked — no retry."
        )
        return {
            "status": "skipped",
            "reason": str(e),
            "down_time_id": payload.get("down_time_id"),
        }


def _run_escalate_down_time(namespace_id: str, payload: dict, job_id: str) -> dict:
    """The actual work. Raises `FunctionalJobError` for invalid input /
    unknown tenant (caught and acked by `escalate_down_time`); lets any
    system/transient error propagate to the retry decorator."""
    if not namespace_id:
        raise FunctionalJobError("escalate_down_time: 'namespace_id' is required.")

    down_time_id = payload.get("down_time_id")
    if not down_time_id:
        raise FunctionalJobError("escalate_down_time: 'down_time_id' is required.")

    firestore = get_firestore_client()

    namespace = firestore.get_document(NAMESPACE_COLLECTION, namespace_id)
    if namespace is None:
        raise FunctionalJobError(
            f"escalate_down_time: no namespace '{namespace_id}' — refusing to "
            "escalate for an unknown tenant."
        )

    issue = firestore.get_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, down_time_id
    )
    # A missing issue (or one belonging to another tenant — a forged/stale
    # message, same guard as the sibling handlers) is the normal end of the
    # chain for a deleted ticket, not an error: stop, do not reschedule.
    if issue is None or issue.get("namespace_id") != namespace_id:
        logger.info(
            f"escalate_down_time: issue '{down_time_id}' not found in "
            f"namespace '{namespace_id}' (deleted?) — stopping the "
            "escalation chain without rescheduling."
        )
        return {"status": "stopped", "reason": "issue not found", "down_time_id": down_time_id}

    status = issue.get("status")

    if status == DownTimeStatus.CLOSED.value:
        # Terminal state, and the safety net if an earlier `cancel_escalation`
        # call (on close) failed to delete the pending task.
        firestore.update_subdocument(
            DOWN_TIME_COLLECTION,
            namespace_id,
            ISSUES_SUBCOLLECTION,
            down_time_id,
            {"escalation_task_id": None},
        )
        return {"status": "stopped", "reason": "closed", "down_time_id": down_time_id}

    if status not in (
        DownTimeStatus.RESOLVED.value,
        DownTimeStatus.PENDING.value,
        DownTimeStatus.ONGOING.value,
    ):
        # Unknown/unexpected status — fail closed, do not escalate or
        # reschedule on data we don't recognize.
        logger.warning(
            f"escalate_down_time: unexpected status '{status}' for issue "
            f"'{down_time_id}' in namespace '{namespace_id}' — stopping "
            "without rescheduling."
        )
        return {"status": "stopped", "reason": f"unexpected status '{status}'", "down_time_id": down_time_id}

    # Contain the whole recipient-lookup + fan-out + reschedule phase: a
    # transient Firestore blip here must not escape to the `backoff`
    # decorator — a retry would re-read the same (still unresolved) status
    # and re-notify everyone again, a silent duplicate-alert risk with no
    # corresponding benefit. Mirrors the containment `add_down_time` and
    # `notify_down_time_update` apply around their own notification phases.
    try:
        language = language_of(namespace)
        scope_source = {
            "production_scope": issue.get("down_time_scope"),
            "workstation_id": issue.get("workstation_id"),
            "production_line_id": issue.get("production_line_id"),
            "uap_id": issue.get("uap_id"),
        }
        location = resolve_location(firestore, namespace_id, namespace, scope_source, language)

        if status == DownTimeStatus.RESOLVED.value:
            _notify_production_agents_awaiting_confirmation(
                firestore, namespace_id, issue, namespace, language, location, down_time_id
            )
        else:  # pending / ongoing
            _notify_management(
                firestore, namespace_id, issue, namespace, language, location, down_time_id
            )

        _reschedule(firestore, namespace_id, namespace, issue, down_time_id)
    except Exception as e:
        logger.error(
            f"escalate_down_time: notification/reschedule phase failed for "
            f"issue '{down_time_id}' in namespace '{namespace_id}': {e}"
        )

    return {"status": "escalated", "down_time_status": status, "down_time_id": down_time_id}
