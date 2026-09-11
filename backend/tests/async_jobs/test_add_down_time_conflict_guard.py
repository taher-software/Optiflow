"""`add_down_time` handler — the defensive re-check half of the
single-open-downtime guard, per `.claude/specs/downtime-gantt.md` §4:

"checked synchronously in the endpoint's service (so the caller gets the
409), and re-checked defensively in the `add_down_time` async handler,
which aborts without creating the ticket when the conflict exists (the
endpoint only publishes; it never runs the handler in-process)."

None of this exists yet — today `add_down_time` only guards against
replaying the SAME `job_id` (see `tests/async_jobs/test_add_down_time.py`),
never against a DIFFERENT job_id landing on a resource that already has an
open ticket. So `test_conflicting_resource_aborts_without_creating_ticket`
is expected to fail on its own assertion (a second issue document gets
created) rather than on a broken fixture.

The publisher is never invoked here — per convention, the handler is called
directly with its payload, never through Pub/Sub (see `.claude/skills/test`
"Async handler tests")."""

import importlib

import pytest

from src.app.globals.enum import DownTimeStatus, DownTimeType, ProductionScope, Role
from src.app.gcp.firestore import FirestoreClient

add_down_time_module = importlib.import_module("src.app.async_jobs.add_down_time")
add_down_time = add_down_time_module.add_down_time

NS = "ns-handler-conflict-guard"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS)


@pytest.fixture
def push_spy(monkeypatch):
    calls: list[dict] = []

    def _spy(tokens, title, body, data=None):
        calls.append(
            {"tokens": list(tokens), "title": title, "body": body, "data": data}
        )

    monkeypatch.setattr(add_down_time_module, "send_push_notifications", _spy)
    return calls


def _issue(fake_db, namespace_id, job_id):
    return FirestoreClient(client=fake_db).get_subdocument(
        "down_time", namespace_id, "issues", job_id
    )


def _issue_count(fake_db, namespace_id):
    return len(
        FirestoreClient(client=fake_db).find_subdocuments(
            "down_time", namespace_id, "issues"
        )
    )


def _payload(**overrides):
    base = {
        "created_by": "creator-1",
        "production_scope": ProductionScope.PLANT.value,
        "down_time_type": DownTimeType.BREAKDOWN.value,
    }
    base.update(overrides)
    return base


def test_conflicting_resource_aborts_without_creating_ticket(fake_db, push_spy):
    """An existing `pending` plant-scope ticket already open (different
    job_id) — a second `plant`-scope declaration must be aborted, not
    written, by the handler's own defensive re-check."""
    add_down_time(NS, _payload(), "job-first")
    assert _issue(fake_db, NS, "job-first") is not None

    add_down_time(NS, _payload(), "job-second")

    assert _issue(fake_db, NS, "job-second") is None
    assert _issue_count(fake_db, NS) == 1


def test_no_conflict_creates_the_ticket_normally(fake_db, push_spy):
    """Sanity check on the guard's own scope-matching: an unrelated
    workstation-scoped ticket does not block a plant-scoped one."""
    add_down_time(
        NS,
        _payload(
            production_scope=ProductionScope.WORK_STATION.value,
            workstation_id="station-unrelated",
        ),
        "job-first",
    )
    add_down_time(NS, _payload(), "job-second")

    assert _issue(fake_db, NS, "job-first") is not None
    assert _issue(fake_db, NS, "job-second") is not None
    assert _issue_count(fake_db, NS) == 2
