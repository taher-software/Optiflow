"""API tests for the single-open-downtime guard on `POST /down-times`, per
`.claude/specs/downtime-gantt.md` §4 rev1 (test-first — the guard does not
exist yet; today the endpoint always publishes and returns 202).

Conflict definition (§4, revised 2026-09-11): a declaration is refused when
the target resource **or any of its ancestors** (workstation -> its line ->
its UAP -> plant) already carries an issue in status `pending` or `ongoing`.
A `resolved` (not yet closed) ticket does not block — the fix is done and a
new stop is a new incident. An unrelated resource in another branch of the
hierarchy does not block either. The reverse direction — declaring a
*parent* while a *child* is down — stays allowed (current ruling, pending
confirmation per the BOM).

Every "should now be blocked" test is expected to fail on its own assertion
(`202` instead of `409`) since the endpoint does not check for an existing
open ticket at all yet. The "still allowed" tests assert behavior that
already holds today and are not expected to fail — they exist to pin the
non-regression half of the contract once the guard lands.

**rev4** (§4, structured 409 body, review findings W10 / mobile-parsing
angle): `detail` is a structured object —
`{"code": "downtime_already_open", "blocking_scope", "blocking_ticket_id",
"message"}` — not prose to substring-match.

**rev5** (§4, developer ruling 2026-09-11): `blocking_ticket_id` is ALWAYS
the blocking ticket's id — no `_is_visible` gating in front of it.
Declaring a downtime is restricted to `production agent`
(`_down_time_report_scope`), and `production agent` is in
`_FULL_VISIBILITY_ROLES`: the only role that can ever receive this 409
already reads every ticket of its namespace through `GET /down-times/{id}`,
so a "blocking ticket hidden from the caller" scenario cannot occur. See
`TestConflictGuardVisibility` for the pinned rule. The default
`_seed_open_issue` still carries `process=Process.PRODUCTION.value`,
matching the default `_agent`'s (production agent -> process "production")
own process; that value is incidental now (process no longer affects the
outcome) and kept only as a sensible default payload.
"""

import uuid

import pytest

from src.app.globals.enum import DownTimeStatus, DownTimeType, Process, ProductionScope, Role

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
        # Matches the default `_agent`'s own process (production agent ->
        # "production"), so the blocking ticket is visible to the caller by
        # default — see `_is_visible` / `TestConflictGuardVisibility`.
        "process": Process.PRODUCTION.value,
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
        # §4 rev4 — `detail` is a structured object, not prose to
        # substring-match: `code` / `blocking_scope` / `blocking_ticket_id`
        # / `message`. The default issue carries the caller's own process,
        # so the blocking ticket is visible and its id is present.
        detail = res.json()["detail"]
        assert detail["code"] == "downtime_already_open"
        assert detail["blocking_scope"] == ProductionScope.PLANT.value
        assert detail["blocking_ticket_id"] == existing["id"]
        assert existing["id"] in detail["message"]

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

    def test_open_plant_ticket_blocks_uap_declaration(
        self, client, seed_user, seed_uap, auth_headers, fake_db, publish_spy
    ):
        """An open plant-wide ticket blocks a declaration on any UAP."""
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)
        _seed_open_issue(
            fake_db, down_time_scope="plant", status=DownTimeStatus.PENDING.value
        )
        res = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.UAP.value,
                "uap_id": uap["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert res.status_code == 409, res.text
        assert len(publish_spy) == 0

    def test_open_plant_ticket_blocks_line_declaration(
        self, client, seed_user, seed_uap, seed_production_line, auth_headers,
        fake_db, publish_spy,
    ):
        """An open plant-wide ticket blocks a declaration on any line."""
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        _seed_open_issue(
            fake_db, down_time_scope="plant", status=DownTimeStatus.ONGOING.value
        )
        res = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.PRODUCTION_LINE.value,
                "uap_id": uap["id"],
                "production_line_id": line["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert res.status_code == 409, res.text
        assert len(publish_spy) == 0

    def test_open_plant_ticket_blocks_workstation_declaration(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation,
        auth_headers, fake_db, publish_spy,
    ):
        """An open plant-wide ticket blocks a declaration on any workstation."""
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_open_issue(
            fake_db, down_time_scope="plant", status=DownTimeStatus.PENDING.value
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
        assert len(publish_spy) == 0

    def test_open_uap_ticket_blocks_line_declaration(
        self, client, seed_user, seed_uap, seed_production_line, auth_headers,
        fake_db, publish_spy,
    ):
        """An open ticket on a UAP blocks a declaration on one of its lines."""
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        _seed_open_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=uap["id"],
            status=DownTimeStatus.PENDING.value,
        )
        res = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.PRODUCTION_LINE.value,
                "uap_id": uap["id"],
                "production_line_id": line["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert res.status_code == 409, res.text
        assert len(publish_spy) == 0

    def test_open_uap_ticket_blocks_workstation_declaration(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation,
        auth_headers, fake_db, publish_spy,
    ):
        """An open ticket on a UAP blocks a declaration on a workstation
        nested under one of its lines."""
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_open_issue(
            fake_db,
            down_time_scope="uap",
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
        assert len(publish_spy) == 0

    def test_open_line_ticket_blocks_workstation_declaration(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation,
        auth_headers, fake_db, publish_spy,
    ):
        """An open ticket on a production line blocks a declaration on one
        of its workstations."""
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
        assert res.status_code == 409, res.text
        assert len(publish_spy) == 0


class TestConflictGuardAllows:
    """§4 rev1 — resolved/closed ancestor tickets, unrelated branches, and
    the reverse (parent-while-child-down) direction never block."""

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

    def test_resolved_ancestor_ticket_does_not_block(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation,
        auth_headers, fake_db, publish_spy,
    ):
        """A `resolved` (not yet closed) ticket on the parent line does not
        block a declaration on one of its workstations — the fix is done."""
        agent = _agent(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_open_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            uap_id=uap["id"],
            status=DownTimeStatus.RESOLVED.value,
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

    def test_unrelated_branch_ticket_does_not_block(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation,
        auth_headers, fake_db, publish_spy,
    ):
        """An open ticket on a line in a DIFFERENT UAP branch of the
        hierarchy does not block a declaration on an unrelated workstation."""
        agent = _agent(seed_user)
        busy_uap = seed_uap(namespace_id=NS)
        busy_line = seed_production_line(namespace_id=NS, uap_id=busy_uap["id"])
        _seed_open_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=busy_line["id"],
            uap_id=busy_uap["id"],
            status=DownTimeStatus.ONGOING.value,
        )
        other_uap = seed_uap(namespace_id=NS)
        other_line = seed_production_line(namespace_id=NS, uap_id=other_uap["id"])
        other_station = seed_workstation(
            namespace_id=NS, production_line_id=other_line["id"]
        )
        res = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.WORK_STATION.value,
                "uap_id": other_uap["id"],
                "production_line_id": other_line["id"],
                "workstation_id": other_station["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert res.status_code == 202, res.text
        assert len(publish_spy) == 1

    def test_declaring_parent_while_child_down_is_allowed(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation,
        auth_headers, fake_db, publish_spy,
    ):
        """Reverse direction (current ruling, pending confirmation): a
        workstation already down does not block declaring a downtime on its
        parent line — a broader stop is new information, not a duplicate."""
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
                "production_scope": ProductionScope.PRODUCTION_LINE.value,
                "uap_id": uap["id"],
                "production_line_id": line["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )
        assert res.status_code == 202, res.text
        assert len(publish_spy) == 1


class TestConflictGuardVisibility:
    """§4 rev5 — `blocking_ticket_id` is ALWAYS the blocking ticket's id;
    there is no visibility gating to pin here. Declaring a downtime is
    restricted to `production agent` (`_down_time_report_scope`), and
    `production agent` is in `_FULL_VISIBILITY_ROLES` — the only role that
    can ever receive this 409 already reads every ticket of its namespace
    through `GET /down-times/{id}`. So the "blocking ticket in another
    process" scenario cannot occur for any caller of this endpoint, and no
    `_is_visible` check belongs in front of `blocking_ticket_id` (developer
    ruling, 2026-09-11, spec §4 rev5 — do not re-add the gating)."""

    def test_blocking_ticket_in_another_process_still_shows_its_id(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation,
        auth_headers, fake_db,
    ):
        """The declaring production agent is a full-visibility role, so even
        a blocking ticket owned by another process (maintenance) must
        surface its id: `blocking_ticket_id` is set and the id appears in
        `message`. This is the case that used to be wrongly hidden."""
        agent = _agent(seed_user)  # production agent -> process "production"
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        blocking = _seed_open_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            uap_id=uap["id"],
            status=DownTimeStatus.ONGOING.value,
            process=Process.MAINTENANCE.value,
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
        detail = res.json()["detail"]
        assert detail["blocking_ticket_id"] == blocking["id"]
        assert blocking["id"] in detail["message"]

    def test_blocking_ticket_in_the_same_process_shows_its_id(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation,
        auth_headers, fake_db,
    ):
        """Same scenario, but the blocking ticket belongs to the caller's
        own process (production): the id must be present too — same-process
        or not makes no difference once there is no visibility gating."""
        agent = _agent(seed_user)  # production agent -> process "production"
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        blocking = _seed_open_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            uap_id=uap["id"],
            status=DownTimeStatus.ONGOING.value,
            process=Process.PRODUCTION.value,
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
        detail = res.json()["detail"]
        assert detail["blocking_ticket_id"] == blocking["id"]
        assert blocking["id"] in detail["message"]
