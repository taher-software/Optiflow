"""Fixtures local to `tests/async_jobs/`.

Two independent slowdowns compound if left unguarded here:

1. `escalate_down_time` is `backoff`-decorated at the top level, and
   notification failures are deliberately allowed to propagate to that
   decorator (see the module's docstring) so tests can prove real retry
   happens. Left alone, `backoff` sleeps for real between attempts (`time.sleep`
   inside `backoff._sync`) — a permanent, compounding tax on every retry
   test. Neutralized below by patching `time.sleep` itself to a no-op. This
   does NOT weaken what the retry tests assert — they still verify call
   counts and outcomes; only the real elapsed wall-clock wait is removed.
2. The bigger one: most default test payloads/scopes here (e.g.
   `ProductionScope.PLANT`) make `should_escalate` true, so *every* test that
   creates/reschedules a downtime ticket — not just the ones that actually
   care about escalation — was reaching the REAL `schedule_escalation`
   (via `_common.schedule_escalation_cycle`, the single composition both
   handlers call), which constructs a real `google.cloud.tasks_v2.
   CloudTasksClient()` (network/credential discovery) before failing on the
   missing project id. Stubbed out fast and successful by default below;
   tests that specifically exercise escalation scheduling override this
   stub with their own spy (a test's own `monkeypatch.setattr` on the same
   `monkeypatch` fixture simply replaces it — see `schedule_escalation_spy`
   / `reschedule_spy` in the sibling test modules, and `tests/async_jobs/
   test_common.py` for direct unit tests of the composition itself).

   `_common.schedule_escalation_cycle` is the ONE place that calls
   `core.escalation.schedule_escalation` — a direct `from ... import
   schedule_escalation`, so it binds its own name into `_common`'s
   namespace. Patching `core.escalation`'s copy alone would not affect what
   `schedule_escalation_cycle` actually calls at runtime (same gotcha the
   `fake_db` fixture's own comment calls out for `add_down_time`/
   `get_firestore_client`) — patching `_common`'s bound name here covers
   BOTH handlers at once, since both call through the one shared function.
"""

import importlib
import time

import pytest

from src.app.core.escalation import ScheduleEscalationResult

common_module = importlib.import_module("src.app.async_jobs._common")


@pytest.fixture(autouse=True)
def _no_real_backoff_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_args, **_kwargs: None)


@pytest.fixture(autouse=True)
def _stub_schedule_escalation_by_default(monkeypatch):
    """Default stub always reports a clean "created" outcome
    (`already_existed=False`) — the shape `schedule_escalation` returns
    since it stopped returning a bare id/`None`. Tests that specifically
    need `already_existed=True` or a genuine-failure outcome override this
    with their own spy (see `schedule_escalation_spy` / `reschedule_spy` in
    the sibling test modules)."""
    monkeypatch.setattr(
        common_module,
        "schedule_escalation",
        lambda namespace_id, down_time_id, timezone_name, task_id=None, escalation_number=None: (
            ScheduleEscalationResult(task_id=task_id, already_existed=False)
        ),
    )
