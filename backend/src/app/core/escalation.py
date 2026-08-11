"""Downtime escalation policy + scheduling helpers.

Shared between the sync API layer (`routers/down_time/`, which opens/closes
tickets and must (re)schedule/cancel the escalation cycle) and the async job
layer (the `escalate_down_time` handler, which re-evaluates the ticket and, if
still unresolved, reschedules the next cycle) — `core/` is the neutral home
either side may import without crossing the sync/async boundary, exactly like
`core/timezone.py`.

**Fresh task id per cycle — do not "simplify" this away.** Cloud Tasks
tombstones a task name for roughly an hour after it executes or is deleted
and refuses to recreate a task under that same name. Escalation reschedules
itself every `ESCALATION_DELAY_SECONDS` (30 minutes), so a stable id (e.g.
the issue id) would work for the *first* cycle but fail silently on the
*second* — `create_task` would raise, `schedule_escalation` would swallow it
and return `None`, and the escalation chain would end after a single alert
with no error surfaced anywhere. `schedule_escalation` therefore always asks
`CloudTask.create_task` for a brand-new UUID-named task, and the caller MUST
persist the returned id on the issue document as `escalation_task_id` so a
later `cancel_escalation` call always targets the *current* cycle's task
(the previous cycle's task id is stale/tombstoned and cancelling it would be
a no-op anyway, since it already fired to get here).
"""

from __future__ import annotations

import logging
from typing import Optional

from src.app.gcp import get_cloud_task_manager
from src.app.globals.enum import JobType, ProductionScope, WorkstationType

logger = logging.getLogger(__name__)

ESCALATION_DELAY_SECONDS = 1800  # 30 minutes

_ALWAYS_ESCALATE_SCOPES = frozenset(
    {
        ProductionScope.PLANT.value,
        ProductionScope.UAP.value,
        ProductionScope.PRODUCTION_LINE.value,
    }
)
_ESCALATING_WORKSTATION_TYPES = frozenset(
    {WorkstationType.BOTTLENECK.value, WorkstationType.CRITICAL.value}
)


def should_escalate(issue: dict, workstation: Optional[dict]) -> bool:
    """Whether an unresolved downtime `issue` warrants management escalation.

    Pure predicate (no I/O) — the caller is responsible for fetching the
    `workstation` document (or passing `None` when it can't be found).

    - scope `plant`, `uap`, or `production line` -> always True: these stop a
      whole area or line, so they are inherently escalation-worthy regardless
      of any single workstation's classification.
    - scope `work station` -> True only when the workstation's `type` is
      `WorkstationType.BOTTLENECK` or `WorkstationType.CRITICAL`. A `standard`
      station, a missing workstation document, or a missing/unknown `type`
      all resolve to False (fail closed — never escalate on unclear data).
    """
    scope = issue.get("down_time_scope")
    if scope in _ALWAYS_ESCALATE_SCOPES:
        return True
    if scope == ProductionScope.WORK_STATION.value:
        if not workstation:
            return False
        return workstation.get("type") in _ESCALATING_WORKSTATION_TYPES
    return False


def schedule_escalation(
    namespace_id: str, down_time_id: str, timezone_name: Optional[str]
) -> Optional[str]:
    """Schedule the next escalation cycle via a delayed Cloud Task.

    Best-effort: never raises. A Cloud Tasks outage must never fail ticket
    creation or block a production agent from closing/updating a ticket —
    any failure is logged at warning and `None` is returned.

    Returns:
        The id of the newly created task (to persist on the issue document
        as `escalation_task_id`), or `None` on failure.
    """
    try:
        manager = get_cloud_task_manager()
        return manager.create_task(
            delay=ESCALATION_DELAY_SECONDS,
            namespace_id=namespace_id,
            job_type=JobType.ESCALATE_DOWN_TIME,
            timezone_name=timezone_name,
            payload={"down_time_id": down_time_id},
        )
    except Exception as e:
        logger.warning(
            f"schedule_escalation: failed to schedule escalation for down_time "
            f"'{down_time_id}' in namespace '{namespace_id}': {e}"
        )
        return None


def cancel_escalation(task_id: Optional[str]) -> bool:
    """Best-effort cancellation of a scheduled escalation task.

    A falsy `task_id` is a no-op returning False. Never raises — a Cloud
    Tasks outage must never block a ticket close/delete.
    """
    if not task_id:
        return False
    try:
        manager = get_cloud_task_manager()
        return manager.delete_task(task_id)
    except Exception as e:
        logger.warning(f"cancel_escalation: failed to cancel task '{task_id}': {e}")
        return False
