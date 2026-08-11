"""Fixtures local to `tests/async_jobs/`.

Two independent slowdowns compound if left unguarded here:

1. `escalate_down_time` is `backoff`-decorated at the top level, and this
   round deliberately makes notification failures propagate to that
   decorator (see the module's docstring) so tests can prove real retry
   happens. Left alone, `backoff` sleeps for real between attempts (`time.sleep`
   inside `backoff._sync`) — a permanent, compounding tax on every retry
   test. Neutralized below by patching `time.sleep` itself to a no-op. This
   does NOT weaken what the retry tests assert — they still verify call
   counts and outcomes; only the real elapsed wall-clock wait is removed.
2. The bigger one: most default test payloads/scopes here (e.g.
   `ProductionScope.PLANT`) make `should_escalate` true, so *every* test that
   creates/reschedules a downtime ticket — not just the ones that actually
   care about escalation — was reaching the REAL `schedule_escalation`,
   which constructs a real `google.cloud.tasks_v2.CloudTasksClient()`
   (network/credential discovery) before failing on the missing project id.
   Stubbed out fast and successful by default below; tests that specifically
   exercise escalation scheduling override this stub with their own spy (a
   test's own `monkeypatch.setattr` on the same `monkeypatch` fixture simply
   replaces it — see `schedule_escalation_spy` / `reschedule_spy` in the
   sibling test modules).

   Both handlers do `from src.app.core.escalation import schedule_escalation`
   — a direct import binds its own name into EACH handler module's
   namespace, so patching `core.escalation`'s copy alone would not affect
   what either handler actually calls at runtime (same gotcha the `fake_db`
   fixture's own comment calls out for `add_down_time`/`get_firestore_client`).
   Every module holding its own bound reference is patched below.
"""

import importlib
import time

import pytest

escalation_module = importlib.import_module("src.app.core.escalation")
add_down_time_module = importlib.import_module("src.app.async_jobs.add_down_time")
escalate_down_time_module = importlib.import_module("src.app.async_jobs.escalate_down_time")


@pytest.fixture(autouse=True)
def _no_real_backoff_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_args, **_kwargs: None)


@pytest.fixture(autouse=True)
def _stub_schedule_escalation_by_default(monkeypatch):
    stub = lambda namespace_id, down_time_id, timezone_name, task_id=None, escalation_number=None: task_id  # noqa: E731
    monkeypatch.setattr(escalation_module, "schedule_escalation", stub)
    monkeypatch.setattr(add_down_time_module, "schedule_escalation", stub)
    monkeypatch.setattr(escalate_down_time_module, "schedule_escalation", stub)
