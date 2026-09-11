"""Layer 2 (defensive) tests for stopping escalations on archived resources:
`_run_escalate_down_time` must stop without rescheduling and without
notifying when the ticket's resource (workstation, or the workstation's
production line) is archived — covering a task already dispatched before
the archive happened, or one whose Layer-1 `cancel_escalation` call (see
`tests/api/test_archive_stops_escalation.py`) failed, since
`cancel_escalation` is best-effort by design and never guarantees the task
is actually gone.

Covers: `src/app/async_jobs/escalate_down_time.py::_run_escalate_down_time`
(around line 314), which as of this Work Unit has no archived-resource
guard at all — every ticket on an archived resource is currently escalated
exactly like one on an active resource. Every "stops" test below is
expected to fail on its own assertion (a reschedule/notification that
should not have happened, or a `result["status"]` that isn't `"stopped"`),
never on a broken fixture.

The guard resolves the ticket's resource the same way the rest of the code
does — the document directly referenced by the ticket's scope — and reads
nothing else. Archiving a production line or a UAP cascades `archived_at`
down to every resource beneath it (see `core.archiving`), so an ancestor
archive is already visible on the ticket's own resource; the archived-line
tests below therefore seed the cascade the product actually produces
(line *and* its workstation archived) rather than a line archived with an
active workstation under it, a state the product cannot produce.

Fixtures below (`_wire_firestore`, `push_spy`, `email_spy`, `reschedule_spy`,
`_seed_issue`, `_payload`) are deliberately copied verbatim from
`tests/async_jobs/test_escalate_down_time.py` rather than imported cross-
module (no shared conftest currently exports them) — same signatures, same
behavior, per the test skill's "reuse rather than invent" rule.
"""

import importlib
from datetime import datetime

import pytest

from src.app.core.escalation import ScheduleEscalationResult
from src.app.core.firestore import PRODUCTION_LINE_COLLECTION, WORKSTATION_COLLECTION
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import DownTimeStatus, Process, ProductionScope, Role

escalate_module = importlib.import_module("src.app.async_jobs.escalate_down_time")
common_module = importlib.import_module("src.app.async_jobs._common")
escalate_down_time = escalate_module.escalate_down_time

NS = "ns-escalate-archived-resource"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS)


@pytest.fixture(autouse=True)
def _wire_firestore(fake_db, monkeypatch):
    """`escalate_down_time` holds its own imported reference to
    `get_firestore_client` — patch it directly against the same `fake_db` the
    `fake_db` fixture already wires everything else to."""
    client = FirestoreClient(client=fake_db)
    monkeypatch.setattr(escalate_module, "get_firestore_client", lambda: client)
    return client


@pytest.fixture
def push_spy(monkeypatch):
    calls: list[dict] = []

    def _spy(tokens, title, body, data=None, notif_level="urgent"):
        calls.append(
            {
                "tokens": list(tokens),
                "title": title,
                "body": body,
                "data": data,
                "notif_level": notif_level,
            }
        )

    monkeypatch.setattr(escalate_module, "send_push_notifications", _spy)
    return calls


class _EmailSpy:
    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, to, language, location, duration, app_url=None):
        self.calls.append(
            {"to": to, "language": language, "location": location, "duration": duration}
        )

    def __len__(self):
        return len(self.calls)

    def __getitem__(self, index):
        return self.calls[index]

    def __iter__(self):
        return iter(self.calls)


@pytest.fixture
def email_spy(monkeypatch):
    spy = _EmailSpy()
    monkeypatch.setattr(escalate_module, "send_down_time_escalation_email", spy)
    return spy


@pytest.fixture
def reschedule_spy(monkeypatch):
    """Spy on `_common.schedule_escalation` — records every call, including
    when none should have happened at all (the assertion this whole suite
    is built around)."""
    calls: list[dict] = []

    def _spy(namespace_id, down_time_id, timezone_name, task_id=None, escalation_number=None, delay=None):
        calls.append(
            {
                "namespace_id": namespace_id,
                "down_time_id": down_time_id,
                "timezone_name": timezone_name,
                "task_id": task_id,
                "escalation_number": escalation_number,
            }
        )
        return ScheduleEscalationResult(task_id=task_id, already_existed=False)

    monkeypatch.setattr(common_module, "schedule_escalation", _spy)
    return calls


def _seed_issue(_wire_firestore, namespace_id=NS, down_time_id="issue-1", **overrides):
    now_iso = datetime.now().isoformat()
    issue = {
        "id": down_time_id,
        "namespace_id": namespace_id,
        "created_at": now_iso,
        "updated_at": now_iso,
        "down_time_scope": ProductionScope.WORK_STATION.value,
        "uap_id": None,
        "production_line_id": None,
        "workstation_id": None,
        "down_time_type": "breakdown",
        "department": None,
        "process": Process.MAINTENANCE.value,
        "status": DownTimeStatus.PENDING.value,
        "created_by": "creator-1",
        "escalation_task_id": "old-task-id",
    }
    issue.update(overrides)
    _wire_firestore.create_subdocument(
        "down_time", namespace_id, "issues", issue, document_id=down_time_id
    )
    return issue


def _payload(**overrides):
    base = {"down_time_id": "issue-1"}
    base.update(overrides)
    return base


def _seed_workstation(_wire_firestore, station_id, namespace_id=NS, **overrides):
    station = {
        "id": station_id,
        "namespace_id": namespace_id,
        "name": "Station",
        "production_line_id": None,
        "type": "standard",
    }
    station.update(overrides)
    _wire_firestore.create_document(
        WORKSTATION_COLLECTION, station, document_id=station_id
    )
    return station


def _seed_production_line(_wire_firestore, line_id, namespace_id=NS, **overrides):
    line = {
        "id": line_id,
        "namespace_id": namespace_id,
        "name": "Line",
        "uap_id": None,
    }
    line.update(overrides)
    _wire_firestore.create_document(
        PRODUCTION_LINE_COLLECTION, line, document_id=line_id
    )
    return line


# --------------------------------------------------------------------------- #
# Archived workstation -> stop, no reschedule, no notification
# --------------------------------------------------------------------------- #


class TestArchivedWorkstationStopsEscalation:
    def test_stops_without_rescheduling_when_workstation_is_archived(
        self, _wire_firestore, push_spy, email_spy, reschedule_spy
    ):
        _seed_workstation(_wire_firestore, "station-1", archived_at="2026-01-01T00:00:00+00:00")
        _seed_issue(
            _wire_firestore,
            workstation_id="station-1",
            status=DownTimeStatus.PENDING.value,
        )

        result = escalate_down_time(NS, _payload(), "job-archived-station")

        assert result["status"] == "stopped"
        assert result["down_time_id"] == "issue-1"
        assert reschedule_spy == []

    def test_sends_no_notification_when_workstation_is_archived(
        self, _wire_firestore, push_spy, email_spy, reschedule_spy, seed_user
    ):
        # A management recipient IS seeded, so that without the
        # archived-resource guard this test would genuinely observe a
        # notification (the "pending" branch always notifies management
        # once it reaches the fan-out) — an empty recipient list would let
        # this assertion pass vacuously regardless of the guard.
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok-mgr")
        _seed_workstation(_wire_firestore, "station-1", archived_at="2026-01-01T00:00:00+00:00")
        _seed_issue(
            _wire_firestore,
            workstation_id="station-1",
            status=DownTimeStatus.PENDING.value,
        )

        escalate_down_time(NS, _payload(), "job-archived-station-notify")

        assert push_spy == []
        assert len(email_spy) == 0

    def test_reason_mentions_archived(self, _wire_firestore, push_spy, email_spy, reschedule_spy):
        """The exact wording of the "stopped" reason isn't pinned by the
        contract (only the existing pattern of a short, human-readable
        string, e.g. `"closed"` / `"issue not found"`), so this only checks
        it names the archived-resource cause rather than pinning an exact
        literal."""
        _seed_workstation(_wire_firestore, "station-1", archived_at="2026-01-01T00:00:00+00:00")
        _seed_issue(
            _wire_firestore,
            workstation_id="station-1",
            status=DownTimeStatus.PENDING.value,
        )

        result = escalate_down_time(NS, _payload(), "job-archived-station-reason")

        assert "archiv" in result.get("reason", "").lower()


# --------------------------------------------------------------------------- #
# Archived production line -> also stops. Archiving a line cascades
# `archived_at` onto its workstations, so the ticket's own resource already
# carries the archive; these tests seed that cascade.
# --------------------------------------------------------------------------- #


class TestArchivedProductionLineStopsEscalation:
    def test_stops_without_rescheduling_when_the_workstations_line_is_archived(
        self, _wire_firestore, push_spy, email_spy, reschedule_spy
    ):
        _seed_production_line(
            _wire_firestore, "line-1", archived_at="2026-01-01T00:00:00+00:00"
        )
        _seed_workstation(
            _wire_firestore,
            "station-1",
            production_line_id="line-1",
            archived_at="2026-01-01T00:00:00+00:00",
        )
        _seed_issue(
            _wire_firestore,
            workstation_id="station-1",
            status=DownTimeStatus.PENDING.value,
        )

        result = escalate_down_time(NS, _payload(), "job-archived-line")

        assert result["status"] == "stopped"
        assert reschedule_spy == []

    def test_sends_no_notification_when_the_workstations_line_is_archived(
        self, _wire_firestore, push_spy, email_spy, reschedule_spy, seed_user
    ):
        # See the sibling workstation-level test for why a management
        # recipient must actually be seeded here.
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok-mgr")
        _seed_production_line(
            _wire_firestore, "line-1", archived_at="2026-01-01T00:00:00+00:00"
        )
        _seed_workstation(
            _wire_firestore,
            "station-1",
            production_line_id="line-1",
            archived_at="2026-01-01T00:00:00+00:00",
        )
        _seed_issue(
            _wire_firestore,
            workstation_id="station-1",
            status=DownTimeStatus.PENDING.value,
        )

        escalate_down_time(NS, _payload(), "job-archived-line-notify")

        assert push_spy == []
        assert len(email_spy) == 0


# --------------------------------------------------------------------------- #
# Non-regression: an open ticket on an ACTIVE resource still escalates and
# still reschedules exactly as today — the contrast that stops a
# "refuse everything" implementation from passing.
# --------------------------------------------------------------------------- #


class TestActiveResourceStillEscalates:
    def test_active_workstation_still_reschedules_and_escalates(
        self, _wire_firestore, push_spy, email_spy, reschedule_spy, seed_user
    ):
        _seed_workstation(_wire_firestore, "station-1")
        _seed_issue(
            _wire_firestore,
            workstation_id="station-1",
            status=DownTimeStatus.PENDING.value,
        )
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok-mgr")

        result = escalate_down_time(NS, _payload(), "job-active-station")

        assert result["status"] == "escalated"
        assert len(reschedule_spy) == 1

    def test_active_production_line_still_reschedules_and_escalates(
        self, _wire_firestore, push_spy, email_spy, reschedule_spy, seed_user
    ):
        _seed_production_line(_wire_firestore, "line-1")
        _seed_workstation(_wire_firestore, "station-1", production_line_id="line-1")
        _seed_issue(
            _wire_firestore,
            workstation_id="station-1",
            status=DownTimeStatus.PENDING.value,
        )
        seed_user(namespace_id=NS, role=Role.MANAGER.value, push_token="tok-mgr")

        result = escalate_down_time(NS, _payload(), "job-active-line")

        assert result["status"] == "escalated"
        assert len(reschedule_spy) == 1
