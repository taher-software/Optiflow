"""Deep API-level coverage for `GET /kpi/dashboard|drilldown|daily`, per
`.claude/specs/kpi-dashboard.md` §3/§5bis: exact KPI numbers over a seeded
multi-shift, multi-UAP namespace, tenant isolation, drill-down dimension
narrowing, daily bucketing in the namespace's timezone, and period-range
edge cases.

Top-level shape / empty-namespace / basic-role smoke tests live in
`tests/api/test_kpi.py`; this file owns the exact-numbers and multi-step
scenarios called out in the KPI test Work Unit.
"""

import uuid
from datetime import date, datetime

import pytest

import src.app.routers.kpi.services as kpi_services_module
from src.app.core.firestore import NAMESPACE_SETTINGS_COLLECTION, SETTINGS_SUBCOLLECTION
from src.app.globals.enum import DownTimeStatus, DownTimeType, Process, Role

NS = "ns-kpi-dash"
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"
TZ = "Europe/Paris"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS, timezone=TZ, company_name="Acme Plant")


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
    now_iso = datetime(2026, 1, 15, 9, 0, tzinfo=None).isoformat()
    issue = {
        "id": str(uuid.uuid4()),
        "namespace_id": namespace_id,
        "created_at": now_iso,
        "updated_at": now_iso,
        "down_time_scope": "plant",
        "uap_id": None,
        "production_line_id": None,
        "workstation_id": None,
        "down_time_type": DownTimeType.BREAKDOWN.value,
        "process": Process.MAINTENANCE.value,
        "status": DownTimeStatus.PENDING.value,
        "created_by": "creator-1",
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


@pytest.fixture
def freeze_kpi_clock(monkeypatch):
    """Pins `services.datetime.now(tz)` to a fixed instant (2026-01-15
    18:00, localized to the query tz — after every seeded ticket's
    created/resolved times, since `_ticket_downtime_seconds` clamps to
    "now" even for closed tickets) so open-ticket "now" clamping is
    deterministic. `freezegun` is not among this project's installed test
    dependencies (see `tests/async_jobs/test_add_down_time.py`
    ::freeze_add_down_time_clock`), so this patches the module's imported
    `datetime` name directly — same effect, scoped to this module only."""
    fixed = datetime(2026, 1, 15, 18, 0, 0)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.replace(tzinfo=tz) if tz else fixed

    monkeypatch.setattr(kpi_services_module, "datetime", _FixedDatetime)
    return fixed


def _paris(hour, minute=0, day=15):
    return f"2026-01-{day:02d}T{hour:02d}:{minute:02d}:00+01:00"


@pytest.fixture
def seeded_scenario(fake_db, seed_uap, seed_production_line):
    """Seeds the shared multi-shift / multi-UAP / mixed-ticket scenario used
    by the dashboard + several drill-down tests. Returns the seeded ids and
    tickets so individual tests can assert against them."""
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

    # Ticket A: uap1 (via line1), shift 1, breakdown/maintenance, closed 1h.
    ticket_a = _seed_issue(
        fake_db,
        production_line_id=line1["id"],
        shift=1,
        down_time_type=DownTimeType.BREAKDOWN.value,
        status=DownTimeStatus.CLOSED.value,
        created_at=_paris(7, 0),
        resolved_at=_paris(8, 0),
        resolved_by="agent-1",
    )
    # Ticket B: uap2 (via line2), shift 2, quality issue, closed 2h.
    ticket_b = _seed_issue(
        fake_db,
        production_line_id=line2["id"],
        shift=2,
        down_time_type=DownTimeType.QUALITY_ISSUE.value,
        process=Process.QUALITY.value,
        status=DownTimeStatus.CLOSED.value,
        created_at=_paris(15, 0),
        resolved_at=_paris(17, 0),
        resolved_by="agent-2",
    )
    # Ticket C: uap1 (via line1), NO shift key at all, breakdown, still
    # open at freeze_kpi_clock's "now" (18:00) -> 30min downtime.
    ticket_c = _seed_issue(
        fake_db,
        production_line_id=line1["id"],
        down_time_type=DownTimeType.BREAKDOWN.value,
        status=DownTimeStatus.PENDING.value,
        created_at=_paris(17, 30),
    )
    ticket_c.pop("shift", None)
    fake_db.collection(DOWN_TIME_COLLECTION).document(NS).collection(
        ISSUES_SUBCOLLECTION
    ).document(ticket_c["id"]).set(ticket_c)

    return {
        "uap1": uap1,
        "uap2": uap2,
        "line1": line1,
        "line2": line2,
        "ticket_a": ticket_a,
        "ticket_b": ticket_b,
        "ticket_c": ticket_c,
    }


def _period(day=15):
    d = date(2026, 1, day).isoformat()
    return {"from": d, "to": d}


class TestDashboardExactNumbers:
    def test_overall_and_breakdowns_match_seeded_scenario(
        self, client, seed_user, auth_headers, seeded_scenario, freeze_kpi_clock
    ):
        owner = _owner(seed_user)

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # overall: downtime = 3600 (A) + 7200 (B) + 1800 (C) = 12600s.
        assert data["overall"]["count"] == 3
        assert data["overall"]["downtime_seconds"] == 12600
        # mttr over CLOSED tickets only (A, B): mean(3600, 7200) = 5400.
        assert data["overall"]["mttr_seconds"] == 5400
        # planned (fix #2, no break deducted since revision 2 §5bis.3/4):
        # `freeze_kpi_clock` pins "now" to 18:00 Paris, BEFORE the queried
        # day's end -> the day is prorated instead of counted in full.
        # Shift 1 (06:00-14:00) is fully elapsed by 18:00 (8h = 28800s);
        # shift 2 (14:00-22:00) is half elapsed (4h of its 8h window ->
        # 0.5 * 28800 = 14400s). planned = 28800 + 14400 = 43200s.
        assert data["overall"]["mtbf_seconds"] == 14400

        # by_shift: ticket C (no `shift` field) excluded entirely.
        by_shift = {row["id"]: row for row in data["by_shift"]}
        assert by_shift.keys() == {"1", "2"}
        assert by_shift["1"]["kpis"]["count"] == 1
        assert by_shift["1"]["kpis"]["downtime_seconds"] == 3600
        assert by_shift["2"]["kpis"]["count"] == 1
        assert by_shift["2"]["kpis"]["downtime_seconds"] == 7200

        # by_location: 2 UAPs -> kind "uap". Rows never carry a meaningful
        # per-row planned-time denominator (fix #5).
        by_location = {row["id"]: row for row in data["by_location"]}
        assert all(row["kind"] == "uap" for row in data["by_location"])
        assert by_location[seeded_scenario["uap1"]["id"]]["kpis"]["count"] == 2
        assert by_location[seeded_scenario["uap1"]["id"]]["kpis"]["downtime_seconds"] == 5400
        assert by_location[seeded_scenario["uap1"]["id"]]["kpis"]["mtbf_seconds"] is None
        assert by_location[seeded_scenario["uap2"]["id"]]["kpis"]["count"] == 1
        assert by_location[seeded_scenario["uap2"]["id"]]["kpis"]["downtime_seconds"] == 7200

        # pareto_by_process: quality (B=7200) > maintenance (A+C=5400).
        pareto = data["pareto_by_process"]
        assert [row["id"] for row in pareto] == [
            Process.QUALITY.value,
            Process.MAINTENANCE.value,
        ]
        assert pareto[0]["share"] == pytest.approx(7200 / 12600, abs=1e-4)
        assert pareto[1]["share"] == pytest.approx(5400 / 12600, abs=1e-4)
        assert pareto[0]["cumulative"] == pytest.approx(7200 / 12600, abs=1e-4)
        assert pareto[1]["cumulative"] == pytest.approx(1.0, abs=1e-4)

        # by_type: break_down (A+C) vs quality_issue (B).
        by_type = {row["id"]: row for row in data["by_type"]}
        assert by_type["break_down"]["kpis"]["count"] == 2
        assert by_type["break_down"]["kpis"]["downtime_seconds"] == 5400
        assert by_type["break_down"]["kpis"]["mtbf_seconds"] is None
        assert by_type["quality_issue"]["kpis"]["count"] == 1
        assert by_type["quality_issue"]["kpis"]["downtime_seconds"] == 7200

    def test_tenant_isolation_other_namespace_never_counted(
        self, client, seed_user, seed_namespace, auth_headers, fake_db, seeded_scenario, freeze_kpi_clock
    ):
        other_ns = "ns-kpi-other"
        seed_namespace(id=other_ns, timezone="UTC", company_name="Other Plant")
        _seed_settings(fake_db, namespace_id=other_ns)
        _seed_issue(
            fake_db,
            namespace_id=other_ns,
            status=DownTimeStatus.CLOSED.value,
            created_at=_paris(7, 0),
            resolved_at=_paris(10, 0),
        )

        owner = _owner(seed_user)
        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["count"] == 3


class TestCarryOverTickets:
    """Fix #1 — a ticket that started before the queried period but is still
    "live" for it (still open, or closed but resolved inside the window)
    must show up in downtime-based aggregations, not be silently dropped by
    the plain `created_at` range query. `count`/`mttr` stay on the
    current-range query only (unaffected by carry-overs)."""

    def test_still_open_ticket_from_before_window_counts_in_overall_and_location(
        self,
        client,
        seed_user,
        auth_headers,
        fake_db,
        seed_uap,
        seed_production_line,
        freeze_kpi_clock,
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        seed_uap(namespace_id=NS)  # 2nd UAP -> by_location groups by "uap".
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        _seed_issue(
            fake_db,
            production_line_id=line["id"],
            status=DownTimeStatus.PENDING.value,
            created_at=_paris(8, 0, day=10),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # Created before the window -> excluded from `count` (current-range
        # only), but its clamped [period_start 00:00, now 18:00] = 18h
        # downtime still counts.
        assert data["overall"]["count"] == 0
        assert data["overall"]["downtime_seconds"] == 18 * 3600
        by_location = {row["id"]: row for row in data["by_location"]}
        assert by_location[uap["id"]]["kpis"]["downtime_seconds"] == 18 * 3600

    def test_closed_ticket_resolved_inside_window_but_created_before_counts(
        self, client, seed_user, auth_headers, fake_db, freeze_kpi_clock
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=_paris(8, 0, day=9),
            resolved_at=_paris(10, 0, day=15),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        assert data["overall"]["count"] == 0
        # Clamped to [period_start 00:00, resolved_at 10:00] = 10h.
        assert data["overall"]["downtime_seconds"] == 10 * 3600
        # No CLOSED ticket in the current-range query -> mttr stays 0.
        assert data["overall"]["mttr_seconds"] == 0

    def test_ticket_resolved_before_window_is_not_carried_over(
        self, client, seed_user, auth_headers, fake_db, freeze_kpi_clock
    ):
        """A ticket both created AND resolved before the window is simply
        history — it must not leak into the period at all."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=_paris(8, 0, day=9),
            resolved_at=_paris(10, 0, day=9),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        assert data["overall"]["count"] == 0
        assert data["overall"]["downtime_seconds"] == 0


class TestDrilldownDeep:
    def test_uap_to_line_returns_station_children(
        self, client, seed_user, auth_headers, seeded_scenario, seed_workstation, freeze_kpi_clock
    ):
        owner = _owner(seed_user)
        station = seed_workstation(
            namespace_id=NS, production_line_id=seeded_scenario["line1"]["id"]
        )

        res = client.get(
            "/kpi/drilldown",
            params={
                **_period(),
                "path": f"uap:{seeded_scenario['uap1']['id']}>line:{seeded_scenario['line1']['id']}",
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["children_hint_key"] == "dashboard.drill.stationsHint"
        assert [row["kind"] for row in data["children"]] == ["station"] * len(data["children"])
        assert any(row["id"] == station["id"] for row in data["children"])

    def test_shift_in_path_suppresses_by_shift_and_narrows_kpis(
        self, client, seed_user, auth_headers, seeded_scenario, freeze_kpi_clock
    ):
        owner = _owner(seed_user)

        dashboard_res = client.get(
            "/kpi/dashboard", params=_period(), headers=auth_headers(owner)
        )
        overall_count = dashboard_res.json()["data"]["overall"]["count"]

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": "shift:1"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        # `response_model_exclude_none=True` (fix #12) omits a suppressed
        # section entirely rather than sending it as `null`.
        assert "downtime_by_shift" not in data
        assert data["kpis"]["count"] == 1
        assert data["kpis"]["count"] != overall_count

    def test_type_in_path_suppresses_process_sections_and_type_section(
        self, client, seed_user, auth_headers, seeded_scenario, freeze_kpi_clock
    ):
        """Client decision (revises review fix W3): a downtime TYPE is
        analyzed by WHO intervenes on it, not by process, so a `type` step
        fixes `process` again — `pareto_by_process`/`repair_by_process` are
        suppressed for a type slice (along with `downtime_by_type`, since
        `type` is the fixed dimension itself), while the by-agent sections
        (fix #13) are what a type drill-down surfaces instead."""
        owner = _owner(seed_user)

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": "type:break_down"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert "pareto_by_process" not in data
        assert "repair_by_process" not in data
        assert "downtime_by_type" not in data
        assert data["kpis"]["count"] == 2
        # A `type` step still surfaces the agent sections (a selected
        # process, direct or via type, returns them).
        assert data["mttr_by_agent"] is not None
        assert data["count_by_agent"] is not None

    def test_process_in_path_attributes_mttr_by_agent_with_resolved_names(
        self, client, seed_user, auth_headers, seeded_scenario, fake_db, freeze_kpi_clock
    ):
        owner = _owner(seed_user)
        seed_user(
            id="agent-1",
            namespace_id=NS,
            role=Role.MAINTENANCE_AGENT.value,
            first_name="Jane",
            last_name="Doe",
        )

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"process:{Process.MAINTENANCE.value}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["mttr_by_agent"] is not None
        assert data["count_by_agent"] is not None
        agent_row = next(r for r in data["mttr_by_agent"] if r["id"] == "agent-1")
        assert agent_row["label"] == "Jane Doe"
        assert agent_row["value"] == 3600
        count_row = next(r for r in data["count_by_agent"] if r["id"] == "agent-1")
        assert count_row["value"] == 1

    def test_process_and_shift_query_params_narrow_results(
        self, client, seed_user, auth_headers, seeded_scenario, freeze_kpi_clock
    ):
        owner = _owner(seed_user)

        res = client.get(
            "/kpi/drilldown",
            params={
                **_period(),
                "path": f"uap:{seeded_scenario['uap1']['id']}",
                "process": Process.MAINTENANCE.value,
                "shift": "1",
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        # uap1 has tickets A (shift 1) and C (no shift) — only A matches.
        assert data["kpis"]["count"] == 1
        assert data["kpis"]["downtime_seconds"] == 3600

    def test_children_derive_from_deepest_location_step_not_plant_top_level(
        self, client, seed_user, auth_headers, seeded_scenario, freeze_kpi_clock
    ):
        """Fix #4 — `uap:A>process:maintenance` must return uap A's own
        lines as `children` (the deepest LOCATION step in the path, `uap`),
        NOT the plant-wide top location level (which, with 2 UAPs, would
        wrongly include uap A itself as a child of itself)."""
        owner = _owner(seed_user)
        uap1_id = seeded_scenario["uap1"]["id"]

        res = client.get(
            "/kpi/drilldown",
            params={
                **_period(),
                "path": f"uap:{uap1_id}>process:{Process.MAINTENANCE.value}",
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        assert data["children_hint_key"] == "dashboard.drill.linesHint"
        assert data["children"] is not None
        child_ids = {row["id"] for row in data["children"]}
        assert uap1_id not in child_ids
        assert seeded_scenario["line1"]["id"] in child_ids
        assert all(row["kind"] == "line" for row in data["children"])


class TestDailyDeep:
    def test_date_bucketing_uses_namespace_timezone(
        self, client, seed_user, auth_headers, fake_db, seed_namespace
    ):
        ns = "ns-kpi-daily-tz"
        seed_namespace(id=ns, timezone=TZ, company_name="TZ Plant")
        owner = _owner(seed_user, namespace_id=ns)
        # 23:30 UTC on the 15th == 00:30 Paris on the 16th.
        _seed_issue(
            fake_db,
            namespace_id=ns,
            created_at="2026-01-15T23:30:00+00:00",
            status=DownTimeStatus.PENDING.value,
        )

        res = client.get(
            "/kpi/daily",
            params={
                "metric": "count",
                "scope_kind": "plant",
                "from": "2026-01-15",
                "to": "2026-01-16",
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        points = {p["date"]: p["value"] for p in res.json()["data"]["points"]}
        assert points["2026-01-15"] == 0
        assert points["2026-01-16"] == 1

    def test_one_point_per_day_and_count_metric_per_day(
        self, client, seed_user, auth_headers, fake_db, seed_namespace
    ):
        ns = "ns-kpi-daily-count"
        seed_namespace(id=ns, timezone="UTC", company_name="Count Plant")
        owner = _owner(seed_user, namespace_id=ns)
        _seed_issue(fake_db, namespace_id=ns, created_at="2026-02-01T10:00:00+00:00")
        _seed_issue(fake_db, namespace_id=ns, created_at="2026-02-02T10:00:00+00:00")
        _seed_issue(fake_db, namespace_id=ns, created_at="2026-02-02T11:00:00+00:00")
        # 2026-02-03 has no tickets at all.

        res = client.get(
            "/kpi/daily",
            params={
                "metric": "count",
                "scope_kind": "plant",
                "from": "2026-02-01",
                "to": "2026-02-03",
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        points = res.json()["data"]["points"]
        assert [p["date"] for p in points] == ["2026-02-01", "2026-02-02", "2026-02-03"]
        assert [p["value"] for p in points] == [1, 2, 0]

    def test_mttr_metric_is_zero_on_days_with_no_closed_tickets(
        self, client, seed_user, auth_headers, fake_db, seed_namespace
    ):
        ns = "ns-kpi-daily-mttr"
        seed_namespace(id=ns, timezone="UTC", company_name="Mttr Plant")
        owner = _owner(seed_user, namespace_id=ns)
        _seed_issue(
            fake_db,
            namespace_id=ns,
            status=DownTimeStatus.CLOSED.value,
            created_at="2026-03-01T08:00:00+00:00",
            resolved_at="2026-03-01T09:00:00+00:00",
        )
        _seed_issue(
            fake_db,
            namespace_id=ns,
            status=DownTimeStatus.PENDING.value,
            created_at="2026-03-02T08:00:00+00:00",
        )

        res = client.get(
            "/kpi/daily",
            params={
                "metric": "mttr",
                "scope_kind": "plant",
                "from": "2026-03-01",
                "to": "2026-03-02",
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        points = {p["date"]: p["value"] for p in res.json()["data"]["points"]}
        assert points["2026-03-01"] == 3600
        assert points["2026-03-02"] == 0

    def test_scope_kind_uap_filters_via_workstation_rollup(
        self,
        client,
        seed_user,
        auth_headers,
        fake_db,
        seed_namespace,
        seed_uap,
        seed_production_line,
        seed_workstation,
    ):
        ns = "ns-kpi-daily-scope"
        seed_namespace(id=ns, timezone="UTC", company_name="Scope Plant")
        owner = _owner(seed_user, namespace_id=ns)
        uap = seed_uap(namespace_id=ns)
        other_uap = seed_uap(namespace_id=ns)
        line = seed_production_line(namespace_id=ns, uap_id=uap["id"])
        station = seed_workstation(namespace_id=ns, production_line_id=line["id"])

        # In-scope: only `workstation_id` is set, rolled up to `uap` via the
        # line.
        _seed_issue(
            fake_db,
            namespace_id=ns,
            workstation_id=station["id"],
            created_at="2026-04-01T10:00:00+00:00",
        )
        # Out of scope: belongs to the other UAP.
        _seed_issue(
            fake_db,
            namespace_id=ns,
            uap_id=other_uap["id"],
            created_at="2026-04-01T11:00:00+00:00",
        )

        res = client.get(
            "/kpi/daily",
            params={
                "metric": "count",
                "scope_kind": "uap",
                "scope_id": uap["id"],
                "from": "2026-04-01",
                "to": "2026-04-01",
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        points = res.json()["data"]["points"]
        assert points == [{"date": "2026-04-01", "value": 1}]

    def test_carry_over_ticket_duration_attributed_to_first_day(
        self, client, seed_user, auth_headers, fake_db, seed_namespace
    ):
        """Fix #1 — `duration` folds in carry-over tickets too, attributed
        wholly to the window's first day (documented simplification vs. a
        per-day split); `count` does not (current-range only)."""
        ns = "ns-kpi-daily-carryover"
        seed_namespace(id=ns, timezone="UTC", company_name="Carryover Plant")
        owner = _owner(seed_user, namespace_id=ns)
        _seed_issue(
            fake_db,
            namespace_id=ns,
            status=DownTimeStatus.PENDING.value,
            created_at="2026-06-01T08:00:00+00:00",
        )

        res = client.get(
            "/kpi/daily",
            params={
                "metric": "duration",
                "scope_kind": "plant",
                "from": "2026-06-05",
                "to": "2026-06-06",
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        points = {p["date"]: p["value"] for p in res.json()["data"]["points"]}
        assert points["2026-06-05"] > 0
        assert points["2026-06-06"] == 0

        count_res = client.get(
            "/kpi/daily",
            params={
                "metric": "count",
                "scope_kind": "plant",
                "from": "2026-06-05",
                "to": "2026-06-06",
            },
            headers=auth_headers(owner),
        )
        count_points = {p["date"]: p["value"] for p in count_res.json()["data"]["points"]}
        assert count_points["2026-06-05"] == 0
        assert count_points["2026-06-06"] == 0


class TestNamespaceMetaShifts:
    """`namespace.shifts` — the real shift clock windows the frontend must
    display next to a shift label (e.g. "Équipe 2 (14h-22h)"), instead of a
    hardcoded table. Reuses `_configured_shifts` internally (services.py) —
    these tests only check the field is threaded through onto the payload
    correctly, not the selection logic itself (covered by
    `test_kpi_helpers.py`)."""

    def test_three_shifts_all_configured_returns_ordered_windows(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(
            fake_db,
            shift_number=3,
            shift_1={"start_time": "06:00", "end_time": "14:00"},
            shift_2={"start_time": "14:00", "end_time": "22:00"},
            shift_3={"start_time": "22:00", "end_time": "06:00"},
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        shifts = res.json()["data"]["namespace"]["shifts"]

        assert shifts == [
            {"id": "1", "start_time": "06:00", "end_time": "14:00"},
            {"id": "2", "start_time": "14:00", "end_time": "22:00"},
            {"id": "3", "start_time": "22:00", "end_time": "06:00"},
        ]

    def test_single_shift_with_no_configured_window_returns_empty_list(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, shift_number=1)  # shift_1/2/3 all None.

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        assert data["namespace"]["shift_number"] == 1
        assert data["namespace"]["shifts"] == []

    def test_namespace_with_no_settings_document_returns_empty_list(
        self, client, seed_user, auth_headers
    ):
        # No `_seed_settings` call at all -> `_namespace_context` defaults to
        # `{}`, matching the empty-namespace smoke test in `test_kpi.py`.
        owner = _owner(seed_user)

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        assert data["namespace"]["shifts"] == []

    def test_corrupted_shift_window_is_dropped_but_shift_number_unaffected(
        self, client, seed_user, auth_headers, fake_db
    ):
        """A `shift_number` of 3 with one unparsable window still reports 3
        (`by_shift`/MTBF behavior, unaffected by this unit), but `shifts`
        only carries the 2 usable windows — never a partial/garbage entry."""
        owner = _owner(seed_user)
        _seed_settings(
            fake_db,
            shift_number=3,
            shift_1={"start_time": "06:00", "end_time": "14:00"},
            shift_2={"start_time": "not-a-time", "end_time": "22:00"},
            shift_3={"start_time": "22:00", "end_time": "06:00"},
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        assert data["namespace"]["shift_number"] == 3
        assert data["namespace"]["shifts"] == [
            {"id": "1", "start_time": "06:00", "end_time": "14:00"},
            {"id": "3", "start_time": "22:00", "end_time": "06:00"},
        ]

    def test_midnight_wrapping_window_is_returned_as_stored(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(
            fake_db,
            shift_number=1,
            shift_1={"start_time": "22:00", "end_time": "06:00"},
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        assert data["namespace"]["shifts"] == [
            {"id": "1", "start_time": "22:00", "end_time": "06:00"}
        ]


class TestOthersTypeSlug:
    def test_others_type_appears_in_by_type_and_downtime_by_type(
        self, client, seed_user, auth_headers, fake_db, freeze_kpi_clock
    ):
        """Fix #14 — an OTHERS ticket now has an "others" slug id, so it
        shows up in `by_type`/`downtime_by_type` instead of being counted in
        `overall` but invisible from every type-keyed breakdown."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        _seed_issue(
            fake_db,
            down_time_type=DownTimeType.OTHERS.value,
            status=DownTimeStatus.CLOSED.value,
            created_at=_paris(8, 0),
            resolved_at=_paris(9, 0),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        assert data["overall"]["downtime_seconds"] == 3600
        by_type = {row["id"]: row for row in data["by_type"]}
        assert "others" in by_type
        assert by_type["others"]["kpis"]["downtime_seconds"] == 3600


class TestPeriodEdgeCases:
    def test_from_equals_to_is_a_single_valid_day(
        self, client, seed_user, seed_namespace, auth_headers, fake_db
    ):
        ns = "ns-kpi-period-single"
        seed_namespace(id=ns, timezone="UTC", company_name="Single Day Plant")
        _seed_settings(fake_db, namespace_id=ns)
        owner = _owner(seed_user, namespace_id=ns)

        res = client.get(
            "/kpi/dashboard",
            params={"from": "2026-05-01", "to": "2026-05-01"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text

    def test_to_before_from_returns_422(self, client, seed_user, auth_headers):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/dashboard",
            params={"from": "2026-05-10", "to": "2026-05-01"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 422

    def test_daily_to_before_from_returns_422(self, client, seed_user, auth_headers):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/daily",
            params={
                "metric": "count",
                "scope_kind": "plant",
                "from": "2026-05-10",
                "to": "2026-05-01",
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 422

    def test_drilldown_to_before_from_returns_422(self, client, seed_user, auth_headers):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/drilldown",
            params={"from": "2026-05-10", "to": "2026-05-01", "path": "uap:x"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 422

    def test_span_over_366_days_returns_422(self, client, seed_user, auth_headers):
        """Fix #7."""
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/dashboard",
            params={"from": "2025-01-01", "to": "2026-01-03"},  # 367-day gap
            headers=auth_headers(owner),
        )
        assert res.status_code == 422

    def test_span_of_exactly_366_days_is_ok(self, client, seed_user, auth_headers):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/dashboard",
            params={"from": "2025-01-01", "to": "2026-01-01"},  # 365 days inclusive
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text


class TestQueryParamValidation:
    """Fix #10/#11 — typo'd enum-ish query params and an over-long/over-deep
    `path` are rejected by FastAPI/pydantic (422) before ever reaching the
    service layer."""

    def test_drilldown_invalid_process_returns_422(self, client, seed_user, auth_headers):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": "uap:x", "process": "not-a-process"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 422

    def test_drilldown_invalid_shift_returns_422(self, client, seed_user, auth_headers):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": "uap:x", "shift": "4"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 422

    def test_daily_invalid_process_returns_422(self, client, seed_user, auth_headers):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/daily",
            params={
                "metric": "count",
                "scope_kind": "plant",
                "process": "not-a-process",
                **_period(),
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 422

    def test_daily_invalid_shift_returns_422(self, client, seed_user, auth_headers):
        owner = _owner(seed_user)
        res = client.get(
            "/kpi/daily",
            params={
                "metric": "count",
                "scope_kind": "plant",
                "shift": "0",
                **_period(),
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 422

    def test_path_over_max_length_returns_422(self, client, seed_user, auth_headers):
        owner = _owner(seed_user)
        long_path = "uap:" + ("x" * 600)
        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": long_path},
            headers=auth_headers(owner),
        )
        assert res.status_code == 422

    def test_path_over_max_steps_returns_422(self, client, seed_user, auth_headers):
        owner = _owner(seed_user)
        too_many_steps = ">".join(f"shift:{i % 3 + 1}" for i in range(9))
        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": too_many_steps},
            headers=auth_headers(owner),
        )
        assert res.status_code == 422


class TestMtbfPlannedTimeRevision3:
    """§5bis.4bis — a configured mono-shift now has a real window (revision
    3: required from `shift_number == 1`) instead of the 24h/day fallback,
    and its planned time (MTBF's numerator) is net of its break. All 3
    scenarios freeze "now" at 18:00 Paris, strictly after the 06:00-14:00
    shift's raw window closes, so `_shift_seconds_prorated`'s elapsed
    fraction is 1.0 and the full (break-adjusted) per-day planned time
    counts without proration noise."""

    def test_configured_mono_shift_mtbf_is_window_minus_break(
        self, client, seed_user, auth_headers, fake_db, freeze_kpi_clock
    ):
        owner = _owner(seed_user)
        _seed_settings(
            fake_db,
            shift_number=1,
            shift_1={
                "start_time": "06:00",
                "end_time": "14:00",
                "break_start_time": "10:00",
                "break_end_time": "10:30",
            },
        )
        _seed_issue(
            fake_db,
            shift=1,
            status=DownTimeStatus.CLOSED.value,
            created_at=_paris(7, 0),
            resolved_at=_paris(8, 0),
            resolved_by="agent-1",
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # planned = 8h window - 30min break = 27000s; 1 ticket -> mtbf = planned.
        assert data["overall"]["mtbf_seconds"] == 8 * 3600 - 30 * 60

    def test_mtbf_without_pause_is_higher_than_with_pause(
        self, client, seed_user, auth_headers, fake_db, freeze_kpi_clock
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"})
        _seed_issue(
            fake_db,
            shift=1,
            status=DownTimeStatus.CLOSED.value,
            created_at=_paris(7, 0),
            resolved_at=_paris(8, 0),
            resolved_by="agent-1",
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["mtbf_seconds"] == 8 * 3600

    def test_illegible_break_ignored_without_500(
        self, client, seed_user, auth_headers, fake_db, freeze_kpi_clock
    ):
        """A stored break pair that predates request-time validation and is
        outside the shift window (or otherwise invalid) must degrade to "no
        break" rather than 500ing the dashboard request."""
        owner = _owner(seed_user)
        _seed_settings(
            fake_db,
            shift_number=1,
            shift_1={
                "start_time": "06:00",
                "end_time": "14:00",
                "break_start_time": "20:00",
                "break_end_time": "20:30",
            },
        )
        _seed_issue(
            fake_db,
            shift=1,
            status=DownTimeStatus.CLOSED.value,
            created_at=_paris(7, 0),
            resolved_at=_paris(8, 0),
            resolved_by="agent-1",
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        # Break ignored -> full 8h window counts, same as no-break case.
        assert res.json()["data"]["overall"]["mtbf_seconds"] == 8 * 3600
