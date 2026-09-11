"""API tests for the single-open-downtime guard on `POST /down-times`, per
`.claude/specs/downtime-gantt.md` §4 (test-first — the guard does not exist
yet; today the endpoint always publishes and returns 202).

Conflict definition (§4): an existing issue in the namespace with the SAME
resource identity (same `production_scope` + same id; `plant` vs `plant`)
whose status is `pending` or `ongoing` blocks a new declaration with `409`.
A `resolved` (not yet closed) ticket does not block, and a different scope/id
(even nested, e.g. a station under an already-down line) does not block
either.

Every "should now be blocked" test is expected to fail on its own assertion
(`202` instead of `409`) since the endpoint does not check for an existing
open ticket at all yet. The "still allowed" tests assert behavior that
already holds today and are not expected to fail — they exist to pin the
non-regression half of the contract once the guard lands.
"""

import uuid

import pytest

from src.app.globals.enum import DownTimeStatus, DownTimeType, ProductionScope, Role

NS = "ns-conflict-guard"
DOWN_TIMES_URL = "/down-times"
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS)


@pytest.fixture(autouse=True)
def _auto_publish(publish_spy):
    return publish_spy


def _agent(seed_user, **overrides):
    overrides.setdefault("namespace_id", NS)
    overrides.setdefault("role", Role.PRODUCTION_AGENT.value)
    return seed_user(**overrides)


def _seed_open_issue(fake_db, namespace_id=NS, **overrides):
    issue_id = overrides.pop("id", str(uuid.uuid4()))
    issue = {
        "id": issue_id,
        "namespace_id": namespace_id,
        "created_at": "2026-01-15T08:00:00+00:00",
        "updated_at": "2026-01-15T08:00:00+00:00",
        "down_time_scope": "plant",
        "uap_id": None,
        "production_line_id": None,
        "workstation_id": None,
        "down_time_type": DownTimeType.BREAKDOWN.value,
        "status": DownTimeStatus.PENDING.value,
        "created_by": "creator-1",
    }
    issue.update(overrides)
    fake_db.collection(DOWN_TIME_COLLECTION).document(namespace_id).collection(
        ISSUES_SUBCOLLECTION
    ).document(issue_id).set(issue)
    return issue


class TestConflictGuardBlocks:
    """§4 — matching resource identity + `pending`/`ongoing` status -> 409."""

    def test_plant_scope_already_pending_returns_409(
        self, client, seed_user, auth_headers, fake_db
    ):
        agent = _agent(seed_user)
        existing = _seed_open_issue(
            fake_db, down_time_scope="plant", status=DownTimeStatus.PENDING.value
        )
        res = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.PLANT.value,
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert res.status_code == 409, res.text
        # §4 requires the message to name the resource / cite the existing
        # ticket id — a clear, user-facing conflict message, not a bare 409.
        assert existing["id"] in res.text

    def test_workstation_scope_already_ongoing_returns_409(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation,
        auth_headers, fake_db,
    ):
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_open_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            production_line_id=line["id"],
            uap_id=uap["id"],
            status=DownTimeStatus.ONGOING.value,
        )
        res = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.WORK_STATION.value,
                "uap_id": uap["id"],
                "production_line_id": line["id"],
                "workstation_id": station["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert res.status_code == 409, res.text

    def test_conflict_response_does_not_publish(
        self, client, seed_user, auth_headers, fake_db, publish_spy
    ):
        agent = _agent(seed_user)
        _seed_open_issue(
            fake_db, down_time_scope="plant", status=DownTimeStatus.PENDING.value
        )
        client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.PLANT.value,
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert len(publish_spy) == 0


class TestConflictGuardAllows:
    """§4 — resolved tickets and differing scope/id never block."""

    def test_resolved_not_yet_closed_does_not_block(
        self, client, seed_user, auth_headers, fake_db, publish_spy
    ):
        agent = _agent(seed_user)
        _seed_open_issue(
            fake_db, down_time_scope="plant", status=DownTimeStatus.RESOLVED.value
        )
        res = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.PLANT.value,
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert res.status_code == 202, res.text
        assert len(publish_spy) == 1

    def test_closed_ticket_does_not_block(
        self, client, seed_user, auth_headers, fake_db, publish_spy
    ):
        agent = _agent(seed_user)
        _seed_open_issue(
            fake_db, down_time_scope="plant", status=DownTimeStatus.CLOSED.value
        )
        res = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.PLANT.value,
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert res.status_code == 202, res.text
        assert len(publish_spy) == 1

    def test_different_scope_under_already_down_line_does_not_block(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation,
        auth_headers, fake_db, publish_spy,
    ):
        """A station under an already-down LINE is a different resource
        identity — declaring the station's own downtime must not be
        blocked by the line's open ticket."""
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_open_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            uap_id=uap["id"],
            status=DownTimeStatus.ONGOING.value,
        )
        res = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.WORK_STATION.value,
                "uap_id": uap["id"],
                "production_line_id": line["id"],
                "workstation_id": station["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert res.status_code == 202, res.text
        assert len(publish_spy) == 1
