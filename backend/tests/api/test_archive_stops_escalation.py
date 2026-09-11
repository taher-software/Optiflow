"""API tests for Layer 1 of "stopping escalations on archived resources":
archiving a workstation / production line / UAP must cancel the pending
escalation Cloud Task of every OPEN downtime ticket on it — including
tickets on resources swept in by the cascade — via
`core.escalation.cancel_escalation`, and clear that ticket's
`escalation_task_id`. The ticket is NOT otherwise modified: its `status`
field is left exactly as stored.

Covers: `src/app/routers/{uap,production_line,workstation}/services.py`
(`delete_uap` / `delete_production_line` / `delete_workstation`). As of this
Work Unit, none of the three archiving services touch any downtime ticket at
all, so every test below is expected to fail on its own assertion (the
escalation_task_id / cancel-spy staying untouched by the archive call), not
on a broken fixture or import error.

Patching convention: `down_time.services` already imports
`cancel_escalation` straight off `core.escalation`
(`from src.app.core.escalation import cancel_escalation`) and every test
that spies on it patches that bound name on `down_time_services_module`
(see `tests/api/test_down_time_lifecycle.py::TestEscalationCancelledOnCloseAndDelete`).
This suite assumes the archiving services will follow that exact, already
established convention, and patches the same bound name on each archiving
service module with `raising=False` (the name does not exist on those
modules yet — this Work Unit is test-first). If the real implementation
calls through a differently-named indirection, these spy-based assertions
will fail for that reason instead; the companion assertions on the stored
`escalation_task_id` are written to hold regardless of which internal name
is used, since they check the only externally-observable contract.

Scope boundary: this is Layer 1 (proactive, at archive time) only. Layer 2
(the defensive guard inside `escalate_down_time` itself) is covered by
`tests/async_jobs/test_escalate_down_time_archived_resource.py`. KPI /
ticket-status side effects beyond `escalation_task_id` are out of scope,
matching `tests/api/test_resource_archiving.py`'s own scope note.
"""

from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import DownTimeStatus, ProductionScope, Role

import src.app.routers.production_line.services as production_line_services_module
import src.app.routers.uap.services as uap_services_module
import src.app.routers.workstation.services as workstation_services_module

UAPS_URL = "/uaps"
PRODUCTION_LINES_URL = "/production-lines"
WORKSTATIONS_URL = "/workstations"

NS = "ns-archive-stops-escalation"

DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"


def _owner(seed_user, **overrides):
    overrides.setdefault("namespace_id", NS)
    overrides.setdefault("role", Role.OWNER.value)
    return seed_user(**overrides)


def _seed_issue(fake_db, issue_id, **fields):
    doc = {
        "id": issue_id,
        "namespace_id": NS,
        "down_time_scope": ProductionScope.WORK_STATION.value,
        "uap_id": None,
        "production_line_id": None,
        "workstation_id": None,
        "down_time_type": "break down",
        "process": "maintenance",
        "status": DownTimeStatus.PENDING.value,
        "created_by": "opener",
        "escalation_task_id": "task-original",
    }
    doc.update(fields)
    fake_db.collection(DOWN_TIME_COLLECTION).document(NS).collection(
        ISSUES_SUBCOLLECTION
    ).document(issue_id).set(doc)
    return doc


def _read_issue(fake_db, issue_id):
    return FirestoreClient(client=fake_db).get_subdocument(
        DOWN_TIME_COLLECTION, NS, ISSUES_SUBCOLLECTION, issue_id
    )


def _cancel_spy(monkeypatch, *modules):
    calls: list[str] = []

    def _spy(task_id):
        calls.append(task_id)
        return True

    for module in modules:
        monkeypatch.setattr(module, "cancel_escalation", _spy, raising=False)
    return calls


# --------------------------------------------------------------------------- #
# Archiving a workstation cancels the open ticket on it
# --------------------------------------------------------------------------- #


class TestArchiveWorkstationCancelsEscalation:
    def test_archive_workstation_cancels_open_ticket_escalation(
        self, client, fake_db, seed_user, seed_workstation, auth_headers, monkeypatch
    ):
        owner = _owner(seed_user)
        station = seed_workstation(namespace_id=NS)
        calls = _cancel_spy(monkeypatch, workstation_services_module)
        _seed_issue(
            fake_db,
            "issue-1",
            workstation_id=station["id"],
            status=DownTimeStatus.PENDING.value,
            escalation_task_id="task-original",
        )

        response = client.delete(
            f"{WORKSTATIONS_URL}/{station['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 200
        assert calls == ["task-original"]
        stored = _read_issue(fake_db, "issue-1")
        assert stored["escalation_task_id"] is None

    def test_archive_workstation_leaves_ticket_status_unchanged(
        self, client, fake_db, seed_user, seed_workstation, auth_headers, monkeypatch
    ):
        owner = _owner(seed_user)
        station = seed_workstation(namespace_id=NS)
        _cancel_spy(monkeypatch, workstation_services_module)
        _seed_issue(
            fake_db,
            "issue-1",
            workstation_id=station["id"],
            status=DownTimeStatus.ONGOING.value,
            escalation_task_id="task-original",
        )

        response = client.delete(
            f"{WORKSTATIONS_URL}/{station['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 200
        stored = _read_issue(fake_db, "issue-1")
        assert stored["status"] == DownTimeStatus.ONGOING.value

    def test_archive_workstation_does_not_disturb_a_closed_ticket(
        self, client, fake_db, seed_user, seed_workstation, auth_headers, monkeypatch
    ):
        owner = _owner(seed_user)
        station = seed_workstation(namespace_id=NS)
        calls = _cancel_spy(monkeypatch, workstation_services_module)
        closed = _seed_issue(
            fake_db,
            "issue-closed",
            workstation_id=station["id"],
            status=DownTimeStatus.CLOSED.value,
            escalation_task_id=None,
        )

        response = client.delete(
            f"{WORKSTATIONS_URL}/{station['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 200
        assert calls == []
        assert _read_issue(fake_db, "issue-closed") == closed

    def test_archive_workstation_with_no_open_ticket_archives_without_error(
        self, client, fake_db, seed_user, seed_workstation, auth_headers, monkeypatch
    ):
        owner = _owner(seed_user)
        station = seed_workstation(namespace_id=NS)
        calls = _cancel_spy(monkeypatch, workstation_services_module)

        response = client.delete(
            f"{WORKSTATIONS_URL}/{station['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 200
        assert calls == []

    def test_archive_workstation_cancellation_failure_does_not_fail_the_request(
        self, client, fake_db, seed_user, seed_workstation, auth_headers, monkeypatch
    ):
        """`cancel_escalation` is documented to never raise, but the archive
        service's own call-site must not let a misbehaving canceller turn a
        successful archive into a 500 either — same belt-and-braces
        guarantee `down_time.services` already pins for close/delete (see
        `test_down_time_lifecycle.py::test_close_survives_cancellation_raising`)."""
        owner = _owner(seed_user)
        station = seed_workstation(namespace_id=NS)

        def _boom(task_id):
            raise RuntimeError("cloud tasks is down")

        monkeypatch.setattr(
            workstation_services_module, "cancel_escalation", _boom, raising=False
        )
        _seed_issue(
            fake_db,
            "issue-1",
            workstation_id=station["id"],
            status=DownTimeStatus.PENDING.value,
            escalation_task_id="task-original",
        )

        response = client.delete(
            f"{WORKSTATIONS_URL}/{station['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 200


# --------------------------------------------------------------------------- #
# Archiving a production line cancels escalations for tickets on its
# cascaded workstations
# --------------------------------------------------------------------------- #


class TestArchiveProductionLineCascadeCancelsEscalation:
    def test_archive_production_line_cancels_ticket_on_its_workstation(
        self,
        client,
        fake_db,
        seed_user,
        seed_production_line,
        seed_workstation,
        auth_headers,
        monkeypatch,
    ):
        owner = _owner(seed_user)
        line = seed_production_line(namespace_id=NS)
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        calls = _cancel_spy(monkeypatch, production_line_services_module)
        _seed_issue(
            fake_db,
            "issue-1",
            workstation_id=station["id"],
            status=DownTimeStatus.PENDING.value,
            escalation_task_id="task-original",
        )

        response = client.delete(
            f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 200
        assert calls == ["task-original"]
        assert _read_issue(fake_db, "issue-1")["escalation_task_id"] is None


# --------------------------------------------------------------------------- #
# Archiving a UAP cancels escalations for tickets on the deepest level of
# the cascade (a workstation on one of the UAP's lines), not just on the UAP
# itself
# --------------------------------------------------------------------------- #


class TestArchiveUapCascadeCancelsDeepestEscalation:
    def test_archive_uap_cancels_ticket_on_cascaded_workstation(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
        monkeypatch,
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        calls = _cancel_spy(monkeypatch, uap_services_module)
        _seed_issue(
            fake_db,
            "issue-1",
            workstation_id=station["id"],
            status=DownTimeStatus.PENDING.value,
            escalation_task_id="task-original",
        )

        response = client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        assert response.status_code == 200
        assert calls == ["task-original"]
        assert _read_issue(fake_db, "issue-1")["escalation_task_id"] is None

    def test_archive_uap_with_no_open_ticket_anywhere_in_the_cascade_archives_without_error(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
        monkeypatch,
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line["id"])
        calls = _cancel_spy(monkeypatch, uap_services_module)

        response = client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        assert response.status_code == 200
        assert calls == []
