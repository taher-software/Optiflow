"""Smoke tests for `GET /kpi/dashboard|drilldown|daily`.

These only check the top-level response shape/status and a couple of
high-value behavioral cases (empty namespace, a shift-fixed drilldown
suppressing `downtime_by_shift`, one point per day, 403 for a non-management
role). Deep coverage of the aggregation helpers (`services.py`) is owned by
the dedicated test-agent unit that runs next.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from src.app.core.firestore import NAMESPACE_SETTINGS_COLLECTION, SETTINGS_SUBCOLLECTION
from src.app.globals.enum import DownTimeStatus, DownTimeType, Process, Role

NS = "ns-kpi"
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS, timezone="UTC", company_name="Acme Plant")


def _owner(seed_user, **overrides):
    overrides.setdefault("namespace_id", NS)
    overrides.setdefault("role", Role.OWNER.value)
    return seed_user(**overrides)


def _seed_settings(fake_db, **overrides):
    doc = {
        "namespace_id": NS,
        "shift_number": 1,
        "shift_1": None,
        "shift_2": None,
        "shift_3": None,
        "time_to_escalate": 1800,
    }
    doc.update(overrides)
    fake_db.collection(NAMESPACE_SETTINGS_COLLECTION).document(NS).collection(
        SETTINGS_SUBCOLLECTION
    ).document(NS).set(doc)
    return doc


def _seed_issue(fake_db, **overrides):
    now = datetime.now(timezone.utc)
    issue = {
        "id": str(uuid.uuid4()),
        "namespace_id": NS,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "down_time_scope": "plant",
        "uap_id": None,
        "production_line_id": None,
        "workstation_id": None,
        "down_time_type": DownTimeType.BREAKDOWN.value,
        "process": Process.MAINTENANCE.value,
        "status": DownTimeStatus.PENDING.value,
        "created_by": "creator-1",
        "shift": None,
        "acknowledged_at": None,
        "acknowledged_by": None,
        "resolved_at": None,
        "resolved_by": None,
        "closed_at": None,
        "closed_by": None,
    }
    issue.update(overrides)
    fake_db.collection(DOWN_TIME_COLLECTION).document(NS).collection(
        ISSUES_SUBCOLLECTION
    ).document(issue["id"]).set(issue)
    return issue


def _period_today():
    today = date.today().isoformat()
    return {"from": today, "to": today}


class TestDashboard:
    def test_empty_namespace_returns_zeros(self, client, seed_user, auth_headers, fake_db):
        owner = _owner(seed_user)
        _seed_settings(fake_db)

        res = client.get("/kpi/dashboard", params=_period_today(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        assert data["namespace"]["name"] == "Acme Plant"
        assert data["namespace"]["shift_number"] == 1
        assert data["namespace"]["uap_count"] == 0
        assert data["overall"] == {
            "downtime_seconds": 0,
            "count": 0,
            "mttr_seconds": 0,
            "mtbf_seconds": data["overall"]["mtbf_seconds"],
        }
        assert data["by_shift"] == []
        assert data["by_location"] == []
        assert data["pareto_by_process"] == []
        assert data["repair_by_process"] == []
        assert data["by_type"] == []

    def test_returns_expected_top_level_shape_with_tickets(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        now = datetime.now(timezone.utc)
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=(now - timedelta(hours=2)).isoformat(),
            resolved_at=(now - timedelta(hours=1)).isoformat(),
            resolved_by="agent-1",
        )
        _seed_issue(fake_db, status=DownTimeStatus.PENDING.value)

        res = client.get("/kpi/dashboard", params=_period_today(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        for key in (
            "namespace",
            "overall",
            "by_shift",
            "by_location",
            "pareto_by_process",
            "repair_by_process",
            "by_type",
        ):
            assert key in data
        assert data["overall"]["count"] == 2
        assert data["overall"]["downtime_seconds"] > 0
        assert len(data["by_type"]) == 1
        assert data["by_type"][0]["id"] == "break_down"
        assert len(data["pareto_by_process"]) == 1
        assert data["pareto_by_process"][0]["id"] == Process.MAINTENANCE.value

    def test_403_for_maintenance_agent(self, client, seed_user, auth_headers):
        agent = seed_user(namespace_id=NS, role=Role.MAINTENANCE_AGENT.value)
        res = client.get("/kpi/dashboard", params=_period_today(), headers=auth_headers(agent))
        assert res.status_code == 403


class TestDrilldown:
    def test_uap_drilldown_returns_children(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        _seed_issue(fake_db, uap_id=uap["id"], production_line_id=line["id"])

        res = client.get(
            "/kpi/drilldown",
            params={**_period_today(), "path": f"uap:{uap['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["children"] is not None
        assert data["children_hint_key"] == "dashboard.drill.linesHint"
        assert any(row["id"] == line["id"] for row in data["children"])

    def test_shift_path_suppresses_downtime_by_shift_section(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(
            fake_db,
            shift_number=2,
            shift_1={"start_time": "06:00", "end_time": "14:00"},
            shift_2={"start_time": "14:00", "end_time": "22:00"},
        )
        _seed_issue(fake_db, shift=1)

        res = client.get(
            "/kpi/drilldown",
            params={**_period_today(), "path": "shift:1"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        # `response_model_exclude_none=True` on the drilldown route (fix #12)
        # omits a suppressed section from the payload entirely rather than
        # sending it as `null`.
        assert "downtime_by_shift" not in data
        assert data["children_hint_key"] == "dashboard.drill.locationsHint"

    def test_malformed_path_returns_422(self, client, seed_user, auth_headers, fake_db):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        res = client.get(
            "/kpi/drilldown",
            params={**_period_today(), "path": "not-a-valid-path"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 422


class TestDaily:
    def test_returns_one_point_per_day(self, client, seed_user, auth_headers, fake_db):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        today = date.today()
        from_date = today - timedelta(days=2)
        _seed_issue(fake_db)

        res = client.get(
            "/kpi/daily",
            params={
                "metric": "count",
                "scope_kind": "plant",
                "from": from_date.isoformat(),
                "to": today.isoformat(),
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        points = res.json()["data"]["points"]
        assert len(points) == 3
        assert [p["date"] for p in points] == [
            (from_date + timedelta(days=i)).isoformat() for i in range(3)
        ]
        assert sum(p["value"] for p in points) == 1

    def test_invalid_metric_returns_422(self, client, seed_user, auth_headers):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/daily",
            params={"metric": "bogus", "scope_kind": "plant", **_period_today()},
            headers=auth_headers(owner),
        )
        assert res.status_code == 422
