"""`add_down_time` async job handler.

Declares a new downtime ticket ("issue") under
`down_time/{namespace_id}/issues/{job_id}` and notifies the online process
agents (e.g. "maintenance agent") responsible for it via push notification.
Notification copy is bilingual (en/fr, per the namespace's `language` field)
and specialized per `DownTimeType` — see `src.app.core.notifications`.
Unknown-cause (`DownTimeType.OTHERS`) tickets additionally alert every
production supervisor in the namespace (push + email). Both channels are
attempted per recipient; a single failing recipient never stops the rest of
the fan-out, but if a channel fails for EVERY recipient it was attempted for,
`_notify_production_supervisors` raises `SystemJobError` naming the failed
channel(s). Finally, when the ticket matches the escalation policy
(`src.app.core.escalation`), schedules the FIRST escalation cycle via the
shared `_common.schedule_escalation_cycle(..., escalation_number=1)` — see
its docstring for the deterministic Cloud Task id (`f"{job_id}-1"`) and the
write-on-success-only rule (the issue is only updated with
`escalation_task_id` once the Cloud Task actually exists). `escalate_down_time`
then re-evaluates and reschedules itself per the namespace's configured
escalation delay (`NamespaceSettings.time_to_escalate`, defaulting to 1800s —
see `_common._resolve_escalation_delay`) until the ticket closes.

**Shift assignment.** When the namespace's `NamespaceSettings` doc has
`shift_number > 1`, the newly created issue is stamped with `shift` — the
1-based shift number (`shift_1`/`shift_2`/`shift_3` windows) whose
`[start_time, end_time)` contains the creation moment in the namespace's
local time, or `None` for a gap between configured windows. See
`_resolve_shift` (pure, unit-testable) for the midnight-wrap handling. A
single-shift namespace (no settings doc, or `shift_number` missing/<=1) gets
no `shift` key at all — this is a purely additive, backward-compatible
change to the issue document shape.

**The notification/escalation phase is NOT contained.** Any failure there —
including a total push/email failure surfaced by `_notify_production_supervisors`
as `SystemJobError` — propagates all the way out to `add_down_time`'s own
`backoff` decorator, which retries the whole run up to `max_tries` (3). This
mirrors the decision already made for `escalate_down_time` (see that
module's docstring for why containment there was wrong).

**Idempotency guard is first-attempt-only, on purpose.** The issue document
is created once, then the SAME `job_id`/delivery may re-enter this handler
either because `backoff` is retrying in-process (the notification phase
failed) or because the broker genuinely redelivered the message (at-least-
once delivery, after this handler already fully succeeded earlier). Both
cases see the issue document already existing — but they must be treated
differently, or a `backoff` retry would be swallowed by the very guard it
needs to get past. `add_down_time` tracks a per-invocation attempt counter
(created fresh on every call — never module-level, which would leak across
concurrent jobs/tests) and threads it down to `_run_add_down_time` as
`is_first_attempt`. The guard then branches on it: first attempt + exists ->
genuine redelivery, skip; retry + exists -> we wrote it earlier in this same
call, fall through and re-run notifications without re-creating the issue
(`create_subdocument` still fires exactly once per delivery).

**Accepted consequence:** because a total notification failure now genuinely
retries the whole handler, a recipient already reached in an earlier,
partial fan-out may be notified again on a retry. That is a deliberate
trade — a duplicate downtime alert beats a silently undelivered one — and it
matches the decision already recorded in `escalate_down_time`.

Escalation scheduling sits in the same (now-retryable) phase and needs no
special handling to be safe to re-run: `_common.schedule_escalation_cycle`
derives a deterministic Cloud Task id from `escalation_number` (always the
literal `1` here), so a retry lands on the same id and
`schedule_escalation` reports `already_existed=True` without writing to
Firestore again — see that function's docstring.

**A giveup after exhausting all retries must still return a meaningful
result**, never `None` (see `routers/workers/modelsOut.py`, which the worker
route feeds the handler's return value into): `add_down_time` re-checks
whether the issue document exists and reports `created_notifications_failed`
(ticket exists, notifications never fully succeeded) rather than a clean
`created`, or `failed` in the unlikely case ticket creation itself never
completed.

Trigger: published (job_type=`JobType.ADD_DOWN_TIME`) by the downtime-ticket
creation endpoint (owned by the api sub-factory) once a workstation/line/UAP
stop is declared.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import backoff

from src.app.core.email import send_down_time_supervisor_email
from src.app.core.escalation import should_escalate
from src.app.core.firestore import (
    NAMESPACE_COLLECTION,
    USERS_COLLECTION,
)
from src.app.core.notifications import agent_notification, supervisor_notification
from src.app.core.push import PushDeliveryError, send_push_notifications
from src.app.core.timezone import namespace_timezone
from src.app.gcp import get_firestore_client
from src.app.globals.enum import (
    DOWNTIME_TYPE_PROCESS,
    DownTimeStatus,
    DownTimeType,
    Language,
    Process,
    ProductionScope,
    Role,
    language_of,
)

from ._common import (
    DOWN_TIME_COLLECTION,
    ISSUES_SUBCOLLECTION,
    read_namespace_settings,
    resolve_location,
    resolve_scope_document,
    schedule_escalation_cycle,
)
from .exceptions import FunctionalJobError, SystemJobError
from src.app.core.shift_time import parse_hhmm as _parse_hhmm

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = (
    "created_by",
    "production_scope",
    "down_time_type",
)




def _resolve_shift(settings: dict | None, now_local: datetime) -> Optional[int]:
    """Which shift (1/2/3) the given local moment falls into, per the
    namespace's `NamespaceSettings` doc — pure function, no I/O, so it's
    trivially unit-testable.

    Returns `None` when `settings` is falsy or `shift_number <= 1` — the
    caller then must NOT add a `shift` key at all (single-shift namespaces
    behave exactly as before this feature existed). When `shift_number > 1`,
    returns the matched shift number, or `None` for a genuine gap (no
    configured `shift_i` window contains `now_local`) — that `None` IS
    meaningful in that case and the caller stores it.

    Each `shift_i` window is `{"start_time": "HH:MM", "end_time": "HH:MM"}`.
    A window where `end <= start` wraps past midnight (e.g. 22:00-06:00) and
    covers `[start, 1440) u [0, end)`; otherwise it covers `[start, end)`.
    An unparsable/malformed "HH:MM" value is logged at warning and treated
    as no-match for that shift — a bad settings value must never break
    ticket creation.
    """
    if not settings:
        return None
    shift_number = settings.get("shift_number")
    if not isinstance(shift_number, int) or shift_number <= 1:
        return None

    now_minutes = now_local.hour * 60 + now_local.minute

    for i in range(1, shift_number + 1):
        window = settings.get(f"shift_{i}")
        if not window:
            continue
        try:
            start = _parse_hhmm(window["start_time"])
            end = _parse_hhmm(window["end_time"])
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(
                f"_resolve_shift: unparsable shift_{i} window {window!r}: {e}. "
                "Treating as no-match."
            )
            continue

        if start == end:
            # Zero-length window (misconfiguration): match nothing rather than
            # silently covering the whole day and masking later shifts. The
            # write schema also forbids equal start/end, so this is defense in
            # depth over raw Firestore data.
            continue
        if end < start:  # wraps past midnight
            if now_minutes >= start or now_minutes < end:
                return i
        else:
            if start <= now_minutes < end:
                return i

    return None


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


def _notify_process_agents(
    firestore,
    namespace_id: str,
    down_time_type: DownTimeType,
    process: Process,
    language: Language,
    location: str,
    job_id: str,
) -> None:
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

    title, body = agent_notification(down_time_type, process, language, location)
    send_push_notifications(
        tokens,
        title=title,
        body=body,
        data={"down_time_id": job_id, "process": process.value},
    )


def _notify_production_supervisors(
    firestore, namespace_id: str, language: Language, location: str, job_id: str
) -> None:
    """Alert (push + email) every production supervisor in the namespace for
    an unknown-cause (`DownTimeType.OTHERS`) ticket.

    Deliberately notifies ALL production supervisors regardless of the
    `online` field — unlike `_notify_process_agents`, this alert must reach
    them even when offline (product decision; do not "fix" this to match the
    agent online-filter).

    Both channels are always attempted, in order (push then email), even if
    the push channel fails completely: a push failure is caught here and
    remembered rather than left to propagate, so it can never skip the email
    loop. Per-recipient email sends stay individually best-effort — one bad
    address must never stop the rest of the fan-out. Only once BOTH channels
    have been fully attempted does this function raise `SystemJobError`, and
    only if a channel that had at least one recipient failed for ALL of its
    recipients — naming which channel(s) failed in the message.

    This function's `SystemJobError` is NOT contained at its call site (see
    this module's docstring): it propagates out of `_run_add_down_time` to
    `add_down_time`'s own `backoff` decorator and IS retried, up to
    `max_tries`."""
    supervisors = firestore.find_documents(
        USERS_COLLECTION,
        {"namespace_id": namespace_id, "role": Role.PRODUCTION_SUPERVISOR.value},
    )

    title, body = supervisor_notification(language, location)
    data = {"down_time_id": job_id, "process": Process.PRODUCTION.value}

    tokens = [u["push_token"] for u in supervisors if u.get("push_token")]
    push_failed = False
    try:
        send_push_notifications(tokens, title=title, body=body, data=data)
    except PushDeliveryError as e:
        push_failed = True
        logger.warning(
            f"add_down_time: push notification to production supervisors "
            f"totally failed for issue '{job_id}' in namespace "
            f"'{namespace_id}': {e}"
        )

    recipients_with_email = 0
    email_failures = 0
    for supervisor in supervisors:
        email = supervisor.get("email")
        if not email:
            continue
        recipients_with_email += 1
        try:
            send_down_time_supervisor_email(email, language, location)
        except Exception as e:
            email_failures += 1
            # Best-effort per-recipient: one bad address doesn't skip the
            # rest of the fan-out. Log the user id, not the email address —
            # PII must not land in the log sink.
            logger.warning(
                f"add_down_time: failed to send supervisor email to user "
                f"'{supervisor.get('id')}' for issue '{job_id}': {e}"
            )

    email_totally_failed = (
        recipients_with_email > 0 and email_failures == recipients_with_email
    )

    if push_failed or email_totally_failed:
        failed_channels = [
            name
            for name, failed in (("push", push_failed), ("email", email_totally_failed))
            if failed
        ]
        raise SystemJobError(
            "add_down_time: total notification failure for production "
            f"supervisors on issue '{job_id}' — channel(s) failed entirely: "
            f"{', '.join(failed_channels)}."
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
def _add_down_time_attempt(namespace_id: str, payload: dict, job_id: str, attempt: dict) -> dict | None:
    """One `backoff`-retried attempt. `attempt` is a small mutable dict
    (`{"count": ...}`) owned and created fresh by `add_down_time` for this
    invocation, threaded through here by closure so it survives across
    `backoff`'s in-process retries but never leaks to a different call (see
    module docstring). Incremented once per attempt, including retries, so
    `_run_add_down_time` can tell "first attempt of this delivery" from "a
    retry re-entering the same delivery".

    Wrapped in `try/except` exactly per `.claude/skills/async`:
    `FunctionalJobError` is caught HERE, inside the decorated function —
    before `backoff`'s own `except Exception` would ever see it — so it is
    logged and acked, never retried. Any other exception propagates out to
    the decorator."""
    attempt["count"] += 1
    try:
        return _run_add_down_time(
            namespace_id, payload, job_id, is_first_attempt=attempt["count"] == 1
        )
    except FunctionalJobError as e:
        logger.warning(
            f"add_down_time: functional failure (job_id={job_id}): {e}. "
            "Logged and acked — no retry."
        )
        return {"status": "skipped", "reason": str(e), "down_time_id": job_id}


def add_down_time(namespace_id: str, payload: dict, job_id: str) -> dict:
    """
    Declare a new downtime ticket and notify the responsible process agents.

    Retry model (per `.claude/skills/async`): `FunctionalJobError` (invalid
    input / business rule) is logged and returns an OK result — it is NOT
    retried. Any other (system/external/transient) failure — including a
    total notification failure — propagates to the `backoff` decorator on
    `_add_down_time_attempt`, which retries up to 3 times; on exhaustion
    `_on_giveup` logs and the handler still returns a meaningful dict (never
    `None`) to the broker. The handler is idempotent (keyed on `job_id`),
    with a first-attempt-only guard — see the module docstring and
    `_run_add_down_time`.

    Returns:
        A small result dict (`{status, ...}`) describing the outcome, which the
        worker route returns to the broker.
    """
    # Per-invocation attempt counter — created FRESH on every call (never
    # module-level state, which would leak across concurrent jobs/tests).
    attempt = {"count": 0}
    result = _add_down_time_attempt(namespace_id, payload, job_id, attempt)

    if result is not None:
        return result

    # `raise_on_giveup=False` means `_add_down_time_attempt` returned `None`
    # after `backoff` exhausted all `max_tries` retries. The worker route
    # must still receive a meaningful dict (see `routers/workers/modelsOut.py`)
    # — re-check whether the issue document exists to report accurately. The
    # expected case is that ticket creation succeeded on the first attempt
    # and only the notification phase kept failing; `failed` covers the
    # unlikely case where even ticket creation itself never completed.
    firestore = get_firestore_client()
    existing = firestore.get_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, job_id
    )
    if existing is not None:
        return {
            "status": "created_notifications_failed",
            "reason": "notification phase failed after all retries",
            "down_time_id": job_id,
        }
    return {
        "status": "failed",
        "reason": "ticket creation failed after all retries",
        "down_time_id": job_id,
    }


def _run_add_down_time(
    namespace_id: str, payload: dict, job_id: str, is_first_attempt: bool
) -> dict:
    """The actual work. Raises `FunctionalJobError` for invalid input /
    business-rule violations (caught and acked by `_add_down_time_attempt`);
    lets any system/transient error propagate to the retry decorator —
    including from the notification phase (see module docstring: it is NOT
    contained)."""
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

    # --- Idempotency guard. `existing is not None` means the issue document
    # was already written — but that means two DIFFERENT things depending on
    # `is_first_attempt` (see module docstring for the full rationale):
    #   * first attempt + exists -> a genuine broker redelivery of an
    #     already-fully-processed ticket (at-least-once delivery). Skip.
    #   * retry (not first attempt) + exists -> WE wrote this document on an
    #     earlier attempt of THIS SAME call, then the notification phase
    #     failed and `backoff` re-entered. Do NOT skip: fall through and
    #     re-run the notification phase against the already-written issue,
    #     without re-creating it (`create_subdocument` still fires exactly
    #     once per delivery, however many attempts it takes).
    existing = firestore.get_subdocument(
        DOWN_TIME_COLLECTION, namespace_id, ISSUES_SUBCOLLECTION, job_id
    )
    if existing is not None and is_first_attempt:
        logger.info(
            f"add_down_time: issue '{job_id}' already exists in namespace "
            f"'{namespace_id}', skipping (idempotent replay)."
        )
        return {"status": "skipped", "reason": "already processed", "down_time_id": job_id}

    if existing is None:
        try:
            down_time_type = DownTimeType(payload["down_time_type"])
        except ValueError as e:
            raise FunctionalJobError(
                f"add_down_time: invalid 'down_time_type' value "
                f"'{payload.get('down_time_type')}'."
            ) from e

        process = _resolve_process(down_time_type, payload.get("department"))
    else:
        logger.info(
            f"add_down_time: issue '{job_id}' already exists in namespace "
            f"'{namespace_id}' — retry of the same delivery (not the first "
            "attempt), re-running the notification phase without "
            "re-creating the issue."
        )
        down_time_type = DownTimeType(existing["down_time_type"])
        process = Process(existing["process"])

    # The namespace must exist — never create a downtime issue under an unknown
    # tenant (guards against forged/stale job messages writing orphan
    # `down_time/{namespace_id}` subcollections).
    namespace = firestore.get_document(NAMESPACE_COLLECTION, namespace_id)
    if namespace is None:
        raise FunctionalJobError(
            f"add_down_time: no namespace '{namespace_id}' — refusing to create "
            "a downtime for an unknown tenant."
        )

    # Namespace settings (shift schedule + escalation delay) — read once,
    # best-effort (never raises: a settings-read blip must not fail ticket
    # creation, a purely additive feature). Used for shift assignment on the
    # create path below, and reused for the escalation delay further down on
    # BOTH the create and idempotent-replay paths, so the same doc is never
    # read twice in one run.
    settings = read_namespace_settings(firestore, namespace_id)

    if existing is None:
        tz = namespace_timezone(namespace_id, namespace)
        now_iso = datetime.now(tz).isoformat()

        is_setup_changeover = down_time_type == DownTimeType.SETUP_CHANGEOVER

        # §9.5/W5 (kpi-scope-spread, revision 2) — `CreateDownTimeIn` refuses
        # `plant` + a sub-location id at the HTTP boundary, but this handler
        # is also reachable directly by the (unauthenticated-by-design)
        # worker route, recopying whatever the payload says with no
        # revalidation. Enforce the §8 invariant here too: NEUTRALISE (never
        # reject) a forbidden combination by forcing the three sub-location
        # ids to `None` on the stored document, and log a warning naming the
        # ticket — a real downtime event must never be lost to a malformed
        # payload.
        uap_id = payload.get("uap_id")
        production_line_id = payload.get("production_line_id")
        workstation_id = payload.get("workstation_id")
        if payload["production_scope"] == ProductionScope.PLANT.value and (
            uap_id or production_line_id or workstation_id
        ):
            logger.warning(
                f"add_down_time: ticket '{job_id}' declared 'plant' scope but "
                "carried a sub-location id (uap_id/production_line_id/"
                "workstation_id) — forcing all three to None per the §8 "
                "invariant."
            )
            uap_id = production_line_id = workstation_id = None

        issue_data = {
            "id": job_id,
            "namespace_id": namespace_id,
            "created_at": now_iso,
            "updated_at": now_iso,
            "down_time_scope": payload["production_scope"],
            "uap_id": uap_id,
            "production_line_id": production_line_id,
            "workstation_id": workstation_id,
            "down_time_type": payload["down_time_type"],
            "department": payload.get("department") if is_setup_changeover else None,
            "process": process.value,
            "status": DownTimeStatus.PENDING.value,
            "created_by": payload["created_by"],
        }

        # Shift assignment — best-effort, namespace-settings-driven. A
        # single-shift namespace (no settings doc, or `shift_number` missing
        # / <= 1) behaves exactly as before this feature: no `shift` key at
        # all. Only a multi-shift namespace (`shift_number > 1`) gets one,
        # even when the moment falls in a gap between configured windows
        # (`_resolve_shift` returns `None` for that case, and we still store
        # it — `None` there is meaningful, distinct from "not applicable").
        shift_number = (settings or {}).get("shift_number")
        if isinstance(shift_number, int) and shift_number > 1:
            issue_data["shift"] = _resolve_shift(settings, datetime.now(tz))

        firestore.create_subdocument(
            DOWN_TIME_COLLECTION,
            namespace_id,
            ISSUES_SUBCOLLECTION,
            issue_data,
            document_id=job_id,
        )
    else:
        issue_data = existing

    # Notification phase — NOT contained (see module docstring): any failure
    # here, including a total push/email failure surfaced by
    # `_notify_production_supervisors` as `SystemJobError`, propagates
    # straight out to `add_down_time`'s own `backoff` decorator, which
    # retries the whole run up to `max_tries`. Accepted consequence: a
    # recipient already reached in an earlier, partial attempt may be
    # notified again on a retry — a duplicate alert beats a silently
    # undelivered one (same trade already made for `escalate_down_time`).
    language = language_of(namespace)
    # `resolve_scope_document`/`resolve_location` need `production_scope` /
    # `workstation_id` / `production_line_id` / `uap_id` keys. The raw
    # payload has them directly; the already-written issue document stores
    # `down_time_scope` instead of `production_scope` — adapt it (see
    # `_common.resolve_scope_document`'s docstring for this exact shape).
    scope_source = (
        payload
        if existing is None
        else {
            "production_scope": issue_data.get("down_time_scope"),
            "workstation_id": issue_data.get("workstation_id"),
            "production_line_id": issue_data.get("production_line_id"),
            "uap_id": issue_data.get("uap_id"),
        }
    )
    # Fetched once and reused for both the location label and the escalation
    # check below (only a `work station`-scoped ticket needs it for
    # `should_escalate`) — avoid reading the same document twice.
    scope_doc = resolve_scope_document(firestore, namespace_id, scope_source)
    location = resolve_location(
        firestore, namespace_id, namespace, scope_source, language, doc=scope_doc
    )

    _notify_process_agents(
        firestore, namespace_id, down_time_type, process, language, location, job_id
    )

    if down_time_type is DownTimeType.OTHERS:
        _notify_production_supervisors(
            firestore, namespace_id, language, location, job_id
        )

    workstation = (
        scope_doc
        if scope_source["production_scope"] == ProductionScope.WORK_STATION.value
        else None
    )
    if should_escalate(issue_data, workstation):
        # Cycle 1 via the shared composition (`_common.schedule_escalation_cycle`,
        # also used by `escalate_down_time` for every later cycle — see its
        # docstring for the deterministic-id contract and the
        # write-on-success-only rule). Safe to re-run on a retry: the
        # deterministic `task_id` (`f"{job_id}-1"`, derived only from the
        # retry-invariant literal `1`) makes a repeat collapse into
        # `already_existed=True` with no duplicate Firestore write.
        schedule_escalation_cycle(
            firestore, namespace_id, namespace, job_id, 1, settings=settings
        )

    return {"status": "created", "down_time_id": job_id}
