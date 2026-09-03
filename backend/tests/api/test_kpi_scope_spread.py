"""API-level coverage for `.claude/specs/kpi-scope-spread.md` — the
downward spread of a wide-scope downtime ticket (`plant`/`uap`/`production
line`) into the KPI location breakdown and drill-down/daily scope filter.

The defect this contract fixes: `_resolve_location` (services.py:739) only
rolls a location UP (station -> line -> UAP). A `plant`-scope ticket carries
none of `uap_id`/`production_line_id`/`workstation_id`, so
`_group_tickets_by_location` (:770) drops it from every row of `by_location`,
and `_filter_by_scope` (:1502, used by `/kpi/daily`'s `scope_kind` filter)
drops it from every drill-down. This file exercises the endpoints, not the
helpers directly, mirroring `test_kpi_weighting.py`'s style: seed a
UAP -> line -> workstation hierarchy, seed a ticket with a given
`down_time_scope`, hit `/kpi/dashboard` and `/kpi/daily`, and assert on the
JSON response.

Per §4 of the contract, `count`/`mttr` are explicitly NOT reconciled against
the header when a ticket spreads (each location it touches counts it once) —
that is the intended, documented model, not a bug, and scenario 11 pins it.

All tickets use fixed 2026-01-15 timestamps in the past relative to
wall-clock "now", so the `min(natural_end, now)` clamp never kicks in for
CLOSED tickets and no clock-freezing is needed, EXCEPT the reconciliation
scenario (25) which includes a still-open carry-over ticket and freezes the
clock via `freeze_kpi_clock` for that one test.

Revision 2 (§9 of the contract, 2026-09-02): the gate was reopened once
after a cross-cutting review found two blocking defects this suite's first
pass did not catch. This revision:

- REPLACES scenario 10 (`TestNoUapAndFloor`): §9.3/W4 rules that
  reconciliation (§7) beats the weight floor — a SPREAD ticket no longer
  reaches an empty location at all (no row), while a ticket DECLARED at an
  empty location still floors its own row at 1, never 0.
- ADDS scenarios 19-25 (§9.6): the drill-down header must be weighted by the
  fixed location, not the whole plant (B1); a workstation with no
  `production_line_id` gets an explicit `unassigned` row so the breakdown
  still reconciles with the header (B2); a `uap`-scope ticket carrying only
  a `production_line_id` must still spread from its RESOLVED uap (W2); the
  plant-scope sub-location invariant (§8) must also be enforced at write
  time by `add_down_time`, not just at the HTTP boundary (W5, covered in
  `tests/async_jobs/test_add_down_time.py`, appended there); and a mixed set
  of spread + non-spread + carry-over tickets must still reconcile (§7's
  actual promise, tested outside the single-ticket clean case).
"""

import uuid
from datetime import date, datetime

import pytest

import src.app.routers.kpi.services as kpi_services_module
from src.app.core.firestore import NAMESPACE_SETTINGS_COLLECTION, SETTINGS_SUBCOLLECTION
from src.app.globals.enum import DownTimeStatus, DownTimeType, Process, Role

NS = "ns-kpi-scope-spread"
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS, timezone="UTC", company_name="Spread Plant")


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


def _by_location(res):
    return {row["id"]: row for row in res.json()["data"]["by_location"]}


@pytest.fixture
def freeze_kpi_clock(monkeypatch):
    """Pins `services.datetime.now(tz)` to 2026-01-15 18:00 (same pattern as
    `test_kpi_weighting.py::freeze_kpi_clock`) — only needed for scenario
    25's still-open carry-over ticket, whose downtime clamp's upper bound is
    "now"."""
    fixed = datetime(2026, 1, 15, 18, 0, 0)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.replace(tzinfo=tz) if tz else fixed

    monkeypatch.setattr(kpi_services_module, "datetime", _FixedDatetime)
    return fixed


# --------------------------------------------------------------------------
# Shared 3-UAP hierarchy fixture used by the arithmetic + spread scenarios:
# UAP A = 10 stations, UAP B = 6, UAP C = 4 (20 total), one line per UAP so
# the by-location breakdown kind stays "uap" (`_pick_location_kind` picks
# "uap" whenever there's more than one).
# --------------------------------------------------------------------------


@pytest.fixture
def three_uap_hierarchy(fake_db, seed_uap, seed_production_line, seed_workstation):
    _seed_settings(fake_db)
    uap_a = seed_uap(namespace_id=NS, name="UAP A")
    uap_b = seed_uap(namespace_id=NS, name="UAP B")
    uap_c = seed_uap(namespace_id=NS, name="UAP C")
    line_a = seed_production_line(namespace_id=NS, uap_id=uap_a["id"])
    line_b = seed_production_line(namespace_id=NS, uap_id=uap_b["id"])
    line_c = seed_production_line(namespace_id=NS, uap_id=uap_c["id"])
    for _ in range(10):
        seed_workstation(namespace_id=NS, production_line_id=line_a["id"])
    for _ in range(6):
        seed_workstation(namespace_id=NS, production_line_id=line_b["id"])
    for _ in range(4):
        seed_workstation(namespace_id=NS, production_line_id=line_c["id"])
    return {
        "uap_a": uap_a,
        "uap_b": uap_b,
        "uap_c": uap_c,
        "line_a": line_a,
        "line_b": line_b,
        "line_c": line_c,
    }


# --------------------------------------------------------------------------
# 1/2. Plant ticket spreads into every row, at every breakdown granularity.
# --------------------------------------------------------------------------


class TestPlantTicketSpreadsIntoLocationBreakdown:
    """Scenarios 1-2: a plant-scope ticket must appear in EVERY row of the
    `by_location` breakdown, whichever granularity `_pick_location_kind`
    selects for the namespace's hierarchy (uap / line / station)."""

    def test_plant_ticket_appears_in_every_uap_row(
        self, client, seed_user, auth_headers, fake_db, three_uap_hierarchy
    ):
        owner = _owner(seed_user)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert set(by_location) == {
            three_uap_hierarchy["uap_a"]["id"],
            three_uap_hierarchy["uap_b"]["id"],
            three_uap_hierarchy["uap_c"]["id"],
        }
        for row in by_location.values():
            assert row["kind"] == "uap"
            assert row["kpis"]["downtime_seconds"] > 0

    def test_plant_ticket_appears_in_every_line_row(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Single UAP, multiple lines -> `_pick_location_kind` selects
        "line"; a plant ticket must still reach every line row."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line1["id"])
        seed_workstation(namespace_id=NS, production_line_id=line2["id"])
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert set(by_location) == {line1["id"], line2["id"]}
        for row in by_location.values():
            assert row["kind"] == "line"

    def test_plant_ticket_appears_in_every_station_row(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Single UAP, single line, multiple stations -> `_pick_location_kind`
        selects "station"; a plant ticket must still reach every station
        row."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        stations = [
            seed_workstation(namespace_id=NS, production_line_id=line["id"]) for _ in range(3)
        ]
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert set(by_location) == {s["id"] for s in stations}
        for row in by_location.values():
            assert row["kind"] == "station"


# --------------------------------------------------------------------------
# 3. The arithmetic — the contract's own worked example.
# --------------------------------------------------------------------------


class TestOwnSharesWeighting:
    def test_plant_ticket_uap_rows_carry_their_own_share_and_reconcile_with_header(
        self, client, seed_user, auth_headers, fake_db, three_uap_hierarchy
    ):
        """10/6/4 stations, a 30-minute plant-wide stop -> UAP rows at
        300/180/120 weighted station-minutes (`downtime_seconds` in
        seconds: 18000/10800/7200), and their SUM equals the header's
        `downtime_seconds` (30min x 20 stations = 36000s) — never the
        naive 3x36000 a whole-plant weight per row would produce."""
        owner = _owner(seed_user)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        by_location = _by_location(res)

        assert by_location[three_uap_hierarchy["uap_a"]["id"]]["kpis"]["downtime_seconds"] == 18000
        assert by_location[three_uap_hierarchy["uap_b"]["id"]]["kpis"]["downtime_seconds"] == 10800
        assert by_location[three_uap_hierarchy["uap_c"]["id"]]["kpis"]["downtime_seconds"] == 7200

        header_downtime = data["overall"]["downtime_seconds"]
        assert header_downtime == 30 * 60 * 20  # 36000
        row_sum = sum(row["kpis"]["downtime_seconds"] for row in by_location.values())
        assert row_sum == header_downtime


# --------------------------------------------------------------------------
# 4/5. Symmetric spread — a narrower scope reaches its own subtree only.
# --------------------------------------------------------------------------


class TestScopedTicketReachesOnlyItsOwnSubtree:
    def test_uap_ticket_reaches_its_lines_and_stations_never_another_uap(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap_a = seed_uap(namespace_id=NS, name="UAP A")
        uap_b = seed_uap(namespace_id=NS, name="UAP B")
        line_a1 = seed_production_line(namespace_id=NS, uap_id=uap_a["id"])
        line_a2 = seed_production_line(namespace_id=NS, uap_id=uap_a["id"])
        line_b = seed_production_line(namespace_id=NS, uap_id=uap_b["id"])
        stations_a1 = [
            seed_workstation(namespace_id=NS, production_line_id=line_a1["id"]) for _ in range(2)
        ]
        stations_a2 = [
            seed_workstation(namespace_id=NS, production_line_id=line_a2["id"]) for _ in range(1)
        ]
        seed_workstation(namespace_id=NS, production_line_id=line_b["id"])
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=uap_a["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        # by_location (uap kind, since 2 UAPs) includes UAP A, excludes UAP B.
        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert uap_a["id"] in by_location
        assert uap_b["id"] not in by_location

        # Drill down into UAP A -> its lines both carry downtime.
        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{uap_a['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        children = {row["id"]: row for row in res.json()["data"]["children"]}
        assert line_a1["id"] in children
        assert line_a2["id"] in children
        assert children[line_a1["id"]]["kpis"]["downtime_seconds"] > 0
        assert children[line_a2["id"]]["kpis"]["downtime_seconds"] > 0

        # And each of those lines' stations too.
        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"line:{line_a1['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        station_children = {row["id"]: row for row in res.json()["data"]["children"]}
        for station in stations_a1:
            assert station["id"] in station_children
            assert station_children[station["id"]]["kpis"]["downtime_seconds"] > 0

    def test_line_ticket_reaches_its_own_stations(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        stations1 = [
            seed_workstation(namespace_id=NS, production_line_id=line1["id"]) for _ in range(2)
        ]
        seed_workstation(namespace_id=NS, production_line_id=line2["id"])
        _seed_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line1["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"line:{line1['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        station_children = {row["id"]: row for row in res.json()["data"]["children"]}
        for station in stations1:
            assert station["id"] in station_children
            assert station_children[station["id"]]["kpis"]["downtime_seconds"] > 0

        # Its own UAP roll-up (unchanged existing behavior) still sees it.
        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert by_location[line1["id"]]["kpis"]["downtime_seconds"] > 0


# --------------------------------------------------------------------------
# 6. Station ticket — strictly unchanged.
# --------------------------------------------------------------------------


class TestStationTicketUnchanged:
    def test_station_ticket_appears_only_in_its_own_station_row(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station1 = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        station2 = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station1["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert set(by_location) == {station1["id"]}
        assert station2["id"] not in by_location
        assert by_location[station1["id"]]["kpis"]["downtime_seconds"] == 3600


# --------------------------------------------------------------------------
# 7/8. Legacy documents — exactly today's behavior, no spreading.
# --------------------------------------------------------------------------


class TestLegacyDocumentsNeverSpread:
    """A document with no `down_time_scope`, or an unrecognized one, must NOT
    be spread by the new rule — it keeps today's id-inference-only
    attribution (§2 of the contract: "on ne devine pas un scope large à
    partir d'ids absents")."""

    def test_missing_down_time_scope_with_no_ids_is_absent_from_every_row(
        self, client, seed_user, auth_headers, fake_db, three_uap_hierarchy
    ):
        owner = _owner(seed_user)
        _seed_issue(
            fake_db,
            down_time_scope=None,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert by_location == {}
        # But it must still count toward the header (unchanged today).
        assert res.json()["data"]["overall"]["count"] == 1

    def test_unrecognized_down_time_scope_with_no_ids_is_absent_from_every_row(
        self, client, seed_user, auth_headers, fake_db, three_uap_hierarchy
    ):
        owner = _owner(seed_user)
        _seed_issue(
            fake_db,
            down_time_scope="atelier",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert by_location == {}
        assert res.json()["data"]["overall"]["count"] == 1


# --------------------------------------------------------------------------
# 9/10. Empty hierarchy, floor at 1.
# --------------------------------------------------------------------------


class TestNoUapAndFloor:
    def test_plant_ticket_in_namespace_without_any_uap_does_not_crash(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["by_location"] == []

    def test_spread_ticket_does_not_reach_a_uap_with_no_stations(
        self, client, seed_user, auth_headers, fake_db, seed_uap
    ):
        """REPLACES the original scenario 10 (§9.3/W4): reconciliation (§7)
        wins over the weight floor. A SPREAD (plant) ticket must not produce
        a row at all for a UAP with no descendant workstations — the old
        expectation (a phantom row weighted 1) is the anomaly the developer
        raised back after the cross-cutting review; this asserts the
        corrected behavior."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap_a = seed_uap(namespace_id=NS, name="UAP A (empty)")
        uap_b = seed_uap(namespace_id=NS, name="UAP B (empty)")
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert uap_a["id"] not in by_location
        assert uap_b["id"] not in by_location

    def test_ticket_declared_on_an_empty_uap_still_floors_its_own_row_at_one(
        self, client, seed_user, auth_headers, fake_db, seed_uap
    ):
        """The other half of the replaced scenario 10: the floor at 1 keeps
        its real purpose for a ticket DECLARED AT (not spread onto) an empty
        location — that row must still exist, weighted 1, never 0."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap_a = seed_uap(namespace_id=NS, name="UAP A (empty)")
        seed_uap(namespace_id=NS, name="UAP B (empty)")
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=uap_a["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert by_location[uap_a["id"]]["kpis"]["downtime_seconds"] == 1800  # 30min x floor(1)


# --------------------------------------------------------------------------
# 11. `count` — unweighted, 1 per row (documented, not a bug).
# --------------------------------------------------------------------------


class TestCountIsOnePerRowWhenSpread:
    def test_plant_ticket_counts_one_in_each_uap_row(
        self, client, seed_user, auth_headers, fake_db, three_uap_hierarchy
    ):
        owner = _owner(seed_user)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert by_location[three_uap_hierarchy["uap_a"]["id"]]["kpis"]["count"] == 1
        assert by_location[three_uap_hierarchy["uap_b"]["id"]]["kpis"]["count"] == 1
        assert by_location[three_uap_hierarchy["uap_c"]["id"]]["kpis"]["count"] == 1
        # Header count is 1, not the sum of the rows' counts (3) -- the
        # documented, non-reconciling model for `count`/`mttr`.
        assert res.json()["data"]["overall"]["count"] == 1


# --------------------------------------------------------------------------
# 12. Dashboard / `/kpi/daily` scope filter coherence.
# --------------------------------------------------------------------------


class TestDashboardAndDailyScopeCoherence:
    def test_daily_duration_for_uap_a_scope_matches_dashboard_row_for_uap_a(
        self, client, seed_user, auth_headers, fake_db, three_uap_hierarchy
    ):
        """A plant-scope ticket must be INCLUDED by `/kpi/daily`'s
        `scope_kind=uap&scope_id=<UAP A>` filter (today it is dropped by
        `_filter_by_scope`), and its weighted contribution there must equal
        UAP A's row in the dashboard breakdown -- the exact coherence this
        contract exists to guarantee (§1)."""
        owner = _owner(seed_user)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        dashboard_res = client.get(
            "/kpi/dashboard", params=_period(), headers=auth_headers(owner)
        )
        assert dashboard_res.status_code == 200, dashboard_res.text
        dashboard_row = _by_location(dashboard_res)[three_uap_hierarchy["uap_a"]["id"]]

        daily_res = client.get(
            "/kpi/daily",
            params={
                "metric": "duration",
                "scope_kind": "uap",
                "scope_id": three_uap_hierarchy["uap_a"]["id"],
                **_period(),
            },
            headers=auth_headers(owner),
        )
        assert daily_res.status_code == 200, daily_res.text
        daily_total = sum(p["value"] for p in daily_res.json()["data"]["points"])

        assert daily_total == dashboard_row["kpis"]["downtime_seconds"] == 18000


# --------------------------------------------------------------------------
# 13. Non-regression — a ticket declared exactly at the broken-down level
#     keeps `_ticket_weight`'s existing weight.
# --------------------------------------------------------------------------


class TestNonRegressionAtOwnLevel:
    def test_uap_ticket_weighs_its_own_uap_row_exactly_as_ticket_weight_does_today(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """A ticket declared exactly at the UAP level (broken down by uap)
        gets the SAME weight it already gets today -- sum of its own lines'
        stations, nothing narrowed or widened by this contract."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap_a = seed_uap(namespace_id=NS)
        uap_b = seed_uap(namespace_id=NS)
        line_a1 = seed_production_line(namespace_id=NS, uap_id=uap_a["id"])
        line_a2 = seed_production_line(namespace_id=NS, uap_id=uap_a["id"])
        line_b = seed_production_line(namespace_id=NS, uap_id=uap_b["id"])
        for _ in range(2):
            seed_workstation(namespace_id=NS, production_line_id=line_a1["id"])
        for _ in range(3):
            seed_workstation(namespace_id=NS, production_line_id=line_a2["id"])
        seed_workstation(namespace_id=NS, production_line_id=line_b["id"])
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=uap_a["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        # 2 + 3 = 5 stations under UAP A -> unchanged from `_ticket_weight`.
        assert by_location[uap_a["id"]]["kpis"]["downtime_seconds"] == 5 * 3600
        assert uap_b["id"] not in by_location

    def test_station_ticket_weighs_one_exactly_as_today(
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
        by_location = _by_location(res)
        assert by_location[stations[0]["id"]]["kpis"]["downtime_seconds"] == 3600


# --------------------------------------------------------------------------
# 19/20. §9.1/B1 — the drill-down header must be weighted by the FIXED
# location, not the whole plant, and must reconcile with its own `children`.
# --------------------------------------------------------------------------


class TestDrilldownHeaderWeightedByFixedLocation:
    """Today `get_drilldown` builds its header `kpis` with the plain
    ticket-level `weight_of` instead of `_location_weight_fn` for the fixed
    path location (`get_daily` was fixed for this, `get_drilldown` was not) —
    a drill-down on UAP A shows the whole plant's weight in its header, and
    that header does not even reconcile with its own `children` block."""

    def test_uap_path_header_matches_dashboard_row_and_its_own_children_sum(
        self, client, seed_user, auth_headers, fake_db, three_uap_hierarchy
    ):
        owner = _owner(seed_user)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )
        uap_a_id = three_uap_hierarchy["uap_a"]["id"]

        dashboard_res = client.get(
            "/kpi/dashboard", params=_period(), headers=auth_headers(owner)
        )
        assert dashboard_res.status_code == 200, dashboard_res.text
        dashboard_row = _by_location(dashboard_res)[uap_a_id]

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{uap_a_id}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        header_downtime = data["kpis"]["downtime_seconds"]
        children_sum = sum(row["kpis"]["downtime_seconds"] for row in data["children"])

        # UAP A's own share (10 of 20 stations, 30min) -- measured today at
        # 36000 (the whole plant), not 18000.
        assert header_downtime == 18000
        assert header_downtime == dashboard_row["kpis"]["downtime_seconds"]
        assert header_downtime == children_sum

    def test_station_path_header_never_carries_the_whole_plants_weight(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """A station is a drill-down LEAF (`children` is `None`), so this
        scenario pins the header value directly against the contract's own
        per-station weight rule (§3: a station's share is always 1, floored)
        instead of reconciling against a `children` block that doesn't
        exist at this depth."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap_x = seed_uap(namespace_id=NS, name="UAP X")
        uap_y = seed_uap(namespace_id=NS, name="UAP Y")
        line_x = seed_production_line(namespace_id=NS, uap_id=uap_x["id"])
        line_y = seed_production_line(namespace_id=NS, uap_id=uap_y["id"])
        stations_x = [
            seed_workstation(namespace_id=NS, production_line_id=line_x["id"]) for _ in range(3)
        ]
        for _ in range(2):
            seed_workstation(namespace_id=NS, production_line_id=line_y["id"])
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"station:{stations_x[0]['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["children"] is None  # leaf

        # This station's own share is 1 station, never the plant's 5 -- 30min
        # x 1 = 1800s, measured today at 30min x 5 = 9000s.
        assert data["kpis"]["downtime_seconds"] == 1800


# --------------------------------------------------------------------------
# 21/22. §9.2/B2 — an explicit "unassigned" row for stations with no
# `production_line_id`, so the breakdown still reconciles with the header.
# --------------------------------------------------------------------------


class TestUnassignedStationsRow:
    """A workstation with `production_line_id = None` is counted in the
    plant-wide header weight (`_ticket_weight` = `len(hierarchy["stations"])`)
    but reachable by no `by_location` row today -- the sum of rows silently
    falls short of the header. §9.2 adds an explicit sentinel row rather than
    hiding the gap."""

    def test_unattached_stations_produce_an_unassigned_row_that_reconciles_with_header(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        # Both UAPs non-empty -- this test is single-purpose (the unassigned
        # row + reconciliation), not a rerun of scenario 10's "empty
        # location gets no row" behavior.
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap_a = seed_uap(namespace_id=NS, name="UAP A")
        uap_b = seed_uap(namespace_id=NS, name="UAP B")
        line_a = seed_production_line(namespace_id=NS, uap_id=uap_a["id"])
        line_b = seed_production_line(namespace_id=NS, uap_id=uap_b["id"])
        for _ in range(3):
            seed_workstation(namespace_id=NS, production_line_id=line_a["id"])
        for _ in range(2):
            seed_workstation(namespace_id=NS, production_line_id=line_b["id"])
        # 4 stations with no line at all -- legitimate per the schema.
        for _ in range(4):
            seed_workstation(namespace_id=NS, production_line_id=None)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        by_location = _by_location(res)

        assert by_location[uap_a["id"]]["kpis"]["downtime_seconds"] == 5400  # 3 stations
        assert by_location[uap_b["id"]]["kpis"]["downtime_seconds"] == 3600  # 2 stations

        assert "unassigned" in by_location
        unassigned_row = by_location["unassigned"]
        assert unassigned_row["label"] == ""
        assert unassigned_row["kind"] == "uap"  # this breakdown's kind
        # 4 unattached stations, 30min -> 7200s.
        assert unassigned_row["kpis"]["downtime_seconds"] == 7200

        header_downtime = data["overall"]["downtime_seconds"]
        row_sum = sum(row["kpis"]["downtime_seconds"] for row in by_location.values())
        assert row_sum == header_downtime

    def test_no_unattached_stations_means_no_unassigned_row(
        self, client, seed_user, auth_headers, fake_db, three_uap_hierarchy
    ):
        """Never a zero row: `unassigned` is emitted ONLY when the count of
        unattached stations is > 0."""
        owner = _owner(seed_user)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert "unassigned" not in by_location


# --------------------------------------------------------------------------
# 23. §9.4/W2 — the spread must start from the RESOLVED location, not the
# raw stored ids.
# --------------------------------------------------------------------------


class TestSpreadUsesResolvedLocationNotRawIds:
    def test_uap_scope_ticket_with_only_a_line_id_still_reaches_that_lines_stations(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """A `uap`-scope ticket carrying ONLY a `production_line_id` (no
        `uap_id`) resolves its UAP via `_resolve_location`'s existing
        roll-up. The spread branches must use that RESOLVED uap id, not the
        raw (absent) `uap_id` on the document -- today they read the raw id
        and reach no station rows at all (measured: 10 station children all
        0)."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap_a = seed_uap(namespace_id=NS, name="UAP A")
        uap_b = seed_uap(namespace_id=NS, name="UAP B")
        line_a1 = seed_production_line(namespace_id=NS, uap_id=uap_a["id"])
        line_a2 = seed_production_line(namespace_id=NS, uap_id=uap_a["id"])
        line_b = seed_production_line(namespace_id=NS, uap_id=uap_b["id"])
        stations_a1 = [
            seed_workstation(namespace_id=NS, production_line_id=line_a1["id"]) for _ in range(2)
        ]
        seed_workstation(namespace_id=NS, production_line_id=line_a2["id"])
        seed_workstation(namespace_id=NS, production_line_id=line_b["id"])
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=None,
            production_line_id=line_a1["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        # UAP A row exists (resolved from line_a1), UAP B does not.
        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert uap_a["id"] in by_location
        assert uap_b["id"] not in by_location

        # Both of UAP A's lines carry downtime (uap-level spread).
        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{uap_a['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        children = {row["id"]: row for row in res.json()["data"]["children"]}
        assert children[line_a1["id"]]["kpis"]["downtime_seconds"] > 0
        assert children[line_a2["id"]]["kpis"]["downtime_seconds"] > 0

        # And line_a1's own stations -- the exact gap the contract measured.
        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"line:{line_a1['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        station_children = {row["id"]: row for row in res.json()["data"]["children"]}
        for station in stations_a1:
            assert station["id"] in station_children
            assert station_children[station["id"]]["kpis"]["downtime_seconds"] > 0


# --------------------------------------------------------------------------
# 25. §7's actual promise -- reconciliation on a MIXED set: spread +
# non-spread + a carry-over ticket starting before the period.
# --------------------------------------------------------------------------


class TestMixedSetReconciliation:
    def test_spread_non_spread_and_carry_over_tickets_still_reconcile_with_header(
        self, client, seed_user, auth_headers, fake_db, three_uap_hierarchy, freeze_kpi_clock
    ):
        owner = _owner(seed_user)
        uap_a_id = three_uap_hierarchy["uap_a"]["id"]
        uap_b_id = three_uap_hierarchy["uap_b"]["id"]
        uap_c_id = three_uap_hierarchy["uap_c"]["id"]

        # 1. Spread plant ticket, 30min, CLOSED -> 20 stations total.
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )
        # 2. Non-spread ticket declared exactly at UAP B, 10min, CLOSED.
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=uap_b_id,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(8),
            resolved_at=_utc(8, 10),
        )
        # 3. Carry-over: opened the day before the period, still open at the
        # frozen "now" (2026-01-15 18:00) -> clamped to [period_start 00:00,
        # now 18:00] = 18h, declared exactly at UAP C.
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=uap_c_id,
            status=DownTimeStatus.PENDING.value,
            created_at=_utc(8, day=14),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        by_location = _by_location(res)

        header_downtime = data["overall"]["downtime_seconds"]
        row_sum = sum(row["kpis"]["downtime_seconds"] for row in by_location.values())
        assert row_sum == header_downtime

        # And the numbers themselves, so a partial cancellation of errors
        # can't slip the reconciliation assertion above.
        assert by_location[uap_a_id]["kpis"]["downtime_seconds"] == 18000  # ticket 1 only
        assert (
            by_location[uap_b_id]["kpis"]["downtime_seconds"] == 10800 + 3600
        )  # ticket 1 + ticket 2
        assert (
            by_location[uap_c_id]["kpis"]["downtime_seconds"] == 7200 + 259200
        )  # ticket 1 + ticket 3
        assert header_downtime == 36000 + 3600 + 259200
