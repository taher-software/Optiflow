"""Shared helpers for downtime async job handlers (see `.claude/skills/async`).

Extracted out of `add_down_time` so `notify_down_time_update` does not
duplicate tenant-scoped location resolution — there must be exactly one
implementation, imported by every handler that needs it. This module owns
that location resolution plus the `down_time`/`issues` collection constants.

Also owns `schedule_escalation_cycle` — the composition (deterministic task
id + `schedule_escalation` call + issue bookkeeping write) both
`add_down_time` (first cycle) and `escalate_down_time` (every subsequent
cycle) need identically. It lives here rather than in `core/escalation.py`
because it does Firestore I/O and is a higher-level composition, not a pure
policy/primitive — `core/escalation.py` stays `should_escalate` +
`schedule_escalation` (the primitive Cloud Task creation call) only. Two
copies of this composition is exactly the drift pattern that already cost
this codebase twice (`resolve_location`, then an earlier retry wrapper) —
there must be exactly one implementation.

Namespace-timezone resolution does NOT live here: it moved to
`src.app.core.timezone.namespace_timezone`, the single shared implementation
used by both the sync API layer and this async job layer (`core/` is the
neutral home either side may import without crossing the sync/async
boundary). Import it directly from there rather than re-exporting it here.
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.app.core.escalation import ESCALATION_DELAY_SECONDS, schedule_escalation
from src.app.core.firestore import (
    NAMESPACE_SETTINGS_COLLECTION,
    PRODUCTION_LINE_COLLECTION,
    SETTINGS_SUBCOLLECTION,
    UAP_COLLECTION,
    WORKSTATION_COLLECTION,
)
from src.app.core.timezone import namespace_timezone
from src.app.globals.enum import Language, ProductionScope

logger = logging.getLogger(__name__)

DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"

_FALLBACK_LOCATION = {Language.EN: "the plant", Language.FR: "l'usine"}

# Sentinel distinguishing "no pre-fetched doc was passed" from "the caller
# already looked it up and it's None" (e.g. scope isn't `work station`, or
# the document doesn't exist) — see `resolve_location`'s `doc` parameter.
_UNRESOLVED = object()


def resolve_scope_document(
    firestore, namespace_id: str, scope_source: dict
) -> dict | None:
    """Best-effort, tenant-scoped fetch of the Firestore document backing a
    downtime ticket's production scope (the workstation / production line /
    UAP document), or `None` when the scope has no such document (`plant`),
    the referenced document doesn't exist, or it belongs to another tenant.
    Never raises.

    `scope_source` must carry the same keys `add_down_time`'s payload does:
    `production_scope` plus whichever of `workstation_id` /
    `production_line_id` / `uap_id` applies. Callers reading an already
    written issue document (rather than the raw creation payload) adapt its
    fields (`down_time_scope` -> `production_scope`, etc.) into this shape.

    Extracted out of `resolve_location` so a caller that also needs the raw
    document (e.g. `add_down_time` evaluating the escalation policy against
    the workstation's `type`) can fetch it exactly once and pass it to both,
    rather than reading it twice.
    """
    try:
        scope = scope_source.get("production_scope")
        doc = None
        if scope == ProductionScope.WORK_STATION.value and scope_source.get("workstation_id"):
            doc = firestore.get_document(
                WORKSTATION_COLLECTION, scope_source["workstation_id"]
            )
        elif scope == ProductionScope.PRODUCTION_LINE.value and scope_source.get(
            "production_line_id"
        ):
            doc = firestore.get_document(
                PRODUCTION_LINE_COLLECTION, scope_source["production_line_id"]
            )
        elif scope == ProductionScope.UAP.value and scope_source.get("uap_id"):
            doc = firestore.get_document(UAP_COLLECTION, scope_source["uap_id"])

        # The worker route is unauthenticated at the app layer, so a job
        # message could pair an attacker's `namespace_id` with a victim
        # tenant's document id. Never surface another tenant's document.
        if doc and doc.get("namespace_id") != namespace_id:
            doc = None

        return doc
    except Exception as e:  # never let a scope-document lookup fail the caller
        logger.warning(
            f"resolve_scope_document: failed to resolve scope document "
            f"(namespace='{namespace_id}'): {e}"
        )
        return None


def resolve_location(
    firestore,
    namespace_id: str,
    namespace: dict | None,
    scope_source: dict,
    language: Language,
    doc: dict | None = _UNRESOLVED,
) -> str:
    """Best-effort human-readable location label for a downtime ticket, from
    its production scope. Reads the relevant Firestore document's `name`
    field. Never raises — falls back to the namespace `company_name`, then to
    a generic "the plant" / "l'usine" label, so a missing/renamed document
    never blocks the caller.

    `scope_source` — see `resolve_scope_document`.

    `doc`: optional pre-fetched scope document (from `resolve_scope_document`)
    to reuse instead of fetching it again — pass this when the caller already
    needed the raw document for something else. Leave unset (the default) to
    have this function fetch it itself, as before.
    """
    doc = resolve_scope_document(firestore, namespace_id, scope_source) if doc is _UNRESOLVED else doc

    name = (doc or {}).get("name") if doc else None
    if name:
        return name

    company_name = (namespace or {}).get("company_name")
    if company_name:
        return company_name
    return _FALLBACK_LOCATION[language]


# Sentinel distinguishing "settings arg not supplied" (read it) from an
# explicitly-passed `None` (a caller that already read it and found none).
_SETTINGS_UNSET: object = object()


def read_namespace_settings(firestore, namespace_id: str):
    """Best-effort read of `NamespaceSettings/{namespace_id}/settings/
    {namespace_id}`. Returns the settings dict, or `None` when the subdoc
    doesn't exist OR the read itself raises. NEVER raises — a settings lookup
    is purely additive and must never block ticket creation or escalation
    scheduling. The single shared reader both the shift-assignment and the
    escalation-delay paths use, so the never-raise guard lives in one place."""
    try:
        return firestore.get_subdocument(
            NAMESPACE_SETTINGS_COLLECTION,
            namespace_id,
            SETTINGS_SUBCOLLECTION,
            namespace_id,
        )
    except Exception as e:  # settings lookup must never block the caller
        logger.warning(
            f"read_namespace_settings: failed to read settings for namespace "
            f"'{namespace_id}': {e}. Treating as no settings."
        )
        return None


def _resolve_escalation_delay_from_settings(settings: dict | None) -> int:
    """Pure resolve of the escalation delay (seconds) from an already-read
    settings dict. Defaults to `ESCALATION_DELAY_SECONDS` when `settings` is
    `None`, or `time_to_escalate` is missing/`None`/not a positive int (a
    `bool` is rejected — `True`/`False` are `int` subclasses)."""
    delay = (settings or {}).get("time_to_escalate")
    if isinstance(delay, bool) or not isinstance(delay, int) or delay <= 0:
        return ESCALATION_DELAY_SECONDS
    return delay


def _resolve_escalation_delay(firestore, namespace_id: str) -> int:
    """Best-effort read + resolve of the namespace's configured
    `time_to_escalate` (seconds). Thin wrapper over `read_namespace_settings`
    + `_resolve_escalation_delay_from_settings`, for callers that only have
    `(firestore, namespace_id)` and haven't already read the settings doc.
    Never raises, never blocks scheduling on a bad/absent value."""
    return _resolve_escalation_delay_from_settings(
        read_namespace_settings(firestore, namespace_id)
    )


def schedule_escalation_cycle(
    firestore,
    namespace_id: str,
    namespace: dict | None,
    down_time_id: str,
    escalation_number: int,
    settings=_SETTINGS_UNSET,
) -> str | None:
    """Schedule one escalation cycle (`escalation_number`, the cycle being
    scheduled — NOT the one that just ran) and, only on success, persist its
    bookkeeping on the issue. The single shared implementation both
    `add_down_time` (cycle 1) and `escalate_down_time` (cycle `n+1`, for
    every `n` it just ran) call — see the module docstring for why there
    must be exactly one.

    Also the single place that resolves the namespace's configured
    `time_to_escalate` delay (`_resolve_escalation_delay`, falling back to
    `ESCALATION_DELAY_SECONDS` when settings are absent/invalid) and passes
    it to `schedule_escalation` — both the first cycle and every reschedule
    go through here, so this one change point governs the delay for the
    whole chain.

    **Deterministic id, and why `escalation_number` must be retry-invariant.**
    `task_id = f"{down_time_id}-{escalation_number}"`. This is safe to call
    twice for the very same cycle (e.g. a caller's own retry) with no
    persist-before-create ordering dance required: same inputs -> same id,
    every time, so a repeat collapses into Cloud Tasks' `AlreadyExists`
    (treated as success by `schedule_escalation`) instead of minting a
    second, parallel task. That guarantee only holds if `escalation_number`
    itself never changes across such a retry — callers MUST derive it from
    something retry-invariant (the incoming job payload for
    `escalate_down_time`; the literal `1` for `add_down_time`'s first cycle),
    **never** from this function's own `escalation_count` write below. If a
    caller derived it from the persisted `escalation_count` instead, a retry
    would read the now-updated count, compute a *different* `task_id`, and
    create a genuinely second, parallel task — reintroducing the forked-chain
    bug this whole deterministic-id design exists to prevent.

    **Three outcomes, and only one of them writes to Firestore.**
    `schedule_escalation` reports which one via `ScheduleEscalationResult`
    (see its docstring — `AlreadyExists` is itself ambiguous between "a task
    under this name is already scheduled" and "this name is tombstoned,
    nothing is scheduled"; that function doesn't guess, and neither does
    this one):

    * `task_id is None` (genuine failure, incl. Cloud Tasks simply not being
      configured) — logged at error here (including `down_time_id`, so it's
      clear whose chain just ended), NOTHING is written to Firestore, and
      this returns `None`. Any previously-stored `escalation_task_id` on the
      issue is deliberately left as-is — no compensating write to clear it.
      That's harmless: it still points at the cycle that already fired to
      get here, and `cancel_escalation` already treats a missing/already-
      fired task (`NotFound`) as already-gone. Do not "fix" this by adding a
      clearing write.
    * `already_existed=True` — logged at INFO, not error: this is a normal,
      healthy outcome (typically a `backoff` retry re-entering after a
      notification failure downstream, landing on the same deterministic
      `task_id`), not a problem. Crucially, this ALSO does not write to
      Firestore — whichever call actually created the task already
      persisted this cycle's bookkeeping; writing again here would be a
      pointless, redundant call on every retry, and worse, it would drift
      `escalated_at` forward to the retry's timestamp instead of the time
      the cycle was genuinely scheduled. Returns the task id.
    * created (`already_existed=False`, `task_id` set) — persists together
      (all three derived only from `escalation_number`, so this whole branch
      only ever runs once per cycle in the first place, but even a
      hypothetical repeat would be a no-op, never a second increment):
        * `escalation_task_id` — the newly created task's id.
        * `escalated_at` — now, in the namespace's local time.
        * `escalation_count = escalation_number - 1` — the number of cycles
          that have actually EXECUTED so far (cycle 1 being scheduled means
          0 have run yet; cycle `n+1` being scheduled means `n` — the one
          that just ran — have).
      Returns the task id.

    Returns:
        The scheduled (or already-scheduled) task's id, or `None` if
        creation failed outright.
    """
    task_id = f"{down_time_id}-{escalation_number}"
    # Reuse a settings doc the caller already read (e.g. `add_down_time`, which
    # reads it for shift assignment) to avoid a second read of the same doc in
    # one run; otherwise read it here (best-effort, never raises).
    if settings is _SETTINGS_UNSET:
        settings = read_namespace_settings(firestore, namespace_id)
    delay = _resolve_escalation_delay_from_settings(settings)
    result = schedule_escalation(
        namespace_id,
        down_time_id,
        (namespace or {}).get("timezone"),
        task_id=task_id,
        escalation_number=escalation_number,
        delay=delay,
    )

    if result.task_id is None:
        logger.error(
            f"schedule_escalation_cycle: failed to create escalation Cloud "
            f"Task '{task_id}' for down_time '{down_time_id}' in namespace "
            f"'{namespace_id}' — the escalation chain ends here."
        )
        return None

    if result.already_existed:
        logger.info(
            f"schedule_escalation_cycle: Cloud Task '{task_id}' for "
            f"down_time '{down_time_id}' in namespace '{namespace_id}' "
            "already exists (a retry of this cycle landing on the same "
            "deterministic id, or a tombstoned name) — skipping the "
            "bookkeeping write; whichever call created it already made it."
        )
        return result.task_id

    tz = namespace_timezone(namespace_id, namespace)
    firestore.update_subdocument(
        DOWN_TIME_COLLECTION,
        namespace_id,
        ISSUES_SUBCOLLECTION,
        down_time_id,
        {
            "escalation_task_id": result.task_id,
            "escalated_at": datetime.now(tz).isoformat(),
            "escalation_count": escalation_number - 1,
        },
    )
    return result.task_id
