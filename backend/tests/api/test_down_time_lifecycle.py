"""API tests for the downtime READ endpoints (list / detail / summary, with
visibility scoping + permission flags) and the lifecycle TRANSITION endpoints
(acknowledge / resolve / close / delete)."""

from datetime import datetime, timedelta, timezone

import pytest

from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import DownTimeType, ProductionScope, Role

NS = "ns-lifecycle"


def _iso(minutes_ago=0):
    return (
        datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    ).isoformat()


@pytest.fixture
def seed_issue(fake_db):
    """Seed an issue document directly into down_time/{NS}/issues/{id}."""

    def _seed(issue_id, **fields):
        doc = {
            "id": issue_id,
            "namespace_id": NS,
            "created_at": _iso(30),
            "updated_at": _iso(30),
            "down_time_scope": "plant",
            "uap_id": None,
            "production_line_id": None,
            "workstation_id": None,
            "down_time_type": "break down",
            "department": None,
            "process": "maintenance",
            "status": "pending",
            "created_by": "opener",
        }
        doc.update(fields)
        (
            fake_db.collection("down_time")
            .document(NS)
            .collection("issues")
            .document(issue_id)
            .set(doc)
        )
        return doc

    return _seed


def _read(fake_db, issue_id):
    return FirestoreClient(client=fake_db).get_subdocument(
        "down_time", NS, "issues", issue_id
    )


# --------------------------------------------------------------------------- #
# Read: visibility
# --------------------------------------------------------------------------- #


class TestDownTimeReadVisibility:
    def test_production_agent_sees_all(
        self, client, seed_user, seed_issue, auth_headers
    ):
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue("m1", process="maintenance")
        seed_issue("q1", process="quality")
        res = client.get("/down-times", headers=auth_headers(pa))
        assert res.status_code == 200
        assert {i["id"] for i in res.json()["data"]["items"]} == {"m1", "q1"}

    def test_maintenance_agent_sees_only_maintenance(
        self, client, seed_user, seed_issue, auth_headers
    ):
        ma = seed_user(namespace_id=NS, role=Role.MAINTENANCE_AGENT.value)
        seed_issue("m1", process="maintenance")
        seed_issue("q1", process="quality")
        res = client.get("/down-times", headers=auth_headers(ma))
        assert res.status_code == 200
        assert {i["id"] for i in res.json()["data"]["items"]} == {"m1"}

    def test_detail_404_when_not_visible(
        self, client, seed_user, seed_issue, auth_headers
    ):
        ma = seed_user(namespace_id=NS, role=Role.MAINTENANCE_AGENT.value)
        seed_issue("q1", process="quality")
        res = client.get("/down-times/q1", headers=auth_headers(ma))
        assert res.status_code == 404

    def test_status_filter(self, client, seed_user, seed_issue, auth_headers):
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue("p1", status="pending")
        seed_issue("o1", status="ongoing")
        res = client.get("/down-times?status=ongoing", headers=auth_headers(pa))
        assert res.status_code == 200
        assert {i["id"] for i in res.json()["data"]["items"]} == {"o1"}

    def test_pagination_limit_offset(
        self, client, seed_user, seed_issue, auth_headers
    ):
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        # created_at newest-first when sorted desc: p0 (now) ... p4 (4 min ago).
        for i in range(5):
            seed_issue(f"p{i}", status="pending", created_at=_iso(i))

        first = client.get("/down-times?limit=2&offset=0", headers=auth_headers(pa))
        data = first.json()["data"]
        assert data["total"] == 5
        assert data["limit"] == 2 and data["offset"] == 0
        assert [i["id"] for i in data["items"]] == ["p0", "p1"]

        last = client.get("/down-times?limit=2&offset=4", headers=auth_headers(pa))
        last_data = last.json()["data"]
        assert last_data["total"] == 5
        assert [i["id"] for i in last_data["items"]] == ["p4"]


# --------------------------------------------------------------------------- #
# Read: permission flags + summary
# --------------------------------------------------------------------------- #


class TestDownTimeFlagsAndSummary:
    def test_permission_flags_pending_maintenance(
        self, client, seed_user, seed_issue, auth_headers
    ):
        ma = seed_user(namespace_id=NS, role=Role.MAINTENANCE_AGENT.value)
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue("m1", process="maintenance", status="pending", created_by=pa["id"])

        ma_view = client.get("/down-times/m1", headers=auth_headers(ma)).json()["data"]
        assert ma_view["can_acknowledge"] is True
        assert ma_view["can_delete"] is False

        pa_view = client.get("/down-times/m1", headers=auth_headers(pa)).json()["data"]
        assert pa_view["can_acknowledge"] is False
        assert pa_view["can_delete"] is True  # production agent + opener + pending

    def test_summary_counts_and_average(
        self, client, seed_user, seed_issue, auth_headers
    ):
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue("p1", status="pending", created_at=_iso(10))
        seed_issue("p2", status="pending", created_at=_iso(20))
        seed_issue("o1", status="ongoing", acknowledged_at=_iso(5))
        res = client.get("/down-times/summary", headers=auth_headers(pa))
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["pending"]["count"] == 2
        assert data["pending"]["average_seconds"] is not None
        assert data["ongoing"]["count"] == 1
        assert data["closed"]["count"] == 0
        assert data["closed"]["average_seconds"] is None


# --------------------------------------------------------------------------- #
# Transitions
# --------------------------------------------------------------------------- #


class TestDownTimeTransitions:
    def test_acknowledge_by_process_agent(
        self, client, fake_db, seed_user, seed_issue, auth_headers
    ):
        ma = seed_user(namespace_id=NS, role=Role.MAINTENANCE_AGENT.value)
        seed_issue("m1", process="maintenance", status="pending")
        res = client.post("/down-times/m1/acknowledge", headers=auth_headers(ma))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["status"] == "ongoing"
        stored = _read(fake_db, "m1")
        assert stored["status"] == "ongoing"
        assert stored["acknowledged_by"] == ma["id"]
        assert stored["acknowledged_at"]

    def test_acknowledge_twice_conflict(
        self, client, seed_user, seed_issue, auth_headers
    ):
        ma = seed_user(namespace_id=NS, role=Role.MAINTENANCE_AGENT.value)
        seed_issue("m1", process="maintenance", status="ongoing")
        res = client.post("/down-times/m1/acknowledge", headers=auth_headers(ma))
        assert res.status_code == 409

    def test_acknowledge_wrong_role_forbidden(
        self, client, seed_user, seed_issue, auth_headers
    ):
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue("m1", process="maintenance", status="pending")
        res = client.post("/down-times/m1/acknowledge", headers=auth_headers(pa))
        assert res.status_code == 403

    def test_acknowledge_wrong_process_forbidden(
        self, client, seed_user, seed_issue, auth_headers
    ):
        ma = seed_user(namespace_id=NS, role=Role.MAINTENANCE_AGENT.value)
        seed_issue("q1", process="quality", status="pending")
        res = client.post("/down-times/q1/acknowledge", headers=auth_headers(ma))
        # not visible + not permitted -> 404 or 403; must not be 200
        assert res.status_code in (403, 404)

    def test_resolve_then_close_happy_path(
        self, client, fake_db, seed_user, seed_issue, auth_headers
    ):
        ma = seed_user(namespace_id=NS, role=Role.MAINTENANCE_AGENT.value)
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue("m1", process="maintenance", status="ongoing")
        r = client.post("/down-times/m1/resolve", headers=auth_headers(ma))
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "resolved"
        c = client.post("/down-times/m1/close", headers=auth_headers(pa))
        assert c.status_code == 200
        assert c.json()["data"]["status"] == "closed"
        assert _read(fake_db, "m1")["closed_by"] == pa["id"]

    def test_close_non_production_agent_forbidden(
        self, client, seed_user, seed_issue, auth_headers
    ):
        ma = seed_user(namespace_id=NS, role=Role.MAINTENANCE_AGENT.value)
        seed_issue("m1", process="maintenance", status="resolved")
        res = client.post("/down-times/m1/close", headers=auth_headers(ma))
        assert res.status_code == 403

    def test_close_when_not_resolved_conflict(
        self, client, seed_user, seed_issue, auth_headers
    ):
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue("m1", process="maintenance", status="pending")
        res = client.post("/down-times/m1/close", headers=auth_headers(pa))
        assert res.status_code == 409

    def test_delete_by_opener_pending(
        self, client, seed_user, seed_issue, auth_headers
    ):
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue("m1", process="maintenance", status="pending", created_by=pa["id"])
        res = client.delete("/down-times/m1", headers=auth_headers(pa))
        assert res.status_code == 200
        assert client.get("/down-times/m1", headers=auth_headers(pa)).status_code == 404

    def test_delete_non_owner_forbidden(
        self, client, seed_user, seed_issue, auth_headers
    ):
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue("m1", process="maintenance", status="pending", created_by="someone-else")
        res = client.delete("/down-times/m1", headers=auth_headers(pa))
        assert res.status_code == 403

    def test_delete_non_pending_conflict(
        self, client, seed_user, seed_issue, auth_headers
    ):
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue("m1", process="maintenance", status="ongoing", created_by=pa["id"])
        res = client.delete("/down-times/m1", headers=auth_headers(pa))
        assert res.status_code == 409

    def test_transition_timestamps_use_namespace_timezone(
        self, client, fake_db, seed_user, seed_issue, seed_namespace, auth_headers
    ):
        # Paris is +01:00 / +02:00 — never UTC.
        seed_namespace(id=NS, timezone="Europe/Paris")
        ma = seed_user(namespace_id=NS, role=Role.MAINTENANCE_AGENT.value)
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue("m1", process="maintenance", status="pending")

        client.post("/down-times/m1/acknowledge", headers=auth_headers(ma))
        client.post("/down-times/m1/resolve", headers=auth_headers(ma))
        client.post("/down-times/m1/close", headers=auth_headers(pa))

        stored = _read(fake_db, "m1")
        for field in ("acknowledged_at", "resolved_at", "closed_at", "updated_at"):
            offset = datetime.fromisoformat(stored[field]).utcoffset()
            assert offset is not None and offset != timedelta(0), field


# --------------------------------------------------------------------------- #
# Close-only lifecycle (down_time_type in CLOSE_ONLY_DOWNTIME_TYPES):
# pending -> closed directly, skipping acknowledge/resolve entirely.
# --------------------------------------------------------------------------- #

# (down_time_type, owning process, the role that would normally be allowed to
# acknowledge/resolve a ticket of that process — used to prove the close-only
# lifecycle rule beats the role rule even for that "normally allowed" role).
_CLOSE_ONLY_CASES = [
    (DownTimeType.OTHERS.value, "production", Role.PRODUCTION_AGENT.value),
    (DownTimeType.WIP_SHORTAGE.value, "production", Role.PRODUCTION_AGENT.value),
]


class TestCloseOnlyLifecycle:
    @pytest.mark.parametrize("down_time_type,process,normal_role", _CLOSE_ONLY_CASES)
    def test_pending_flags_only_allow_close(
        self, client, seed_user, seed_issue, auth_headers, down_time_type, process, normal_role
    ):
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue(
            "c1", down_time_type=down_time_type, process=process, status="pending"
        )
        res = client.get("/down-times/c1", headers=auth_headers(pa))
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["can_acknowledge"] is False
        assert data["can_resolve"] is False
        assert data["can_close"] is True

    @pytest.mark.parametrize("down_time_type,process,normal_role", _CLOSE_ONLY_CASES)
    def test_acknowledge_and_resolve_forbidden_even_for_normal_role(
        self, client, seed_user, seed_issue, auth_headers, down_time_type, process, normal_role
    ):
        # The lifecycle rule (close-only) must beat the role rule: even the
        # role that would normally be allowed to acknowledge/resolve a ticket
        # of this process is still forbidden.
        agent = seed_user(namespace_id=NS, role=normal_role)
        seed_issue(
            "c1", down_time_type=down_time_type, process=process, status="pending"
        )
        ack = client.post("/down-times/c1/acknowledge", headers=auth_headers(agent))
        assert ack.status_code == 403

        seed_issue(
            "c2", down_time_type=down_time_type, process=process, status="ongoing"
        )
        resolve = client.post("/down-times/c2/resolve", headers=auth_headers(agent))
        assert resolve.status_code == 403

    @pytest.mark.parametrize("down_time_type,process,normal_role", _CLOSE_ONLY_CASES)
    def test_close_from_pending_by_production_agent_succeeds(
        self,
        client,
        fake_db,
        seed_user,
        seed_issue,
        auth_headers,
        down_time_type,
        process,
        normal_role,
    ):
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue(
            "c1", down_time_type=down_time_type, process=process, status="pending"
        )
        res = client.post("/down-times/c1/close", headers=auth_headers(pa))
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["status"] == "closed"
        assert data["acknowledged_at"] is None
        assert data["resolved_at"] is None

        stored = _read(fake_db, "c1")
        assert stored["status"] == "closed"
        assert stored.get("acknowledged_at") is None
        assert stored.get("resolved_at") is None

    @pytest.mark.parametrize("down_time_type,process,normal_role", _CLOSE_ONLY_CASES)
    def test_close_by_non_production_agent_forbidden(
        self, client, seed_user, seed_issue, auth_headers, down_time_type, process, normal_role
    ):
        # Any role other than "production agent" is forbidden from closing —
        # use maintenance agent regardless of the ticket's own process, since
        # close is always production-agent-only (not process-scoped).
        agent = seed_user(namespace_id=NS, role=Role.MAINTENANCE_AGENT.value)
        seed_issue(
            "c1", down_time_type=down_time_type, process=process, status="pending"
        )
        res = client.post("/down-times/c1/close", headers=auth_headers(agent))
        assert res.status_code == 403

    @pytest.mark.parametrize("down_time_type,process,normal_role", _CLOSE_ONLY_CASES)
    @pytest.mark.parametrize("legacy_status", ["ongoing", "resolved"])
    def test_close_legacy_non_pending_close_only_ticket_succeeds(
        self,
        client,
        fake_db,
        seed_user,
        seed_issue,
        auth_headers,
        down_time_type,
        process,
        normal_role,
        legacy_status,
    ):
        # Regression for the retroactive-rule deadlock: a close-only ticket
        # created before its type became close-only (or otherwise stuck
        # mid-lifecycle) may still be sitting in `ongoing`/`resolved`. Since
        # acknowledge/resolve are forbidden for close-only types, `close`
        # must remain reachable from there or the ticket strands forever and
        # corrupts the ongoing/resolved KPI buckets.
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue(
            "c1",
            down_time_type=down_time_type,
            process=process,
            status=legacy_status,
        )
        res = client.post("/down-times/c1/close", headers=auth_headers(pa))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["status"] == "closed"
        assert _read(fake_db, "c1")["status"] == "closed"

    @pytest.mark.parametrize("down_time_type,process,normal_role", _CLOSE_ONLY_CASES)
    def test_close_already_closed_close_only_ticket_conflict(
        self, client, seed_user, seed_issue, auth_headers, down_time_type, process, normal_role
    ):
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue(
            "c1", down_time_type=down_time_type, process=process, status="closed"
        )
        res = client.post("/down-times/c1/close", headers=auth_headers(pa))
        assert res.status_code == 409
        assert res.json()["detail"] == "Ticket is already closed."

    def test_normal_type_still_requires_full_lifecycle(
        self, client, seed_user, seed_issue, auth_headers
    ):
        """Regression: a non-close-only type (e.g. breakdown) must still go
        pending -> ongoing -> resolved -> closed; closing directly from
        pending is rejected."""
        ma = seed_user(namespace_id=NS, role=Role.MAINTENANCE_AGENT.value)
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue(
            "b1", down_time_type=DownTimeType.BREAKDOWN.value,
            process="maintenance", status="pending",
        )
        premature_close = client.post("/down-times/b1/close", headers=auth_headers(pa))
        assert premature_close.status_code == 409
        assert premature_close.json()["detail"] == "Ticket is not resolved."

        ack = client.post("/down-times/b1/acknowledge", headers=auth_headers(ma))
        assert ack.status_code == 200
        resolve = client.post("/down-times/b1/resolve", headers=auth_headers(ma))
        assert resolve.status_code == 200
        close = client.post("/down-times/b1/close", headers=auth_headers(pa))
        assert close.status_code == 200
        assert close.json()["data"]["status"] == "closed"

    def test_summary_counts_closed_close_only_ticket_without_skewing_average(
        self, client, seed_user, seed_issue, auth_headers
    ):
        """KPI-integrity case: a directly-closed close-only ticket (no
        `resolved_at`) must count in `closed.count` but must not contribute a
        bogus/zero duration to `closed.average_seconds` (which is defined as
        closed_at - resolved_at)."""
        pa = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        # A normal ticket fully closed, contributing a real duration.
        seed_issue(
            "b1",
            down_time_type=DownTimeType.BREAKDOWN.value,
            process="maintenance",
            status="closed",
            acknowledged_at=_iso(30),
            resolved_at=_iso(20),
            closed_at=_iso(10),
        )
        # A close-only ticket, closed directly from pending: no resolved_at.
        seed_issue(
            "c1",
            down_time_type=DownTimeType.OTHERS.value,
            process="production",
            status="closed",
            acknowledged_at=None,
            resolved_at=None,
            closed_at=_iso(5),
        )
        res = client.get("/down-times/summary", headers=auth_headers(pa))
        assert res.status_code == 200
        closed = res.json()["data"]["closed"]
        assert closed["count"] == 2
        # Average must reflect only the one ticket with both timestamps —
        # not None (crash-avoided) and not skewed to zero by the other.
        assert closed["average_seconds"] is not None
        assert closed["average_seconds"] == pytest.approx(600, abs=2)

    def test_create_down_time_with_others_type_is_accepted(
        self, client, seed_user, auth_headers, publish_spy
    ):
        """422 here would mean the `others` down_time_type doesn't flow
        through `CreateDownTimeIn`'s enum validation."""
        agent = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        res = client.post(
            "/down-times",
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.PLANT.value,
                "down_time_type": DownTimeType.OTHERS.value,
            },
        )
        assert res.status_code == 202, res.text
        assert publish_spy[0]["payload"]["down_time_type"] == "others"
