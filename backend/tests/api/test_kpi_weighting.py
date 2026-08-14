"""API-level coverage for the per-workstation downtime weighting introduced
in `.claude/specs/kpi-dashboard.md` §5bis.1bis (revision 2), plus the other
revision-2 changes that don't yet have end-to-end coverage: `availability`'s
removal and MTBF's shift-window-without-break formula.

`tests/api/test_kpi_helpers.py::TestTicketWeight` already unit-tests
`_ticket_weight` directly against a bare hierarchy dict. This file drives the
same rules through the real `/kpi/*` endpoints over a seeded UAP -> line ->
workstation hierarchy, so it also exercises where the weight is threaded
through: `overall`, every breakdown row, the Pareto, the drill-down bars +
children, and `/kpi/daily?metric=duration` — and, symmetrically, that it is
NOT threaded into `count`, `mttr_seconds`, `repair_by_process`, the
agent bars, or `/kpi/daily?metric=count|mttr`.

All tickets below use fixed 2026-01-15 timestamps in the past relative to
wall-clock "now" at test-run time, so `_ticket_downtime_seconds`'s
`min(natural_end, now)` clamp never kicks in for CLOSED tickets and no
`freeze_kpi_clock`-style patching is needed except for the carry-over test
(an open ticket, whose "now" clamp must be deterministic).
"""

import uuid
from datetime import date, datetime

import pytest

import src.app.routers.kpi.services as kpi_services_module
from src.app.core.firestore import NAMESPACE_SETTINGS_COLLECTION, SETTINGS_SUBCOLLECTION
from src.app.globals.enum import DownTimeStatus, DownTimeType, Process, Role

NS = "ns-kpi-weight"
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS, timezone="UTC", company_name="Weighted Plant")


def _owner(seed_user, namespace_id=NS, **overrides):
    overrides.setdefault("namespace_id", namespace_id)
    overrides.setdefault("role", Role.OWNER.value)
    return seed_user(**overrides)


def _seed_settings(fake_db, namespace_id=NS, **overrides):
    doc = {
        "namespace_id": namespace_id,
        "shift_number": 1,
        "shift_1": None,
        "shift_2": None,
        "shift_3": None,
        "time_to_escalate": 1800,
    }
    doc.update(overrides)
    fake_db.collection(NAMESPACE_SETTINGS_COLLECTION).document(namespace_id).collection(
        SETTINGS_SUBCOLLECTION
    ).document(namespace_id).set(doc)
    return doc


def _seed_issue(fake_db, namespace_id=NS, **overrides):
    issue = {
        "id": str(uuid.uuid4()),
        "namespace_id": namespace_id,
        "created_at": "2026-01-15T07:00:00+00:00",
        "updated_at": "2026-01-15T07:00:00+00:00",
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
    fake_db.collection(DOWN_TIME_COLLECTION).document(namespace_id).collection(
        ISSUES_SUBCOLLECTION
    ).document(issue["id"]).set(issue)
    return issue


def _utc(hour, minute=0, day=15):
    return f"2026-01-{day:02d}T{hour:02d}:{minute:02d}:00+00:00"


def _period(day=15):
    d = date(2026, 1, day).isoformat()
    return {"from": d, "to": d}


@pytest.fixture
def freeze_kpi_clock(monkeypatch):
    """Pins `services.datetime.now(tz)` to 2026-01-15 18:00 (same pattern as
    `test_kpi_dashboard.py::freeze_kpi_clock`) — only needed for the
    carry-over (still-open-ticket) scenario, where the downtime clamp's
    upper bound is "now"."""
    fixed = datetime(2026, 1, 15, 18, 0, 0)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.replace(tzinfo=tz) if tz else fixed

    monkeypatch.setattr(kpi_services_module, "datetime", _FixedDatetime)
    return fixed


# --------------------------------------------------------------------------
# 1. Per-scope weighting (station=1, line=N, UAP=sum, plant=total, floor=1).
# --------------------------------------------------------------------------


class TestWeightPerScope:
    def test_station_ticket_weight_is_one_even_on_a_multi_station_line(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        stations = [
            seed_workstation(namespace_id=NS, production_line_id=line["id"]) for _ in range(3)
        ]
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=stations[0]["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 3600

    def test_line_ticket_downtime_is_multiplied_by_station_count(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        for _ in range(3):
            seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 3 * 3600

    def test_uap_ticket_downtime_is_multiplied_by_sum_of_its_lines_stations(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        for _ in range(2):
            seed_workstation(namespace_id=NS, production_line_id=line1["id"])
        for _ in range(3):
            seed_workstation(namespace_id=NS, production_line_id=line2["id"])
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=uap["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 5 * 3600

    def test_plant_wide_ticket_weight_is_total_station_count_in_namespace(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        for _ in range(5):
            seed_workstation(namespace_id=NS, production_line_id=None)
        _seed_issue(
            fake_db,
            # No uap_id/production_line_id/workstation_id at all -> plant scope.
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 5 * 3600

    def test_line_without_referenced_stations_floors_weight_at_one(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        _seed_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 3600

    def test_uap_without_lines_floors_weight_at_one(
        self, client, seed_user, auth_headers, fake_db, seed_uap
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=uap["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 3600

    def test_plant_wide_ticket_with_zero_workstations_floors_weight_at_one(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 3600


# --------------------------------------------------------------------------
# 2. Shared scenario: a line ticket (weight 3, 1h -> weighted 10800s) vs. a
#    station ticket (weight 1, 2h raw -> weighted 7200s) on a different
#    process. Weighted, the line ticket (maintenance) outranks the station
#    ticket (quality) even though its RAW duration is smaller (3600 < 7200)
#    — the reversal every "applies everywhere" assertion below leans on.
# --------------------------------------------------------------------------


@pytest.fixture
def reversal_scenario(fake_db, seed_uap, seed_production_line, seed_workstation):
    _seed_settings(
        fake_db,
        shift_number=2,
        shift_1={"start_time": "06:00", "end_time": "14:00"},
        shift_2={"start_time": "14:00", "end_time": "22:00"},
    )
    uap1 = seed_uap(namespace_id=NS)
    uap2 = seed_uap(namespace_id=NS)
    line1 = seed_production_line(namespace_id=NS, uap_id=uap1["id"])
    line2 = seed_production_line(namespace_id=NS, uap_id=uap2["id"])
    for _ in range(3):
        seed_workstation(namespace_id=NS, production_line_id=line1["id"])
    station_2 = seed_workstation(namespace_id=NS, production_line_id=line2["id"])

    # Ticket A: line1 (weight 3), shift 1, maintenance/breakdown, 1h closed.
    ticket_a = _seed_issue(
        fake_db,
        down_time_scope="production line",
        production_line_id=line1["id"],
        shift=1,
        down_time_type=DownTimeType.BREAKDOWN.value,
        process=Process.MAINTENANCE.value,
        status=DownTimeStatus.CLOSED.value,
        created_at=_utc(7),
        resolved_at=_utc(8),
        resolved_by="agent-1",
    )
    # Ticket B: station_2 on line2 (weight 1), shift 2, quality, 2h closed.
    ticket_b = _seed_issue(
        fake_db,
        down_time_scope="work station",
        workstation_id=station_2["id"],
        production_line_id=line2["id"],
        shift=2,
        down_time_type=DownTimeType.QUALITY_ISSUE.value,
        process=Process.QUALITY.value,
        status=DownTimeStatus.CLOSED.value,
        created_at=_utc(15),
        resolved_at=_utc(17),
        resolved_by="agent-2",
    )
    return {
        "uap1": uap1,
        "uap2": uap2,
        "line1": line1,
        "line2": line2,
        "ticket_a": ticket_a,
        "ticket_b": ticket_b,
    }


class TestWeightingAppliesToDowntimeAggregations:
    def test_overall_downtime_seconds_is_weighted_sum(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        owner = _owner(seed_user)
        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        # A: 3 * 3600 = 10800. B: 1 * 7200 = 7200. Total 18000.
        assert res.json()["data"]["overall"]["downtime_seconds"] == 18000

    def test_by_shift_downtime_is_weighted(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        owner = _owner(seed_user)
        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_shift = {row["id"]: row for row in res.json()["data"]["by_shift"]}
        assert by_shift["1"]["kpis"]["downtime_seconds"] == 10800
        assert by_shift["2"]["kpis"]["downtime_seconds"] == 7200

    def test_by_location_downtime_is_weighted(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        owner = _owner(seed_user)
        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = {row["id"]: row for row in res.json()["data"]["by_location"]}
        assert all(row["kind"] == "uap" for row in res.json()["data"]["by_location"])
        assert by_location[reversal_scenario["uap1"]["id"]]["kpis"]["downtime_seconds"] == 10800
        assert by_location[reversal_scenario["uap2"]["id"]]["kpis"]["downtime_seconds"] == 7200

    def test_by_type_downtime_is_weighted(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        owner = _owner(seed_user)
        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_type = {row["id"]: row for row in res.json()["data"]["by_type"]}
        assert by_type["break_down"]["kpis"]["downtime_seconds"] == 10800
        assert by_type["quality_issue"]["kpis"]["downtime_seconds"] == 7200

    def test_pareto_by_process_share_reflects_weight_and_reverses_raw_duration_order(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        """Raw durations alone would rank quality (7200s) above maintenance
        (3600s); weighted, maintenance (10800s) outranks quality (7200s)."""
        owner = _owner(seed_user)
        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        pareto = res.json()["data"]["pareto_by_process"]
        assert [row["id"] for row in pareto] == [Process.MAINTENANCE.value, Process.QUALITY.value]
        assert pareto[0]["share"] == pytest.approx(10800 / 18000, abs=1e-4)
        assert pareto[1]["share"] == pytest.approx(7200 / 18000, abs=1e-4)

    def test_drilldown_downtime_by_shift_and_type_bars_are_weighted(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{reversal_scenario['uap1']['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        shift_bars = {bar["id"]: bar["value"] for bar in data["downtime_by_shift"]}
        type_bars = {bar["id"]: bar["value"] for bar in data["downtime_by_type"]}
        assert shift_bars["1"] == 10800
        assert type_bars["break_down"] == 10800

    def test_drilldown_children_downtime_is_weighted(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{reversal_scenario['uap1']['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["children_hint_key"] == "dashboard.drill.linesHint"
        child = next(
            row for row in data["children"] if row["id"] == reversal_scenario["line1"]["id"]
        )
        assert child["kpis"]["downtime_seconds"] == 10800

    def test_daily_duration_metric_is_weighted(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/daily",
            params={"metric": "duration", "scope_kind": "plant", **_period()},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        points = {p["date"]: p["value"] for p in res.json()["data"]["points"]}
        assert points["2026-01-15"] == 18000


class TestWeightingExcludedFromEffortMetrics:
    """§5bis.1bis explicitly carves out `count`/MTTR/repair-by-process/agent
    bars from the weighting — these tests would fail if someone accidentally
    threaded `weight_of` into any of them."""

    def test_count_is_unweighted(self, client, seed_user, auth_headers, reversal_scenario):
        owner = _owner(seed_user)
        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["count"] == 2

    def test_mttr_seconds_is_unweighted(self, client, seed_user, auth_headers, reversal_scenario):
        owner = _owner(seed_user)
        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        # mean(3600, 7200) = 5400, regardless of weight 3 vs 1.
        assert res.json()["data"]["overall"]["mttr_seconds"] == 5400

    def test_repair_by_process_is_unweighted(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        owner = _owner(seed_user)
        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        repair = {bar["id"]: bar["value"] for bar in res.json()["data"]["repair_by_process"]}
        assert repair[Process.MAINTENANCE.value] == 3600
        assert repair[Process.QUALITY.value] == 7200

    def test_mttr_by_agent_and_count_by_agent_are_unweighted(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"process:{Process.MAINTENANCE.value}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        mttr_row = next(r for r in data["mttr_by_agent"] if r["id"] == "agent-1")
        count_row = next(r for r in data["count_by_agent"] if r["id"] == "agent-1")
        assert mttr_row["value"] == 3600
        assert count_row["value"] == 1

    def test_daily_count_metric_is_unweighted(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/daily",
            params={"metric": "count", "scope_kind": "plant", **_period()},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        points = {p["date"]: p["value"] for p in res.json()["data"]["points"]}
        assert points["2026-01-15"] == 2

    def test_daily_mttr_metric_is_unweighted(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/daily",
            params={"metric": "mttr", "scope_kind": "plant", **_period()},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        points = {p["date"]: p["value"] for p in res.json()["data"]["points"]}
        assert points["2026-01-15"] == 5400


# --------------------------------------------------------------------------
# 3. `availability` removed (§5bis.3).
# --------------------------------------------------------------------------


class TestAvailabilityRemoved:
    def test_dashboard_response_has_no_availability_key(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        owner = _owner(seed_user)
        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert "availability" not in data["overall"]
        for section in ("by_shift", "by_location", "by_type"):
            for row in data[section]:
                assert "availability" not in row["kpis"]

    def test_drilldown_response_has_no_availability_key(
        self, client, seed_user, auth_headers, reversal_scenario
    ):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{reversal_scenario['uap1']['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert "availability" not in data["kpis"]
        assert "availability" not in data


# --------------------------------------------------------------------------
# 4. MTBF — shift window with no break deducted (§5bis.4).
# --------------------------------------------------------------------------


class TestMtbfWithoutBreakDeduction:
    def test_mtbf_equals_full_shift_window_over_ticket_count(
        self, client, seed_user, auth_headers, fake_db
    ):
        """Single shift 06:00->14:00 = 8h = 28800s planned/day, queried over
        exactly one already-elapsed day (no proration) with 2 tickets ->
        mtbf = 28800 / 2 = 14400, matching the spec's own worked example."""
        owner = _owner(seed_user)
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        _seed_issue(fake_db, status=DownTimeStatus.PENDING.value, created_at=_utc(7))
        _seed_issue(fake_db, status=DownTimeStatus.PENDING.value, created_at=_utc(9))

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["mtbf_seconds"] == 14400

    def test_legacy_stored_break_minutes_does_not_change_mtbf(
        self, client, seed_user, auth_headers, fake_db
    ):
        """A settings document written before `break_minutes` was removed
        (still carrying the field on its shift) reads back fine and doesn't
        change the MTBF computation — it's simply ignored."""
        owner = _owner(seed_user)
        _seed_settings(
            fake_db,
            shift_number=1,
            shift_1={"start_time": "06:00", "end_time": "14:00", "break_minutes": 30},
        )
        _seed_issue(fake_db, status=DownTimeStatus.PENDING.value, created_at=_utc(7))
        _seed_issue(fake_db, status=DownTimeStatus.PENDING.value, created_at=_utc(9))

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["mtbf_seconds"] == 14400


# --------------------------------------------------------------------------
# 5. Carry-over ticket x weighting interaction (fix #1 x §5bis.1bis).
# --------------------------------------------------------------------------


class TestCarryOverTicketWeighting:
    def test_still_open_line_ticket_carried_over_is_clamped_then_weighted(
        self,
        client,
        seed_user,
        auth_headers,
        fake_db,
        seed_uap,
        seed_production_line,
        seed_workstation,
        freeze_kpi_clock,
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        for _ in range(3):
            seed_workstation(namespace_id=NS, production_line_id=line["id"])
        # Opened 5 days before the queried period, still open at "now"
        # (frozen to 2026-01-15 18:00 by `freeze_kpi_clock`).
        _seed_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            status=DownTimeStatus.PENDING.value,
            created_at=_utc(8, day=10),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # Created before the window -> excluded from `count` (current-range
        # only), but its clamped [period_start 00:00, now 18:00] = 18h,
        # weighted by the line's 3 stations -> 3 * 18h = 194400s.
        assert data["overall"]["count"] == 0
        assert data["overall"]["downtime_seconds"] == 3 * 18 * 3600


# --------------------------------------------------------------------------
# 6. Review fix W1 — `down_time_scope` (when present) wins over the most
#    specific stored id.
# --------------------------------------------------------------------------


class TestWeightFollowsStoredScope:
    def test_uap_scoped_ticket_with_narrower_ids_weighs_the_uap_not_the_line(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """`CreateDownTimeIn` requires only the id of the DECLARED scope; it
        doesn't forbid a client from also sending a narrower id (e.g. a
        contextual `production_line_id`/`workstation_id` alongside a UAP-level
        report). Before the fix, `_ticket_weight` picked the most specific id
        present and weighed the line (2 stations) instead of the UAP (5
        stations across its 2 lines)."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        for _ in range(2):
            seed_workstation(namespace_id=NS, production_line_id=line1["id"])
        for _ in range(3):
            seed_workstation(namespace_id=NS, production_line_id=line2["id"])
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=uap["id"],
            production_line_id=line1["id"],
            workstation_id="some-station-in-line1",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        # UAP-wide weight (5), not the line's (2) or the workstation's (1).
        assert res.json()["data"]["overall"]["downtime_seconds"] == 5 * 3600

    def test_legacy_ticket_without_down_time_scope_still_uses_id_inference(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """A document written before `down_time_scope` existed (or otherwise
        missing it) keeps the old most-specific-id inference rather than
        collapsing to plant-wide."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        for _ in range(4):
            seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_issue(
            fake_db,
            down_time_scope=None,
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 4 * 3600


# --------------------------------------------------------------------------
# 7. Review fix W3 — a `type` drill-down no longer fixes `process`.
# --------------------------------------------------------------------------


class TestTypeDrilldownProcessNoLongerImplied:
    def test_type_spanning_two_processes_still_returns_pareto_and_repair_by_process(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        # Two BREAKDOWN tickets whose own stored `process` disagree (allowed
        # since revision 2 reads `process` off the ticket, not the type).
        _seed_issue(
            fake_db,
            down_time_type=DownTimeType.BREAKDOWN.value,
            process=Process.MAINTENANCE.value,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )
        _seed_issue(
            fake_db,
            down_time_type=DownTimeType.BREAKDOWN.value,
            process=Process.PRODUCTION.value,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(9),
            resolved_at=_utc(11),
        )

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": "type:break_down"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert "pareto_by_process" in data
        assert "repair_by_process" in data
        pareto_ids = {row["id"] for row in data["pareto_by_process"]}
        assert pareto_ids == {Process.MAINTENANCE.value, Process.PRODUCTION.value}
        repair_ids = {bar["id"] for bar in data["repair_by_process"]}
        assert repair_ids == {Process.MAINTENANCE.value, Process.PRODUCTION.value}
        # `downtime_by_type` stays suppressed — `type` is still the fixed
        # dimension of the path itself.
        assert "downtime_by_type" not in data


# --------------------------------------------------------------------------
# 8. Review fix W5 — `/kpi/daily` only loads the location hierarchy when it's
#    actually needed (non-plant scope, or `metric == "duration"`).
# --------------------------------------------------------------------------


class TestDailyLazyHierarchy:
    def _count_hierarchy_calls(self, monkeypatch):
        calls = {"n": 0}
        original = kpi_services_module._location_hierarchy

        def _counting(*args, **kwargs):
            calls["n"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(kpi_services_module, "_location_hierarchy", _counting)
        return calls

    def test_plant_scope_count_metric_skips_hierarchy(
        self, client, seed_user, auth_headers, fake_db, monkeypatch
    ):
        owner = _owner(seed_user)
        calls = self._count_hierarchy_calls(monkeypatch)

        res = client.get(
            "/kpi/daily",
            params={"metric": "count", "scope_kind": "plant", **_period()},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        assert calls["n"] == 0

    def test_plant_scope_mttr_metric_skips_hierarchy(
        self, client, seed_user, auth_headers, fake_db, monkeypatch
    ):
        owner = _owner(seed_user)
        calls = self._count_hierarchy_calls(monkeypatch)

        res = client.get(
            "/kpi/daily",
            params={"metric": "mttr", "scope_kind": "plant", **_period()},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        assert calls["n"] == 0

    def test_plant_scope_duration_metric_loads_hierarchy(
        self, client, seed_user, auth_headers, fake_db, monkeypatch
    ):
        owner = _owner(seed_user)
        calls = self._count_hierarchy_calls(monkeypatch)

        res = client.get(
            "/kpi/daily",
            params={"metric": "duration", "scope_kind": "plant", **_period()},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        assert calls["n"] == 1

    def test_non_plant_scope_count_metric_still_loads_hierarchy(
        self, client, seed_user, auth_headers, fake_db, seed_uap, monkeypatch
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        calls = self._count_hierarchy_calls(monkeypatch)

        res = client.get(
            "/kpi/daily",
            params={"metric": "count", "scope_kind": "uap", "scope_id": uap["id"], **_period()},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        assert calls["n"] == 1
