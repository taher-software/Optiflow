"""`notify_down_time_update` async job handler.

Notifies the relevant people when a downtime ticket ("issue") transitions
through its lifecycle: acknowledged, resolved, or rejected. Bilingual copy
per the namespace's `language` field (see `src.app.core.notifications`),
using the same tenant-scoped location resolution `add_down_time` uses (see
`src.app.async_jobs._common`).

Recipients per event:
  * `acknowledged` / `resolved` — the issue's `created_by`, unless the actor
    performing the transition IS the creator (never notify someone about
    their own action).
  * `rejected` — two groups: (1) `rejected_resolver_id` (the responder whose
    resolution was rejected), same self-skip rule against `actor_id`; and
    (2) every online agent of the issue's process (same recipient rule
    `_notify_process_agents` in `add_down_time` uses), told the downtime is
    still awaiting resolution and how long it has been open.

Deliberate, signed-off deviation from `.claude/skills/async` idempotency rule
("replaying the same `job_id` must cause no duplicate side effects"): this
handler does NOT dedupe a redelivery, and a second push to the same device is
a real, user-visible duplicate side effect (not merely cosmetic) — e.g. a
resolver could see "Production rejected your resolution" twice. The
deviation was accepted anyway, deliberately, because:
  * `_publish_down_time_update` (the trigger, in the api sub-factory) mints a
    fresh `job_id` on every publish call — `job_id` is per-publish, not
    per-logical-event, so it carries no dedupe value at any layer here even
    if this handler tried to key off it.
  * Push delivery is already at-least-once / best-effort end-to-end (Expo
    makes no delivery guarantee, and `core.push` is fire-and-forget), so a
    Firestore write added purely to dedupe this job's own redeliveries would
    buy little on top of that existing unreliability, at the cost of a write
    per notification. This handler writes nothing to Firestore (verified: no
    counters, no markers) and stays that way.
This is an accepted exception, not an oversight — do not "fix" it by adding
a dedupe write.

Trigger: published (job_type=`JobType.NOTIFY_DOWN_TIME_UPDATE`) by the
downtime-ticket lifecycle-transition endpoints (acknowledge / resolve /
reject), owned by the api sub-factory.
"""

from __future__ import annotations

import logging
from datetime import datetime

import backoff

from src.app.core.firestore import NAMESPACE_COLLECTION, USERS_COLLECTION
from src.app.core.notifications import format_duration, lifecycle_notification
from src.app.core.push import send_push_notifications
from src.app.core.timezone import namespace_timezone
from src.app.gcp import get_firestore_client
from src.app.globals.enum import Process, language_of

from ._common import DOWN_TIME_COLLECTION, ISSUES_SUBCOLLECTION, resolve_location
from .exceptions import FunctionalJobError

logger = logging.getLogger(__name__)

_VALID_EVENTS = {"acknowledged", "resolved", "rejected"}


def _notify_user(
    firestore, namespace_id: str, user_id: str, title: str, body: str, down_time_id: str, event: str
) -> None:
    """Best-effort push to a single user by id. No-op if the user doesn't
    exist, belongs to another tenant (forged/stale message guard, same as
    `add_down_time`), or has no push token."""
    user = firestore.get_document(USERS_COLLECTION, user_id)
    if not user or user.get("namespace_id") != namespace_id:
        return
    token = user.get("push_token")
    if not token:
        logger.info(
            f"notify_down_time_update: user '{user_id}' has no push token to "
            f"notify for issue '{down_time_id}'."
        )
        return

    send_push_notifications(
        [token], title=title, body=body, data={"down_time_id": down_time_id, "event": event}
    )


def _notify_process_agents(
    firestore,
    namespace_id: str,
    process: Process,
    title: str,
    body: str,
    down_time_id: str,
    exclude_user_ids: frozenset[str] = frozenset(),
) -> None:
    """Best-effort push notification to every online agent of the given
    process (e.g. "maintenance agent") in this namespace — same recipient
    rule as `add_down_time._notify_process_agents`, plus `exclude_user_ids`
    (the users already notified individually for this event, e.g. the actor
    who performed the transition, or the rejected resolver): "never notify
    someone about their own action" applies to the fan-out too, and a
    resolver who is also a process agent must get exactly one push (the
    resolver-specific copy), not that one plus the fan-out copy."""
    role = f"{process.value} agent"

    users = firestore.find_documents(
        USERS_COLLECTION, {"namespace_id": namespace_id, "role": role}
    )
    # Absent `online` defaults to True (documented default: users may not
    # have this field yet, schemaless collection).
    online_users = [
        u
        for u in users
        if u.get("online", True) and u.get("id") not in exclude_user_ids
    ]
    tokens = [u["push_token"] for u in online_users if u.get("push_token")]

    if not tokens:
        logger.info(
            f"notify_down_time_update: no online '{role}' with a push token "
            f"to notify in namespace '{namespace_id}' for issue "
            f"'{down_time_id}'."
        )
        return

    send_push_notifications(
        tokens,
        title=title,
        body=body,
        data={"down_time_id": down_time_id, "process": process.value, "event": "rejected"},
    )


def _elapsed_duration_string(
    issue: dict, namespace: dict | None, namespace_id: str, language
) -> str | None:
    """Best-effort elapsed-time-since-`created_at` string for the
    rejected/process-agents copy. Returns None (never raises) when
    `created_at` is missing or unparsable, so the caller can fall back to a
    durationless variant rather than ever rendering "None"."""
    created_at = issue.get("created_at")
    if not created_at:
        return None
    try:
        created = datetime.fromisoformat(created_at)
    except (TypeError, ValueError):
        logger.warning(
            f"notify_down_time_update: unparsable 'created_at' "
            f"'{created_at}' for issue in namespace '{namespace_id}', "
            "omitting duration."
        )
        return None

    tz = namespace_timezone(namespace_id, namespace)
    if created.tzinfo is None:
        created = created.replace(tzinfo=tz)
    now = datetime.now(tz)
    elapsed_seconds = (now - created).total_seconds()
    return format_duration(elapsed_seconds, language)


def _on_giveup(details: dict) -> None:
    """Log when a job exhausts its retries. `raise_on_giveup=False` means the
    handler then returns normally, so the worker route still acks OK to the
    broker (a job that keeps failing must not be requeued forever)."""
    logger.error(
        f"notify_down_time_update: gave up after {details.get('tries')} "
        f"attempt(s): {details.get('exception')}"
    )


@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=3,
    on_giveup=_on_giveup,
    raise_on_giveup=False,
)
def notify_down_time_update(namespace_id: str, payload: dict, job_id: str) -> dict:
    """
    Notify the relevant people about a downtime-ticket lifecycle transition.

    Retry model (per `.claude/skills/async`): the body is wrapped in
    `try/except`. A `FunctionalJobError` (invalid input, unknown namespace,
    unknown issue) is logged and returns an OK result — it is NOT retried.
    Any other (system/external/transient) failure propagates to the
    `backoff` decorator, which retries up to 3 times; on exhaustion
    `_on_giveup` logs and the handler returns (OK to the broker).

    Returns:
        A small result dict (`{status, ...}`) describing the outcome, which
        the worker route returns to the broker.
    """
    try:
        return _run_notify_down_time_update(namespace_id, payload, job_id)
    except FunctionalJobError as e:
        logger.warning(
            f"notify_down_time_update: functional failure (job_id={job_id}): "
            f"{e}. Logged and acked — no retry."
        )
        return {
            "status": "skipped",
            "reason": str(e),
            "down_time_id": payload.get("down_time_id"),
        }


def _run_notify_down_time_update(namespace_id: str, payload: dict, job_id: str) -> dict:
    """The actual work. Raises `FunctionalJobError` for invalid input /
    unknown tenant / unknown issue (caught and acked by
    `notify_down_time_update`); lets any system/transient error propagate to
    the retry decorator."""
    if not namespace_id:
        raise FunctionalJobError("notify_down_time_update: 'namespace_id' is required.")
    if not job_id:
        raise FunctionalJobError("notify_down_time_update: 'job_id' is required.")

    down_time_id = payload.get("down_time_id")
    event = payload.get("event")
    actor_id = payload.get("actor_id")

    if not down_time_id:
        raise FunctionalJobError("notify_down_time_update: 'down_time_id' is required.")
    if event not in _VALID_EVENTS:
        raise FunctionalJobError(
            f"notify_down_time_update: invalid 'event' value '{event}'."
        )
    if not actor_id:
        raise FunctionalJobError("notify_down_time_update: 'actor_id' is required.")

    firestore = get_firestore_client()

    # The namespace must exist — never act on a forged/stale job message
    # paired with an unknown tenant (same guard as `add_down_time`).
    namespace = firestore.get_document(NAMESPACE_COLLECTION, namespace_id)
    if namespace is None:
        raise FunctionalJobError(
            f"notify_down_time_update: no namespace '{namespace_id}' — "
            "refusing to notify for an unknown tenant."
        )

    issue = firestore.get_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, down_time_id
    )
    # Tenant-scope guard: the worker route is unauthenticated at the app
    # layer, so a forged/stale message could pair this tenant's namespace_id
    # with another tenant's issue id.
    if issue is None or issue.get("namespace_id") != namespace_id:
        raise FunctionalJobError(
            f"notify_down_time_update: no issue '{down_time_id}' in "
            f"namespace '{namespace_id}'."
        )

    # Contain the whole recipient-lookup + fan-out phase: this job writes
    # nothing, so a transient Firestore blip here must not escape to the
    # `backoff` decorator — a retry would just recompute and re-send the same
    # best-effort notifications, which is a silent duplicate-push risk with
    # no corresponding benefit (mirrors the containment
    # `add_down_time._run_add_down_time` applies around its own notification
    # phase, and the same reasoning: log and move on).
    try:
        language = language_of(namespace)
        scope_source = {
            "production_scope": issue.get("down_time_scope"),
            "workstation_id": issue.get("workstation_id"),
            "production_line_id": issue.get("production_line_id"),
            "uap_id": issue.get("uap_id"),
        }
        location = resolve_location(firestore, namespace_id, namespace, scope_source, language)
        created_by = issue.get("created_by")

        if event in ("acknowledged", "resolved"):
            if created_by and created_by != actor_id:
                title, body = lifecycle_notification(event, language, location)
                _notify_user(
                    firestore, namespace_id, created_by, title, body, down_time_id, event
                )
        else:  # event == "rejected"
            resolver_id = payload.get("rejected_resolver_id")
            if resolver_id and resolver_id != actor_id:
                title, body = lifecycle_notification(
                    "rejected_resolver", language, location
                )
                _notify_user(
                    firestore, namespace_id, resolver_id, title, body, down_time_id, event
                )

            try:
                process = Process(issue.get("process"))
            except ValueError:
                process = None

            if process is not None:
                duration = _elapsed_duration_string(issue, namespace, namespace_id, language)
                variant = "rejected_agents" if duration else "rejected_agents_generic"
                title, body = lifecycle_notification(
                    variant, language, location, duration=duration
                )
                # Never notify the actor about their own action, and never
                # double-notify a resolver who is also a process agent (they
                # already got the `rejected_resolver` copy above).
                exclude_user_ids = frozenset(
                    uid for uid in (actor_id, resolver_id) if uid
                )
                _notify_process_agents(
                    firestore,
                    namespace_id,
                    process,
                    title,
                    body,
                    down_time_id,
                    exclude_user_ids=exclude_user_ids,
                )
    except Exception as e:
        logger.error(
            f"notify_down_time_update: notification phase failed for issue "
            f"'{down_time_id}' in namespace '{namespace_id}': {e}"
        )

    return {"status": "notified", "down_time_id": down_time_id, "event": event}
