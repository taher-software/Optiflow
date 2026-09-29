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
from src.app.globals.enum import DOWNTIME_TYPE_PROCESS, DownTimeStatus, DownTimeType, Process
from src.app.routers.kpi.services import (
    _compute_kpis,
    _configured_shifts,
    _elapsed_shift_seconds,
    _location_hierarchy,
    _mttr_seconds,
    _parse_drill_path,
    _parse_hhmm,
    _pareto_by_process,
    _planned_seconds,
    _planned_seconds_per_day,
    _process_for_ticket,
    _resolve_location,
    _shift_window_seconds,
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

    def test_no_closed_tickets_returns_none(self):
        tickets = [_issue(status=DownTimeStatus.PENDING.value)]
        assert _mttr_seconds(tickets) is None

    def test_empty_list_returns_none(self):
        assert _mttr_seconds([]) is None


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

    def test_empty_slice_returns_zero_downtime_and_null_mttr_mtbf(self):
        period_start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        period_end = datetime(2026, 1, 10, 23, 59, 59, tzinfo=UTC)
        now = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
        planned_seconds = 8 * 3600.0

        kpis = _compute_kpis([], period_start, period_end, now, planned_seconds)

        assert kpis.downtime_seconds == 0
        assert kpis.count == 0
        assert kpis.mttr_seconds is None
        assert kpis.mtbf_seconds is None

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

        # 22:00 -> 06:00 = 8h clock window; no break configured here, so
        # nothing is deducted (revision 3, §5bis.4bis).
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
# _shift_window_seconds — revision 3, §5bis.4bis (break deducted).
# --------------------------------------------------------------------------


class TestShiftWindowSecondsBreak:
    def test_no_break_configured_full_window_counts(self):
        shift = {"start_time": "06:00", "end_time": "14:00"}
        assert _shift_window_seconds(shift) == 8 * 3600

    def test_break_deducted_from_window(self):
        shift = {
            "start_time": "06:00",
            "end_time": "14:00",
            "break_start_time": "10:00",
            "break_end_time": "10:30",
        }
        # 8h window - 30min break.
        assert _shift_window_seconds(shift) == 8 * 3600 - 30 * 60

    def test_break_across_midnight_wrapping_shift_deducted(self):
        shift = {
            "start_time": "22:00",
            "end_time": "06:00",
            "break_start_time": "01:00",
            "break_end_time": "01:30",
        }
        assert _shift_window_seconds(shift) == 8 * 3600 - 30 * 60

    def test_unparsable_break_is_ignored_not_500(self):
        """A stored break pair that fails validation (here: outside the
        shift window — a corrupted document written before request-time
        validation existed) degrades to "no break" instead of raising."""
        shift = {
            "start_time": "06:00",
            "end_time": "14:00",
            "break_start_time": "20:00",
            "break_end_time": "20:30",
        }
        assert _shift_window_seconds(shift) == 8 * 3600

    def test_only_one_break_field_present_is_ignored(self):
        shift = {
            "start_time": "06:00",
            "end_time": "14:00",
            "break_start_time": "10:00",
            "break_end_time": None,
        }
        assert _shift_window_seconds(shift) == 8 * 3600


# --------------------------------------------------------------------------
# _elapsed_shift_seconds — revision 3, §5bis.4bis (C1: net of break).
# --------------------------------------------------------------------------


class TestElapsedShiftSecondsBreak:
    """A plain 06:00-14:00 shift with a 10:00-10:30 break, and its
    midnight-wrapping twin (22:00-06:00 with a 01:00-01:30 break — same
    relative positions, shifted by the wrap), at the same relative
    `now_local` positions."""

    _SHIFT = {
        "start_time": "06:00",
        "end_time": "14:00",
        "break_start_time": "10:00",
        "break_end_time": "10:30",
    }
    _WRAP_SHIFT = {
        "start_time": "22:00",
        "end_time": "06:00",
        "break_start_time": "01:00",
        "break_end_time": "01:30",
    }

    def _now(self, hour, minute=0, day=15):
        return datetime(2026, 1, day, hour, minute, tzinfo=UTC)

    def test_before_break_starts_unchanged(self):
        # 3h into the shift (06:00 -> 09:00), break not reached yet.
        assert _elapsed_shift_seconds(self._SHIFT, self._now(9, 0)) == 3 * 3600

    def test_exactly_at_break_start(self):
        # 4h in (06:00 -> 10:00) == the break's own start.
        assert _elapsed_shift_seconds(self._SHIFT, self._now(10, 0)) == 4 * 3600

    def test_mid_break_pins_to_break_start(self):
        # 10:15, mid-break -> pinned to time-until-break-start (4h).
        assert _elapsed_shift_seconds(self._SHIFT, self._now(10, 15)) == 4 * 3600

    def test_exactly_at_break_end(self):
        # Break just ended -> net worked time == time-until-break-start (4h),
        # nothing worked since the break ended yet.
        assert _elapsed_shift_seconds(self._SHIFT, self._now(10, 30)) == 4 * 3600

    def test_after_break_end_deducts_full_break(self):
        # 12:00 -> 6h raw elapsed, minus the 30min break already passed.
        assert _elapsed_shift_seconds(self._SHIFT, self._now(12, 0)) == 6 * 3600 - 30 * 60

    def test_before_shift_start_is_zero(self):
        assert _elapsed_shift_seconds(self._SHIFT, self._now(5, 0)) == 0.0

    def test_after_shift_end_is_full_planned_net_of_break(self):
        # 18:00, well past the 14:00 end -> full window minus the break.
        assert _elapsed_shift_seconds(self._SHIFT, self._now(18, 0)) == 8 * 3600 - 30 * 60

    def test_no_break_configured_matches_raw_window_elapsed(self):
        shift = {"start_time": "06:00", "end_time": "14:00"}
        assert _elapsed_shift_seconds(shift, self._now(9, 0)) == 3 * 3600

    def test_illegible_break_ignored_matches_raw_window_elapsed(self):
        shift = {
            "start_time": "06:00",
            "end_time": "14:00",
            "break_start_time": "20:00",  # outside the shift window -> invalid.
            "break_end_time": "20:30",
        }
        assert _elapsed_shift_seconds(shift, self._now(9, 0)) == 3 * 3600

    # -- Midnight-wrap twin, same relative positions --------------------

    def test_wrap_before_break_starts_unchanged(self):
        # 2.5h into the shift (22:00 -> 00:30), break (at 01:00) not reached yet.
        assert (
            _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(0, 30))
            == pytest.approx(2.5 * 3600)
        )

    def test_wrap_mid_break_pins_to_break_start(self):
        # 01:15, mid-break -> pinned to 3h (time-until-break-start).
        assert _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(1, 15)) == 3 * 3600

    def test_wrap_exactly_at_break_end(self):
        assert _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(1, 30)) == 3 * 3600

    def test_wrap_after_break_end_deducts_full_break(self):
        # 03:00 -> 5h raw elapsed (22:00 -> 03:00), minus the 30min break.
        assert _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(3, 0)) == 5 * 3600 - 30 * 60

    def test_wrap_after_shift_end_is_full_planned_net_of_break(self):
        # 06:00 is the wrap shift's own end -> full window minus the break.
        assert (
            _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(6, 0)) == 8 * 3600 - 30 * 60
        )

    # -- Regression: "else" branch (past end, before next start) must
    # -- saturate to the full window, not fall back to 0. ----------------

    def test_wrap_just_after_end_saturates_full_window(self):
        # 06:01, just past the 06:00 end -> full window (net of break),
        # same as exactly-at-end, NOT 0.
        assert (
            _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(6, 1))
            == 8 * 3600 - 30 * 60
        )

    def test_wrap_mid_morning_saturates_full_window(self):
        assert (
            _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(10, 0))
            == 8 * 3600 - 30 * 60
        )

    def test_wrap_mid_afternoon_saturates_full_window(self):
        assert (
            _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(15, 0))
            == 8 * 3600 - 30 * 60
        )

    def test_wrap_just_before_next_start_saturates_full_window(self):
        # 21:59, one minute before the next instance starts at 22:00.
        assert (
            _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(21, 59))
            == 8 * 3600 - 30 * 60
        )

    def test_wrap_next_instance_start_resets_to_zero(self):
        # 22:00 exactly -> the next instance just started -> back to 0.
        assert _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(22, 0)) == 0.0

    def test_wrap_continuity_around_end_no_drop_to_zero(self):
        # Just before vs. just after 06:00: neighboring values, no cliff.
        before = _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(5, 59))
        after = _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(6, 1))
        assert after == pytest.approx(8 * 3600 - 30 * 60)
        assert before == pytest.approx(8 * 3600 - 30 * 60, abs=120)
        assert abs(after - before) < 200


class TestElapsedShiftSecondsMidnightWrapNoBreak:
    """Same regression, no break configured — isolates the fix in
    `_elapsed_shift_seconds` from the break-deduction logic."""

    _WRAP_SHIFT = {"start_time": "22:00", "end_time": "06:00"}

    def _now(self, hour, minute=0, day=15):
        return datetime(2026, 1, day, hour, minute, tzinfo=UTC)

    def test_just_after_end_is_full_window_not_zero(self):
        assert _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(6, 1)) == 8 * 3600

    def test_mid_morning_is_full_window(self):
        assert _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(10, 0)) == 8 * 3600

    def test_mid_afternoon_is_full_window(self):
        assert _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(15, 0)) == 8 * 3600

    def test_just_before_next_start_is_full_window(self):
        assert _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(21, 59)) == 8 * 3600

    def test_exact_start_is_zero(self):
        assert _elapsed_shift_seconds(self._WRAP_SHIFT, self._now(22, 0)) == 0.0


# --------------------------------------------------------------------------
# _elapsed_shift_seconds(..., current_day_only=True) — revision 4,
# §5bis.4bis: "today's civil-day slice", not "this instance's progress".
# --------------------------------------------------------------------------


class TestElapsedShiftSecondsCurrentDayOnlyMidnightWrap:
    """22:00 -> 06:00 night shift, no break — both modes at every requested
    clock position, to pin down exactly where they diverge. They agree while
    `now < start_time` (both are still measuring yesterday's tail) and
    diverge once tonight's instance starts (`now >= start_time`): the
    default mode saturates to the full window, while `current_day_only`
    sums BOTH pieces of today's civil day the window touches — yesterday's
    tail PLUS tonight's progress so far — since a midnight-wrapping window
    can occupy two disjoint slices of one civil day."""

    _WRAP_SHIFT = {"start_time": "22:00", "end_time": "06:00"}

    def _now(self, hour, minute=0, day=15):
        return datetime(2026, 1, day, hour, minute, tzinfo=timezone.utc)

    @pytest.mark.parametrize(
        "hour, minute, expected_hours",
        [
            (2, 0, 2.0),  # 02:00 -> today's tail so far: [00:00, 02:00].
            (5, 0, 5.0),  # 05:00 -> [00:00, 05:00].
            (6, 0, 6.0),  # 06:00 -> the whole overnight tail, [00:00, 06:00].
            (10, 0, 6.0),  # 10:00 -- tonight hasn't started, still the tail.
            (21, 59, 6.0),  # 21:59 -- tonight's instance hasn't started yet.
            (22, 0, 6.0),  # 22:00 -- tonight's instance starts: yesterday's
            # full 6h tail PLUS 0h of tonight so far.
            (23, 0, 7.0),  # 23:00 -- yesterday's 6h tail PLUS 1h of tonight.
        ],
    )
    def test_current_day_only(self, hour, minute, expected_hours):
        assert _elapsed_shift_seconds(
            self._WRAP_SHIFT, self._now(hour, minute), current_day_only=True
        ) == pytest.approx(expected_hours * 3600)

    @pytest.mark.parametrize(
        "hour, minute, expected_hours",
        [
            (2, 0, 4.0),  # default mode: current instance started at 22:00 ->
            # 4h elapsed of the CURRENT instance by 02:00, not "since midnight".
            (5, 0, 7.0),
            (6, 0, 8.0),
            (10, 0, 8.0),  # saturates to the full window (old behavior).
            (21, 59, 8.0),
            (22, 0, 0.0),  # resets: a brand new instance just started.
            (23, 0, 1.0),
        ],
    )
    def test_default_mode_unchanged(self, hour, minute, expected_hours):
        assert _elapsed_shift_seconds(
            self._WRAP_SHIFT, self._now(hour, minute)
        ) == pytest.approx(expected_hours * 3600)


class TestElapsedShiftSecondsCurrentDayOnlyMidnightWrapWithBreak:
    """Same night shift, now with a 01:00 -> 01:30 break — proves the
    break-netting cases: fully passed, mid-break, and not-yet-reached, all
    measured the same way as the window itself, against TODAY's civil day
    (`clock_window_elapsed_since_midnight` applied to the break's own real
    clock bounds). The break sits entirely inside `[0, 06:00)`, so once
    01:30 has passed it stays fully netted out regardless of how far into
    tonight's instance `now` has advanced."""

    _WRAP_SHIFT = {
        "start_time": "22:00",
        "end_time": "06:00",
        "break_start_time": "01:00",
        "break_end_time": "01:30",
    }

    def _now(self, hour, minute=0, day=15):
        return datetime(2026, 1, day, hour, minute, tzinfo=timezone.utc)

    def test_break_not_yet_reached_at_00h30(self):
        # In the break's own future -> nothing to deduct: [00:00, 00:30].
        assert _elapsed_shift_seconds(
            self._WRAP_SHIFT, self._now(0, 30), current_day_only=True
        ) == pytest.approx(0.5 * 3600)

    def test_break_partially_elapsed_mid_break_at_01h15(self):
        # 1h15 raw tail elapsed, minus the 15min already spent in the break.
        assert _elapsed_shift_seconds(
            self._WRAP_SHIFT, self._now(1, 15), current_day_only=True
        ) == pytest.approx(1.0 * 3600)

    def test_break_fully_passed_at_02h00(self):
        # 2h raw tail elapsed, minus the full 30min break.
        assert _elapsed_shift_seconds(
            self._WRAP_SHIFT, self._now(2, 0), current_day_only=True
        ) == pytest.approx(1.5 * 3600)

    def test_at_05h00(self):
        assert _elapsed_shift_seconds(
            self._WRAP_SHIFT, self._now(5, 0), current_day_only=True
        ) == pytest.approx(4.5 * 3600)

    def test_at_06h00_full_overnight_tail_minus_break(self):
        assert _elapsed_shift_seconds(
            self._WRAP_SHIFT, self._now(6, 0), current_day_only=True
        ) == pytest.approx(5.5 * 3600)

    def test_at_10h00_capped_at_overnight_tail_minus_break(self):
        assert _elapsed_shift_seconds(
            self._WRAP_SHIFT, self._now(10, 0), current_day_only=True
        ) == pytest.approx(5.5 * 3600)

    def test_at_21h59_still_capped(self):
        assert _elapsed_shift_seconds(
            self._WRAP_SHIFT, self._now(21, 59), current_day_only=True
        ) == pytest.approx(5.5 * 3600)

    def test_at_22h00_tonights_instance_just_started(self):
        # Civil-day occupation: window = 6h (full overnight tail) + 0h of
        # tonight so far = 6h; break already fully elapsed this morning
        # (01:00 -> 01:30) -> net 6h - 0.5h = 5.5h.
        assert _elapsed_shift_seconds(
            self._WRAP_SHIFT, self._now(22, 0), current_day_only=True
        ) == pytest.approx(5.5 * 3600)

    def test_at_23h00_plus_one_hour_of_tonight(self):
        # Window: yesterday's full 6h tail + 1h of tonight so far = 7h.
        # Break (01:00 -> 01:30) already fully elapsed this morning -> net
        # 7h - 0.5h = 6.5h.
        assert _elapsed_shift_seconds(
            self._WRAP_SHIFT, self._now(23, 0), current_day_only=True
        ) == pytest.approx(6.5 * 3600)


class TestElapsedShiftSecondsCurrentDayOnlyMidnightWrapBreakCrossesMidnight:
    """The client's own reference case: 22:00 -> 06:00 shift, break
    23:30 -> 00:30 (itself midnight-wrapping, unlike the previous class's
    01:00 -> 01:30 break) -- both the shift window and its break are
    civil-day occupations, each possibly split into two disjoint pieces by
    the same primitive (`clock_window_elapsed_since_midnight`), so netting
    stays coherent."""

    _WRAP_SHIFT = {
        "start_time": "22:00",
        "end_time": "06:00",
        "break_start_time": "23:30",
        "break_end_time": "00:30",
    }

    def _now(self, hour, minute=0, day=15):
        return datetime(2026, 1, day, hour, minute, tzinfo=timezone.utc)

    def test_at_23h45_window_7h45_break_45min_net_7h(self):
        # Window: 7h45 (yesterday's full 6h tail + 1h45 of tonight so far).
        # Break: 45min elapsed (yesterday's 00:00 -> 00:30 tail [30min] +
        # tonight's 23:30 -> 23:45 so far [15min]). Net: 7h45 - 45min = 7h.
        assert _elapsed_shift_seconds(
            self._WRAP_SHIFT, self._now(23, 45), current_day_only=True
        ) == pytest.approx(7.0 * 3600)


class TestElapsedShiftSecondsCurrentDayOnlyDayShiftCoincidesWithDefault:
    """A non-wrapping day shift (06:00 -> 14:00, break 09:00 -> 09:30): the
    two modes must be IDENTICAL at every position — the whole window already
    lives on a single civil day, so "this instance's progress" and "today's
    slice" are the same slice by construction."""

    _SHIFT = {
        "start_time": "06:00",
        "end_time": "14:00",
        "break_start_time": "09:00",
        "break_end_time": "09:30",
    }

    def _now(self, hour, minute=0, day=15):
        return datetime(2026, 1, day, hour, minute, tzinfo=timezone.utc)

    @pytest.mark.parametrize(
        "hour, minute",
        [(0, 30), (2, 0), (5, 0), (6, 0), (7, 0), (9, 0), (9, 15), (9, 30), (10, 0), (14, 0), (21, 59), (22, 0), (23, 0)],
    )
    def test_modes_coincide(self, hour, minute):
        default = _elapsed_shift_seconds(self._SHIFT, self._now(hour, minute))
        current_day = _elapsed_shift_seconds(
            self._SHIFT, self._now(hour, minute), current_day_only=True
        )
        assert current_day == pytest.approx(default)


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

    def test_configured_shift_counts_its_actually_elapsed_time(self):
        """Revision 3, §5bis.4bis (C2): the in-progress day's planned time is
        the configured shift's real elapsed time (`_elapsed_shift_seconds`),
        not a fractional estimate of it."""
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

    # -- review fix W1: `down_time_scope` (when present) wins over the most
    # -- specific stored id, since `CreateDownTimeIn` doesn't forbid a client
    # -- from also sending a broader/narrower id alongside the declared scope.

    def test_stored_uap_scope_wins_even_with_a_narrower_line_and_station_id(self):
        """A ticket declared `down_time_scope="uap"` that also carries
        `production_line_id`/`workstation_id` (legitimate context, allowed by
        `CreateDownTimeIn`) must weigh the UAP, not the line/station."""
        hierarchy = _hierarchy(
            stations_by_line={"l1": [{"id": "s1"}, {"id": "s2"}], "l2": [{"id": "s3"}]},
            lines_by_uap={"u1": [{"id": "l1"}, {"id": "l2"}]},
        )
        issue = _issue(
            down_time_scope="uap", uap_id="u1", production_line_id="l1", workstation_id="s1"
        )

        assert _ticket_weight(issue, hierarchy) == 3

    def test_stored_line_scope_wins_even_with_a_narrower_station_id(self):
        hierarchy = _hierarchy(stations_by_line={"l1": [{"id": "s1"}, {"id": "s2"}]})
        issue = _issue(
            down_time_scope="production line", production_line_id="l1", workstation_id="s1"
        )

        assert _ticket_weight(issue, hierarchy) == 2

    def test_stored_plant_scope_wins_even_with_ids_present(self):
        hierarchy = _hierarchy(
            stations_by_line={"l1": [{"id": "s1"}, {"id": "s2"}]}, total_stations=9
        )
        issue = _issue(down_time_scope="plant", production_line_id="l1", workstation_id="s1")

        assert _ticket_weight(issue, hierarchy) == 9

    def test_scope_with_missing_own_id_falls_back_to_id_inference(self):
        """`down_time_scope="uap"` but no `uap_id` on the ticket (shouldn't
        happen given `CreateDownTimeIn`'s validators, but must not crash) ->
        repli on the most-specific-id inference, still floored at 1."""
        hierarchy = _hierarchy(stations_by_line={"l1": [{"id": "s1"}, {"id": "s2"}]})
        issue = _issue(down_time_scope="uap", production_line_id="l1")

        assert _ticket_weight(issue, hierarchy) == 2

    def test_missing_down_time_scope_falls_back_to_id_inference(self):
        """Legacy document with no `down_time_scope` field at all -> same
        most-specific-id inference as before revision 2's fix."""
        hierarchy = _hierarchy(stations_by_line={"l1": [{"id": "s1"}, {"id": "s2"}]})
        issue = _issue(production_line_id="l1")

        assert _ticket_weight(issue, hierarchy) == 2

    def test_unknown_down_time_scope_falls_back_to_id_inference(self):
        hierarchy = _hierarchy(stations_by_line={"l1": [{"id": "s1"}, {"id": "s2"}]})
        issue = _issue(down_time_scope="not-a-real-scope", production_line_id="l1")

        assert _ticket_weight(issue, hierarchy) == 2

    def test_weight_of_builder_memoizes_per_ticket_id(self):
        """Review fix I2: `weight_of` caches by ticket id — a second call for
        the same ticket doesn't recompute (proven here by mutating the
        hierarchy in between and observing the first, cached answer)."""
        hierarchy = _hierarchy(stations_by_line={"l1": [{"id": "s1"}, {"id": "s2"}]})
        issue = _issue(id="fixed-id", down_time_scope="production line", production_line_id="l1")
        weight_of = _weight_of_builder(hierarchy)

        assert weight_of(issue) == 2
        hierarchy["stations_by_line"]["l1"] = []
        assert weight_of(issue) == 2


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


# --------------------------------------------------------------------------
# _process_for_ticket — §5bis.7 (revision 2): read the stored `process`
# field first, fall back to DOWNTIME_TYPE_PROCESS[type] for legacy docs.
# --------------------------------------------------------------------------


class TestProcessForTicket:
    def test_stored_process_wins_even_when_type_would_map_elsewhere(self):
        """A break_down ticket (which maps to MAINTENANCE) but whose stored
        `process` is PRODUCTION is counted under PRODUCTION — the stored
        field always wins over the type mapping."""
        issue = _issue(down_time_type=DownTimeType.BREAKDOWN.value, process=Process.PRODUCTION.value)

        assert _process_for_ticket(issue) == Process.PRODUCTION.value

    def test_legacy_ticket_without_process_field_falls_back_to_type_mapping(self):
        issue = _issue(down_time_type=DownTimeType.QUALITY_ISSUE.value)
        assert "process" not in issue

        assert _process_for_ticket(issue) == Process.QUALITY.value

    def test_invalid_stored_process_falls_back_to_type_mapping(self):
        issue = _issue(down_time_type=DownTimeType.MATERIAL_SHORTAGE.value, process="not-a-process")

        assert _process_for_ticket(issue) == Process.LOGISTIC.value

    def test_invalid_process_and_unrecognized_type_returns_none(self):
        issue = _issue(down_time_type="not-a-real-type", process="not-a-process")

        assert _process_for_ticket(issue) is None

    def test_setup_changeover_type_has_no_fixed_mapping_and_no_stored_process_returns_none(self):
        """`SETUP_CHANGEOVER` is deliberately absent from
        `DOWNTIME_TYPE_PROCESS` (its process is chosen at creation time, not
        fixed) — a legacy document with no usable stored `process` resolves
        to `None` rather than crashing on a missing mapping entry."""
        assert DownTimeType.SETUP_CHANGEOVER not in DOWNTIME_TYPE_PROCESS
        issue = _issue(down_time_type=DownTimeType.SETUP_CHANGEOVER.value)

        assert _process_for_ticket(issue) is None
