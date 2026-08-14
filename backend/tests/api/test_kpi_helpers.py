"""Unit tests for the pure helper functions in
`src.app.routers.kpi.services` — the aggregation primitives behind
`GET /kpi/dashboard|drilldown|daily`. Deep-dives §5bis of
`.claude/specs/kpi-dashboard.md`; endpoint-level scenarios (auth, tenant
isolation, response shape) live in `tests/api/test_kpi.py` /
`tests/api/test_kpi_dashboard.py`.

No Firestore/network/time is touched here except `_location_hierarchy` /
`_by_agent_bars`, which take a `FirestoreClient` wrapping the shared
`fake_db` fixture (see `tests/conftest.py`).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from src.app.core.firestore import PRODUCTION_LINE_COLLECTION, UAP_COLLECTION, USERS_COLLECTION, WORKSTATION_COLLECTION
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import DownTimeStatus
from src.app.routers.kpi.services import (
    _compute_kpis,
    _configured_shifts,
    _location_hierarchy,
    _mttr_seconds,
    _parse_drill_path,
    _parse_hhmm,
    _pareto_by_process,
    _planned_seconds,
    _planned_seconds_per_day,
    _resolve_location,
    _ticket_downtime_seconds,
    _ticket_weight,
    _weight_of_builder,
    _by_agent_bars,
)

UTC = timezone.utc


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _issue(**overrides) -> dict:
    now = datetime.now(UTC)
    issue = {
        "id": str(uuid.uuid4()),
        "created_at": _iso(now),
        "status": DownTimeStatus.PENDING.value,
        "resolved_at": None,
        "resolved_by": None,
    }
    issue.update(overrides)
    return issue


# --------------------------------------------------------------------------
# _ticket_downtime_seconds
# --------------------------------------------------------------------------


class TestTicketDowntimeSeconds:
    def test_closed_ticket_fully_inside_window(self):
        base = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)
        issue = _issue(
            status=DownTimeStatus.CLOSED.value,
            created_at=_iso(base),
            resolved_at=_iso(base + timedelta(hours=2)),
        )
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, tzinfo=UTC)
        now = datetime(2026, 1, 11, tzinfo=UTC)

        seconds = _ticket_downtime_seconds(issue, period_start, period_end, now)

        assert seconds == 2 * 3600

    def test_open_ticket_partial_to_now(self):
        base = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)
        issue = _issue(status=DownTimeStatus.PENDING.value, created_at=_iso(base))
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, tzinfo=UTC)
        now = base + timedelta(hours=3)

        seconds = _ticket_downtime_seconds(issue, period_start, period_end, now)

        assert seconds == 3 * 3600

    def test_ticket_starting_before_window_is_clamped(self):
        base = datetime(2026, 1, 9, 20, 0, tzinfo=UTC)
        issue = _issue(
            status=DownTimeStatus.CLOSED.value,
            created_at=_iso(base),
            resolved_at=_iso(datetime(2026, 1, 10, 4, 0, tzinfo=UTC)),
        )
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, tzinfo=UTC)
        now = datetime(2026, 1, 11, tzinfo=UTC)

        seconds = _ticket_downtime_seconds(issue, period_start, period_end, now)

        # Only the 00:00 -> 04:00 slice inside the queried window counts.
        assert seconds == 4 * 3600

    def test_resolved_after_window_end_is_clamped(self):
        base = datetime(2026, 1, 10, 20, 0, tzinfo=UTC)
        issue = _issue(
            status=DownTimeStatus.CLOSED.value,
            created_at=_iso(base),
            resolved_at=_iso(datetime(2026, 1, 11, 4, 0, tzinfo=UTC)),
        )
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, tzinfo=UTC)
        now = datetime(2026, 1, 12, tzinfo=UTC)

        seconds = _ticket_downtime_seconds(issue, period_start, period_end, now)

        # 20:00 -> 23:59:59 only (~4h, rounding to the second boundary).
        assert seconds == pytest.approx(4 * 3600 - 1, abs=1)

    def test_ticket_created_after_window_is_zero(self):
        base = datetime(2026, 1, 12, 8, 0, tzinfo=UTC)
        issue = _issue(status=DownTimeStatus.PENDING.value, created_at=_iso(base))
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, tzinfo=UTC)
        now = datetime(2026, 1, 13, tzinfo=UTC)

        seconds = _ticket_downtime_seconds(issue, period_start, period_end, now)

        assert seconds == 0.0

    def test_ticket_with_no_created_at_is_zero(self):
        issue = _issue(created_at=None)
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, tzinfo=UTC)
        now = datetime(2026, 1, 11, tzinfo=UTC)

        assert _ticket_downtime_seconds(issue, period_start, period_end, now) == 0.0


# --------------------------------------------------------------------------
# _mttr_seconds
# --------------------------------------------------------------------------


class TestMttrSeconds:
    def test_mean_over_closed_tickets_only(self):
        base = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)
        tickets = [
            _issue(
                status=DownTimeStatus.CLOSED.value,
                created_at=_iso(base),
                resolved_at=_iso(base + timedelta(hours=1)),
            ),
            _issue(
                status=DownTimeStatus.CLOSED.value,
                created_at=_iso(base),
                resolved_at=_iso(base + timedelta(hours=3)),
            ),
            _issue(status=DownTimeStatus.PENDING.value, created_at=_iso(base)),
        ]

        assert _mttr_seconds(tickets) == 2 * 3600

    def test_no_closed_tickets_returns_zero(self):
        tickets = [_issue(status=DownTimeStatus.PENDING.value)]
        assert _mttr_seconds(tickets) == 0.0

    def test_empty_list_returns_zero(self):
        assert _mttr_seconds([]) == 0.0


# --------------------------------------------------------------------------
# _compute_kpis
# --------------------------------------------------------------------------


class TestComputeKpis:
    def test_mixed_closed_and_open_tickets(self):
        base = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, tzinfo=UTC)
        now = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
        tickets = [
            _issue(
                status=DownTimeStatus.CLOSED.value,
                created_at=_iso(base),
                resolved_at=_iso(base + timedelta(hours=2)),
            ),
            _issue(status=DownTimeStatus.PENDING.value, created_at=_iso(base + timedelta(hours=4))),
        ]
        planned_seconds = 8 * 3600.0

        kpis = _compute_kpis(tickets, period_start, period_end, now, planned_seconds)

        assert kpis.count == 2
        assert kpis.mttr_seconds == 2 * 3600
        expected_downtime = 2 * 3600 + (now - (base + timedelta(hours=4))).total_seconds()
        assert kpis.downtime_seconds == int(round(expected_downtime))
        assert kpis.mtbf_seconds == int(round(planned_seconds / 2))

    def test_empty_slice_returns_zeros(self):
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, tzinfo=UTC)
        now = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
        planned_seconds = 8 * 3600.0

        kpis = _compute_kpis([], period_start, period_end, now, planned_seconds)

        assert kpis.downtime_seconds == 0
        assert kpis.count == 0
        assert kpis.mttr_seconds == 0
        assert kpis.mtbf_seconds == int(round(planned_seconds))

    def test_zero_planned_seconds_gives_none_mtbf(self):
        """Fix #3: a non-positive planned-time denominator leaves MTBF with
        nothing meaningful to divide by, so it's `None`."""
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, tzinfo=UTC)
        now = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)

        kpis = _compute_kpis([], period_start, period_end, now, 0.0)

        assert kpis.mtbf_seconds is None

    def test_downtime_weighted_by_weight_of(self):
        """§5bis.1bis — `downtime_seconds` multiplies each ticket's clamped
        duration by `weight_of(issue)`; `count`/`mttr` stay unweighted."""
        base = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, tzinfo=UTC)
        now = datetime(2026, 1, 11, tzinfo=UTC)
        tickets = [
            _issue(
                status=DownTimeStatus.CLOSED.value,
                created_at=_iso(base),
                resolved_at=_iso(base + timedelta(hours=1)),
            )
        ]

        kpis = _compute_kpis(
            tickets, period_start, period_end, now, 0.0, weight_of=lambda _issue: 3
        )

        assert kpis.downtime_seconds == 3 * 3600
        assert kpis.count == 1
        assert kpis.mttr_seconds == 3600


# --------------------------------------------------------------------------
# _planned_seconds_per_day
# --------------------------------------------------------------------------


class TestPlannedSecondsPerDay:
    def test_three_eight_hour_shifts(self):
        settings = {
            "shift_number": 3,
            "shift_1": {"start_time": "06:00", "end_time": "14:00"},
            "shift_2": {"start_time": "14:00", "end_time": "22:00"},
            "shift_3": {"start_time": "22:00", "end_time": "06:00"},
        }

        seconds = _planned_seconds_per_day(settings)

        assert seconds == 24 * 3600

    def test_midnight_wrapping_shift_counted_correctly(self):
        settings = {
            "shift_number": 1,
            "shift_1": {"start_time": "22:00", "end_time": "06:00"},
        }

        seconds = _planned_seconds_per_day(settings)

        # 22:00 -> 06:00 = 8h clock window, no break deducted (§5bis.3/4).
        assert seconds == 8 * 3600

    def test_no_settings_defaults_to_24h(self):
        assert _planned_seconds_per_day({}) == 24 * 3600

    def test_shift_filter_narrows_to_single_shift(self):
        settings = {
            "shift_number": 2,
            "shift_1": {"start_time": "06:00", "end_time": "14:00"},
            "shift_2": {"start_time": "14:00", "end_time": "22:00"},
        }

        seconds = _planned_seconds_per_day(settings, shift_filter="2")

        assert seconds == 8 * 3600

    def test_shift_filter_on_unconfigured_shift_is_zero(self):
        settings = {"shift_number": 1, "shift_1": {"start_time": "06:00", "end_time": "14:00"}}

        assert _planned_seconds_per_day(settings, shift_filter="2") == 0.0


# --------------------------------------------------------------------------
# _parse_hhmm / _configured_shifts — fix #9 (tolerant parsing).
# --------------------------------------------------------------------------


class TestParseHhmmTolerant:
    def test_unparsable_time_returns_none_not_raises(self):
        assert _parse_hhmm("not-a-time") is None
        assert _parse_hhmm("") is None

    def test_valid_time_still_parses(self):
        assert _parse_hhmm("06:30") == 6 * 60 + 30

    def test_configured_shifts_skips_shift_with_unparsable_window(self):
        settings = {
            "shift_number": 2,
            "shift_1": {"start_time": "bogus", "end_time": "14:00"},
            "shift_2": {"start_time": "14:00", "end_time": "22:00"},
        }

        shifts = _configured_shifts(settings)

        assert [sid for sid, _ in shifts] == ["2"]

    def test_planned_seconds_per_day_does_not_500_on_corrupt_shift(self):
        """A corrupted stored shift window must degrade gracefully — the
        corrupt shift is skipped (never raises), and since it was the
        namespace's only shift, this falls back to the same "no configured
        shift windows" 24h default as an unconfigured namespace."""
        settings = {
            "shift_number": 1,
            "shift_1": {"start_time": "abc:def", "end_time": "14:00"},
        }

        assert _configured_shifts(settings) == []
        assert _planned_seconds_per_day(settings) == 24 * 3600


# --------------------------------------------------------------------------
# _planned_seconds — fix #2 (clamped to now, final-day proration).
# --------------------------------------------------------------------------


class TestPlannedSecondsClampedToNow:
    def test_no_settings_namespace_today_prorates_to_elapsed_time(self):
        """No configured shifts -> implicit 24h/day window starting at local
        midnight; at a frozen "now" of 08:00 mid-day, only the elapsed 8h
        counts (not the full 24h)."""
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, 999999, tzinfo=UTC)
        now = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)

        planned = _planned_seconds({}, period_start, period_end, now)

        assert planned == 8 * 3600

    def test_fully_elapsed_period_counts_full_days_uncapped(self):
        """Once `now` is past `period_end` (a historical period), the full
        per-day planned time counts — no proration."""
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 11, 23, 59, 59, 999999, tzinfo=UTC)
        now = datetime(2026, 1, 20, tzinfo=UTC)

        planned = _planned_seconds({}, period_start, period_end, now)

        assert planned == 2 * 24 * 3600

    def test_multi_day_period_prorates_only_the_final_day(self):
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 12, 23, 59, 59, 999999, tzinfo=UTC)
        now = datetime(2026, 1, 12, 6, 0, tzinfo=UTC)  # mid-way through day 3.

        planned = _planned_seconds({}, period_start, period_end, now)

        # 2 full days (10th, 11th) + 6h prorated on the 12th.
        assert planned == 2 * 24 * 3600 + 6 * 3600

    def test_configured_shift_prorated_by_elapsed_fraction_of_its_window(self):
        settings = {
            "shift_number": 1,
            "shift_1": {"start_time": "06:00", "end_time": "14:00"},
        }
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, 999999, tzinfo=UTC)
        # 2h into the 8h shift window (06:00 -> 08:00).
        now = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)

        planned = _planned_seconds(settings, period_start, period_end, now)

        assert planned == pytest.approx(2 * 3600)

    def test_now_before_period_start_is_zero(self):
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, 999999, tzinfo=UTC)
        now = datetime(2026, 1, 9, 12, 0, tzinfo=UTC)

        assert _planned_seconds({}, period_start, period_end, now) == 0.0


# --------------------------------------------------------------------------
# _pareto_by_process
# --------------------------------------------------------------------------


class TestParetoByProcess:
    def test_shares_sum_to_one_cumulative_monotone_sorted_desc(self):
        base = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, tzinfo=UTC)
        now = datetime(2026, 1, 11, tzinfo=UTC)
        tickets = [
            _issue(
                status=DownTimeStatus.CLOSED.value,
                created_at=_iso(base),
                resolved_at=_iso(base + timedelta(hours=3)),
                down_time_type="break down",
            ),
            _issue(
                status=DownTimeStatus.CLOSED.value,
                created_at=_iso(base),
                resolved_at=_iso(base + timedelta(hours=1)),
                down_time_type="quality issue",
            ),
        ]

        rows = _pareto_by_process(tickets, period_start, period_end, now)

        assert [r.id for r in rows] == ["maintenance", "quality"]
        assert pytest.approx(sum(r.share for r in rows), abs=1e-4) == 1.0
        cumulative_values = [r.cumulative for r in rows]
        assert cumulative_values == sorted(cumulative_values)
        assert cumulative_values[-1] == pytest.approx(1.0, abs=1e-4)

    def test_zero_downtime_returns_empty(self):
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, tzinfo=UTC)
        now = datetime(2026, 1, 11, tzinfo=UTC)

        assert _pareto_by_process([], period_start, period_end, now) == []


# --------------------------------------------------------------------------
# _parse_drill_path
# --------------------------------------------------------------------------


class TestParseDrillPath:
    def test_valid_multi_step_path(self):
        steps = _parse_drill_path("uap:u1>line:l1>station:s1")
        assert steps == [("uap", "u1"), ("line", "l1"), ("station", "s1")]

    def test_malformed_segment_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_drill_path("not-a-valid-path")
        assert exc_info.value.status_code == 422

    def test_unknown_kind_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_drill_path("bogus:xyz")
        assert exc_info.value.status_code == 422

    def test_empty_path_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_drill_path("")
        assert exc_info.value.status_code == 422


# --------------------------------------------------------------------------
# _location_hierarchy / _resolve_location (light coverage; full drill
# exercised via API tests) — uses fake_db to build a real FirestoreClient.
# --------------------------------------------------------------------------


class TestLocationHierarchy:
    def test_workstation_rolls_up_to_uap_via_line(self, fake_db):
        ns = "ns-hier"
        client = FirestoreClient(client=fake_db)
        uap = {"id": "u1", "namespace_id": ns, "name": "UAP 1"}
        line = {"id": "l1", "namespace_id": ns, "name": "Line 1", "uap_id": "u1"}
        station = {"id": "s1", "namespace_id": ns, "name": "Station 1", "production_line_id": "l1"}
        fake_db.collection(UAP_COLLECTION).document("u1").set(uap)
        fake_db.collection(PRODUCTION_LINE_COLLECTION).document("l1").set(line)
        fake_db.collection(WORKSTATION_COLLECTION).document("s1").set(station)

        hierarchy = _location_hierarchy(client, ns)
        issue = _issue(workstation_id="s1")

        uap_id, line_id, station_id = _resolve_location(issue, hierarchy)

        assert (uap_id, line_id, station_id) == ("u1", "l1", "s1")


# --------------------------------------------------------------------------
# _ticket_weight / _weight_of_builder — §5bis.1bis (revision 2).
# --------------------------------------------------------------------------


def _hierarchy(stations_by_line=None, lines_by_uap=None, total_stations=0):
    return {
        "stations_by_line": stations_by_line or {},
        "lines_by_uap": lines_by_uap or {},
        "stations": {str(i): {} for i in range(total_stations)},
    }


class TestTicketWeight:
    def test_workstation_scope_is_always_one(self):
        hierarchy = _hierarchy(
            stations_by_line={"l1": [{"id": "s1"}, {"id": "s2"}]}, total_stations=5
        )
        issue = _issue(workstation_id="s1", production_line_id="l1")

        assert _ticket_weight(issue, hierarchy) == 1

    def test_line_scope_counts_its_own_stations(self):
        hierarchy = _hierarchy(stations_by_line={"l1": [{"id": "s1"}, {"id": "s2"}]})
        issue = _issue(production_line_id="l1")

        assert _ticket_weight(issue, hierarchy) == 2

    def test_line_scope_with_no_referenced_stations_floors_at_one(self):
        hierarchy = _hierarchy(stations_by_line={})
        issue = _issue(production_line_id="l-empty")

        assert _ticket_weight(issue, hierarchy) == 1

    def test_uap_scope_sums_stations_across_its_lines(self):
        hierarchy = _hierarchy(
            stations_by_line={"l1": [{"id": "s1"}, {"id": "s2"}], "l2": [{"id": "s3"}]},
            lines_by_uap={"u1": [{"id": "l1"}, {"id": "l2"}]},
        )
        issue = _issue(uap_id="u1")

        assert _ticket_weight(issue, hierarchy) == 3

    def test_uap_scope_with_no_lines_floors_at_one(self):
        hierarchy = _hierarchy(lines_by_uap={})
        issue = _issue(uap_id="u-empty")

        assert _ticket_weight(issue, hierarchy) == 1

    def test_plant_scope_counts_every_workstation_in_namespace(self):
        hierarchy = _hierarchy(total_stations=7)
        issue = _issue()  # no workstation_id/production_line_id/uap_id.

        assert _ticket_weight(issue, hierarchy) == 7

    def test_plant_scope_with_zero_workstations_floors_at_one(self):
        hierarchy = _hierarchy(total_stations=0)
        issue = _issue()

        assert _ticket_weight(issue, hierarchy) == 1

    def test_most_specific_non_null_scope_wins(self):
        """A ticket carrying `workstation_id` AND `production_line_id` AND
        `uap_id` is weighted by the most specific (workstation) one."""
        hierarchy = _hierarchy(
            stations_by_line={"l1": [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}]},
            lines_by_uap={"u1": [{"id": "l1"}]},
        )
        issue = _issue(workstation_id="s1", production_line_id="l1", uap_id="u1")

        assert _ticket_weight(issue, hierarchy) == 1

    def test_weight_of_builder_closes_over_hierarchy(self):
        hierarchy = _hierarchy(stations_by_line={"l1": [{"id": "s1"}, {"id": "s2"}]})
        weight_of = _weight_of_builder(hierarchy)

        assert weight_of(_issue(production_line_id="l1")) == 2
        assert weight_of(_issue(workstation_id="s1")) == 1


class TestByAgentBars:
    def test_attributed_to_resolved_by_closed_only(self, fake_db):
        client = FirestoreClient(client=fake_db)
        fake_db.collection(USERS_COLLECTION).document("agent-1").set(
            {"id": "agent-1", "first_name": "Jane", "last_name": "Doe"}
        )
        base = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)
        tickets = [
            _issue(
                status=DownTimeStatus.CLOSED.value,
                created_at=_iso(base),
                resolved_at=_iso(base + timedelta(hours=2)),
                resolved_by="agent-1",
            ),
            _issue(status=DownTimeStatus.PENDING.value, resolved_by="agent-1"),
        ]

        mttr_bars, count_bars = _by_agent_bars(client, tickets)

        assert len(mttr_bars) == 1
        assert mttr_bars[0].id == "agent-1"
        assert mttr_bars[0].label == "Jane Doe"
        assert mttr_bars[0].value == 2 * 3600
        assert count_bars[0].value == 1
