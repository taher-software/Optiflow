"""API-level coverage for `.claude/specs/kpi-shift-downtime-overlap.md` — every
downtime aggregation of the KPI module only accrues while the plant is
*open* (inside a configured shift window, outside that shift's break), and a
shift's own downtime is the time the stop actually OVERLAPPED that shift's
open windows, not the whole ticket attributed via the stored `issue["shift"]`
field.

TEST-FIRST MODE. `src/app/routers/kpi/services.py` does not implement the
open-window clipping/overlap rule as of this revision — every ticket's raw
`[start, end)` interval is still counted in full regardless of shift windows,
and `by_shift`/`downtime_by_shift`/the drilldown `shift` filter/the daily
`shift` filter still attribute a ticket's WHOLE downtime to its stored
`issue["shift"]`. Every test below is therefore expected to fail on its own
numeric assertion (a downtime/duration value that still includes closed time,
or that is still keyed off the stored `shift` rather than the overlap) —
never on a fixture/import error. Scenarios are derived only from the BOM
(`.claude/specs/kpi-shift-downtime-overlap.md`) and the existing KPI test
suites' fixture/model conventions — not from `services.py`.

All tickets/periods use fixed 2026-01 dates and a UTC namespace timezone, so
no timezone-conversion arithmetic is mixed into the open-window math; the
`freeze_kpi_clock` pattern (copied from `test_kpi_dashboard.py`) is used only
for the two still-open-ticket scenarios.

Scenarios covered (§1/§2/§4/§5/§6 of the contract), one class per bullet of
the Work Unit's scenario list:
 1. `TestOverallDropsClosedTime` — the contract's own worked example: a stop
    from 20:00 to 08:00 the next day against 2 shifts (06-14/14-22, no night
    shift) drops the closed 22:00-06:00 stretch from `overall` and splits the
    remainder 2h/2h across the two shifts.
 2. `TestStopFullyInsideOneShift` — a stop entirely inside one shift's window
    is counted in full, on that shift only.
 3. `TestStopStraddlingTwoShifts` — a stop crossing a shift boundary mid-day
    splits by the actual time spent in each shift.
 4. `TestMultiDayStop` — a stop spanning several calendar days is counted, per
    day, in every shift instance it actually crosses (`/kpi/daily`).
 5. `TestNightShiftMidnightWrap` — a midnight-wrapping shift: both the
    pre-midnight and post-midnight parts of one instance count, and the tail
    of the instance that started the day BEFORE the period is counted,
    clamped to `period_start`.
 6. `TestBreakExcluded` — time inside a shift's own break is dropped from
    that shift AND from `overall` when no other shift covers it.
 7. `TestOpenTicketCountsUpToNow` — an open ticket's clamp-to-"now" and
    clamp-to-the-ticket's-own-resource-`archived_at` (resource-archiving rule
    2) both still apply, now composed with the open-window clip.
 8. `TestNoStoredShiftContributesToByShift` — a ticket with no stored `shift`
    key now contributes to `by_shift`'s DOWNTIME via overlap (it no longer
    needs a stored `shift` to show up there at all).
 9. `TestCountMttrStableWhenDowntimeMoves` — `count`/`mttr_seconds` per shift
    stay attributed by the ticket's STORED `shift`, unaffected by the fact
    that its downtime now lands on a different shift's row via overlap.
10. `TestNoConfiguredShiftWindows` — no configured shift window at all falls
    back to the 24h/day plant, downtime identical to today's raw-interval
    rule.
11. `TestWeightingPreservedUnderOverlap` — per-workstation weighting (§5bis.
    1bis) still applies on top of the clipped/split seconds, and the
    `bottleneck`/`critical` type slices stay populated on `by_shift` rows.
12. `TestByShiftRowApplicability` — a single-shift namespace still reports an
    empty `by_shift` (pre-existing, unrelated behavior, non-regression); an
    unconfigured shift (missing window) still gets no row at all.
13. `TestDrilldownDowntimeByShiftBarsUseOverlap` — drilldown's
    `downtime_by_shift` bars use the same overlap rule.
14. `TestDrilldownShiftFilterOverlap` — the drilldown `shift` filter (both
    `query.shift` and the `shift:N` path step) computes downtime as overlap
    with shift N over every ticket of the scope (regardless of its stored
    `shift`), while `count` keeps selecting by stored `shift`.
15. `TestDailyDurationMetricClipped` — `/kpi/daily?metric=duration` is
    clipped per day, with and without a `shift` filter.
16. `TestByLocationByTypeParetoDowntimeClipped` — `by_location`, `by_type`
    and `pareto_by_process` all reflect the clipped downtime, not the raw
    interval.
17. `TestSumByShiftEqualsOverall` — §6/A4: when shift windows don't overlap
    each other, summing `by_shift` downtime reproduces `overall` exactly.
"""

import uuid
from datetime import date, datetime

import pytest

import src.app.routers.kpi.services as kpi_services_module
from src.app.core.firestore import NAMESPACE_SETTINGS_COLLECTION, SETTINGS_SUBCOLLECTION
from src.app.globals.enum import DownTimeStatus, DownTimeType, Process, Role, WorkstationType

NS = "ns-kpi-open-time"
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"

BOTTLENECK = WorkstationType.BOTTLENECK.value
CRITICAL = WorkstationType.CRITICAL.value
STANDARD = WorkstationType.STANDARD.value

TWO_SHIFTS = {
    "shift_number": 2,
    "shift_1": {"start_time": "06:00", "end_time": "14:00"},
    "shift_2": {"start_time": "14:00", "end_time": "22:00"},
}


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS, timezone="UTC", company_name="Open Time Plant")


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


def _utc(hour, minute=0, day=15, month=1):
    return f"2026-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00+00:00"


def _period(day_from=15, day_to=None, month=1):
    day_to = day_to or day_from
    return {
        "from": date(2026, month, day_from).isoformat(),
        "to": date(2026, month, day_to).isoformat(),
    }


def _by_shift(res):
    return {row["id"]: row for row in res.json()["data"]["by_shift"]}


def _by_location(res):
    return {row["id"]: row for row in res.json()["data"]["by_location"]}


def _by_type(res):
    return {row["id"]: row for row in res.json()["data"]["by_type"]}


@pytest.fixture
def freeze_kpi_clock(monkeypatch):
    """Pins `services.datetime.now(tz)` to 2026-01-15 18:00 (same pattern as
    `test_kpi_dashboard.py::freeze_kpi_clock`)."""
    fixed = datetime(2026, 1, 15, 18, 0, 0)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.replace(tzinfo=tz) if tz else fixed

    monkeypatch.setattr(kpi_services_module, "datetime", _FixedDatetime)
    return fixed


# --------------------------------------------------------------------------
# 1. The contract's own worked example.
# --------------------------------------------------------------------------


class TestOverallDropsClosedTime:
    def test_stop_across_closed_window_drops_closed_time_and_splits_by_shift(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **TWO_SHIFTS)
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(20, day=15),
            resolved_at=_utc(8, day=16),
            resolved_by="agent-1",
        )

        res = client.get(
            "/kpi/dashboard", params=_period(15, 16), headers=auth_headers(owner)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # 22:00 -> 06:00 is closed time and counts nowhere: overall = 4h, not
        # the raw 12h interval.
        assert data["overall"]["downtime_seconds"] == 4 * 3600
        by_shift = _by_shift(res)
        assert by_shift["1"]["kpis"]["downtime_seconds"] == 2 * 3600
        assert by_shift["2"]["kpis"]["downtime_seconds"] == 2 * 3600


# --------------------------------------------------------------------------
# 2. Stop fully inside one shift.
# --------------------------------------------------------------------------


class TestStopFullyInsideOneShift:
    def test_stop_fully_inside_shift_counts_full_raw_duration(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **TWO_SHIFTS)
        _seed_issue(
            fake_db,
            shift=1,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
            resolved_by="agent-1",
        )

        res = client.get("/kpi/dashboard", params=_period(15), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        assert data["overall"]["downtime_seconds"] == 3600
        by_shift = _by_shift(res)
        assert by_shift["1"]["kpis"]["downtime_seconds"] == 3600
        assert by_shift["2"]["kpis"]["downtime_seconds"] == 0


# --------------------------------------------------------------------------
# 3. Stop straddling two shifts.
# --------------------------------------------------------------------------


class TestStopStraddlingTwoShifts:
    def test_stop_straddling_two_shifts_splits_by_time_in_each(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **TWO_SHIFTS)
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(13, 50),
            resolved_at=_utc(17, 0),
            resolved_by="agent-1",
        )

        res = client.get("/kpi/dashboard", params=_period(15), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # 13:50 -> 17:00: 10min in shift 1 (13:50 -> 14:00), 3h in shift 2
        # (14:00 -> 17:00).
        assert data["overall"]["downtime_seconds"] == 10 * 60 + 3 * 3600
        by_shift = _by_shift(res)
        assert by_shift["1"]["kpis"]["downtime_seconds"] == 10 * 60
        assert by_shift["2"]["kpis"]["downtime_seconds"] == 3 * 3600


# --------------------------------------------------------------------------
# 4. Multi-day stop counted in every day/instance it crosses.
# --------------------------------------------------------------------------


class TestMultiDayStop:
    def test_multi_day_stop_counted_in_each_day_it_crosses(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **TWO_SHIFTS)
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=f"2026-02-01T00:00:00+00:00",
            resolved_at=f"2026-02-03T00:00:00+00:00",
            resolved_by="agent-1",
        )

        res = client.get(
            "/kpi/daily",
            params={
                "metric": "duration",
                "scope_kind": "plant",
                "from": "2026-02-01",
                "to": "2026-02-03",
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        points = {p["date"]: p["value"] for p in res.json()["data"]["points"]}

        # Each open day (06:00-22:00, 16h) crossed by the stop counts its
        # own open time; the ticket ends exactly at day 3's midnight, so day
        # 3 gets nothing.
        assert points["2026-02-01"] == 16 * 3600
        assert points["2026-02-02"] == 16 * 3600
        assert points["2026-02-03"] == 0


# --------------------------------------------------------------------------
# 5. Night shift, midnight wrap.
# --------------------------------------------------------------------------


class TestNightShiftMidnightWrap:
    NIGHT_SHIFT = {
        "shift_number": 1,
        "shift_1": {"start_time": "22:00", "end_time": "06:00"},
    }

    def test_night_shift_tail_from_day_before_period_counts_clamped_to_period_start(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **self.NIGHT_SHIFT)
        _seed_issue(
            fake_db,
            shift=1,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(23, day=14),
            resolved_at=_utc(2, day=15),
            resolved_by="agent-1",
        )

        res = client.get("/kpi/dashboard", params=_period(15), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # Ticket interval clamped to period_start (00:00 on the 15th) -> 02:00.
        # That [00:00, 02:00] slice is the TAIL of the night-shift instance
        # that started the day before the period (14th 22:00 -> 15th 06:00),
        # so it is entirely open -> full 2h counted.
        assert data["overall"]["downtime_seconds"] == 2 * 3600
        # Created before the period -> excluded from `count` (current-range
        # only, unaffected carry-over rule).
        assert data["overall"]["count"] == 0

    def test_night_shift_spans_midnight_pre_and_post_both_count(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **self.NIGHT_SHIFT)
        _seed_issue(
            fake_db,
            shift=1,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(21, day=15),
            resolved_at=_utc(1, day=16),
            resolved_by="agent-1",
        )

        res = client.get(
            "/kpi/dashboard", params=_period(15, 16), headers=auth_headers(owner)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # 21:00 -> 22:00 is closed (excluded); 22:00 -> 24:00 (2h) and
        # 00:00 -> 01:00 (1h) are both inside the same night-shift instance
        # -> 3h total, not the raw 4h interval.
        assert data["overall"]["downtime_seconds"] == 3 * 3600
        assert data["overall"]["count"] == 1


# --------------------------------------------------------------------------
# 6. Break excluded, both from its own shift and from `overall`.
# --------------------------------------------------------------------------


class TestBreakExcluded:
    def test_break_excluded_from_shift_and_overall_when_uncovered(
        self, client, seed_user, auth_headers, fake_db
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
            created_at=_utc(9, 0),
            resolved_at=_utc(11, 0),
            resolved_by="agent-1",
        )

        res = client.get("/kpi/dashboard", params=_period(15), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # 09:00 -> 11:00 minus the 10:00-10:30 break = 1h + 30min = 5400s;
        # no other shift covers 10:00-10:30, so it's dropped from `overall`
        # too, not just from the shift's own row.
        assert data["overall"]["downtime_seconds"] == 5400


# --------------------------------------------------------------------------
# 7. Open ticket clamps: "now", and the ticket's own resource `archived_at`.
# --------------------------------------------------------------------------


class TestOpenTicketCountsUpToNow:
    def test_open_ticket_counts_up_to_now(
        self, client, seed_user, auth_headers, fake_db, freeze_kpi_clock
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **TWO_SHIFTS)
        _seed_issue(
            fake_db,
            status=DownTimeStatus.PENDING.value,
            created_at=_utc(17, 0),
        )

        res = client.get("/kpi/dashboard", params=_period(15), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # "now" frozen at 18:00 -> 17:00 -> 18:00 = 1h, entirely inside
        # shift 2 (14:00-22:00).
        assert data["overall"]["downtime_seconds"] == 3600
        assert data["overall"]["count"] == 1

    def test_open_ticket_counts_up_to_own_resource_archived_at(
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
        _seed_settings(fake_db, **TWO_SHIFTS)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(
            namespace_id=NS,
            production_line_id=line["id"],
            archived_at="2026-01-15T17:30:00+00:00",
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.PENDING.value,
            created_at=_utc(17, 0),
        )

        res = client.get("/kpi/dashboard", params=_period(15), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # Bounded at the resource's own `archived_at` (17:30), not "now"
        # (18:00) -> 17:00 -> 17:30 = 30min, inside shift 2.
        assert data["overall"]["downtime_seconds"] == 1800
        by_location = _by_location(res)
        assert by_location[station["id"]]["kpis"]["downtime_seconds"] == 1800


# --------------------------------------------------------------------------
# 8. A ticket with no stored `shift` still contributes to `by_shift` via
#    overlap.
# --------------------------------------------------------------------------


class TestNoStoredShiftContributesToByShift:
    def test_ticket_without_stored_shift_contributes_to_its_overlapping_shift_row(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **TWO_SHIFTS)
        issue = _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(15, 0),
            resolved_at=_utc(16, 0),
            resolved_by="agent-1",
        )
        issue.pop("shift", None)
        fake_db.collection(DOWN_TIME_COLLECTION).document(NS).collection(
            ISSUES_SUBCOLLECTION
        ).document(issue["id"]).set(issue)

        res = client.get("/kpi/dashboard", params=_period(15), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        assert data["overall"]["count"] == 1
        assert data["overall"]["downtime_seconds"] == 3600

        by_shift = _by_shift(res)
        # No overlap with shift 1's window (06:00-14:00).
        assert by_shift["1"]["kpis"]["downtime_seconds"] == 0
        assert by_shift["1"]["kpis"]["count"] == 0
        # 15:00-16:00 overlaps shift 2's window (14:00-22:00) fully, even
        # though the ticket carries no stored `shift` at all.
        assert by_shift["2"]["kpis"]["downtime_seconds"] == 3600
        # `count` still requires a matching STORED `shift` -> stays 0.
        assert by_shift["2"]["kpis"]["count"] == 0


# --------------------------------------------------------------------------
# 9. `count`/`mttr_seconds` per shift stay attributed by stored `shift`.
# --------------------------------------------------------------------------


class TestCountMttrStableWhenDowntimeMoves:
    def test_count_and_mttr_stay_by_stored_shift_even_when_downtime_moves(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **TWO_SHIFTS)
        # Stored shift 1, but the ticket's ACTUAL time is entirely inside
        # shift 2's window.
        _seed_issue(
            fake_db,
            shift=1,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(15, 0),
            resolved_at=_utc(17, 0),
            resolved_by="agent-1",
        )

        res = client.get("/kpi/dashboard", params=_period(15), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_shift = _by_shift(res)

        # `count`/`mttr` still select by the STORED `shift` (1), regardless
        # of where the downtime itself landed.
        assert by_shift["1"]["kpis"]["count"] == 1
        assert by_shift["1"]["kpis"]["mttr_seconds"] == 7200
        # But its downtime overlaps shift 1's window not at all.
        assert by_shift["1"]["kpis"]["downtime_seconds"] == 0

        # Shift 2 gets the downtime via overlap, but no count (the ticket's
        # STORED shift is 1, not 2).
        assert by_shift["2"]["kpis"]["downtime_seconds"] == 7200
        assert by_shift["2"]["kpis"]["count"] == 0


# --------------------------------------------------------------------------
# 10. No configured shift windows -> 24h/day fallback, unchanged.
# --------------------------------------------------------------------------


class TestNoConfiguredShiftWindows:
    def test_no_shift_windows_downtime_equals_raw_interval(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        # No `_seed_settings` call at all -> namespace has no settings
        # document, same fallback as `test_kpi_dashboard.py`'s
        # `TestNamespaceMetaShifts::test_namespace_with_no_settings_document_returns_empty_list`.
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(20, day=15),
            resolved_at=_utc(8, day=16),
            resolved_by="agent-1",
        )

        res = client.get(
            "/kpi/dashboard", params=_period(15, 16), headers=auth_headers(owner)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # Plant open 24h/day fallback -> the raw 12h interval, unchanged.
        assert data["overall"]["downtime_seconds"] == 12 * 3600


# --------------------------------------------------------------------------
# 11. Weighting preserved; bottleneck/critical slices stay populated on
#     `by_shift`.
# --------------------------------------------------------------------------


class TestWeightingPreservedUnderOverlap:
    def test_weighted_multi_workstation_ticket_downtime_still_weighted_after_clipping(
        self,
        client,
        seed_user,
        auth_headers,
        fake_db,
        seed_uap,
        seed_production_line,
        seed_workstation,
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **TWO_SHIFTS)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK)
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=CRITICAL)
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(13, 50),
            resolved_at=_utc(17, 0),
            resolved_by="agent-1",
        )

        res = client.get("/kpi/dashboard", params=_period(15), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # Raw split: 600s (shift 1) + 10800s (shift 2) = 11400s per unit
        # weight; weight = 3 (line's 3 stations).
        assert data["overall"]["downtime_seconds"] == 3 * 11400

        by_shift = _by_shift(res)
        assert by_shift["1"]["kpis"]["downtime_seconds"] == 3 * 600
        assert by_shift["2"]["kpis"]["downtime_seconds"] == 3 * 10800
        # bottleneck/critical slices stay populated (namespace perimeter
        # holds one of each) and are themselves weighted+split.
        assert by_shift["1"]["kpis"]["bottleneck"] is not None
        assert by_shift["1"]["kpis"]["bottleneck"]["downtime_seconds"] == 600
        assert by_shift["1"]["kpis"]["critical"]["downtime_seconds"] == 600
        assert by_shift["2"]["kpis"]["bottleneck"]["downtime_seconds"] == 10800
        assert by_shift["2"]["kpis"]["critical"]["downtime_seconds"] == 10800


# --------------------------------------------------------------------------
# 12. `by_shift` row applicability, non-regression + unconfigured shift.
# --------------------------------------------------------------------------


class TestByShiftRowApplicability:
    def test_single_shift_namespace_by_shift_is_empty(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        _seed_issue(
            fake_db,
            shift=1,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
            resolved_by="agent-1",
        )

        res = client.get("/kpi/dashboard", params=_period(15), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["by_shift"] == []

    def test_shift_without_configured_window_has_no_row(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(
            fake_db,
            shift_number=2,
            shift_1={"start_time": "06:00", "end_time": "14:00"},
            shift_2=None,
        )
        _seed_issue(
            fake_db,
            shift=1,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
            resolved_by="agent-1",
        )

        res = client.get("/kpi/dashboard", params=_period(15), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_shift = _by_shift(res)
        assert set(by_shift.keys()) == {"1"}


# --------------------------------------------------------------------------
# 13. Drilldown `downtime_by_shift` bars use the overlap rule.
# --------------------------------------------------------------------------


class TestDrilldownDowntimeByShiftBarsUseOverlap:
    def test_drilldown_downtime_by_shift_bars_use_overlap_rule(
        self,
        client,
        seed_user,
        auth_headers,
        fake_db,
        seed_uap,
        seed_production_line,
        seed_workstation,
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **TWO_SHIFTS)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            production_line_id=line["id"],
            shift=1,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(13, 50),
            resolved_at=_utc(17, 0),
            resolved_by="agent-1",
        )

        res = client.get(
            "/kpi/drilldown",
            params={**_period(15), "path": f"uap:{uap['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        bars = {bar["id"]: bar["value"] for bar in res.json()["data"]["downtime_by_shift"]}
        assert bars["1"] == 10 * 60
        assert bars["2"] == 3 * 3600


# --------------------------------------------------------------------------
# 14. Drilldown `shift` filter (query param + path step) uses overlap for
#     downtime, stored `shift` for `count`.
# --------------------------------------------------------------------------


class TestDrilldownShiftFilterOverlap:
    def _seed_mismatched_shift_ticket(self, fake_db, seed_uap, seed_production_line, seed_workstation):
        _seed_settings(fake_db, **TWO_SHIFTS)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            production_line_id=line["id"],
            shift=1,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(15, 0),
            resolved_at=_utc(17, 0),
            resolved_by="agent-1",
        )
        return uap

    def test_query_shift_filter_downtime_is_overlap_count_is_stored_shift(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        uap = self._seed_mismatched_shift_ticket(fake_db, seed_uap, seed_production_line, seed_workstation)

        res = client.get(
            "/kpi/drilldown",
            params={**_period(15), "path": f"uap:{uap['id']}", "shift": "2"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        kpis = res.json()["data"]["kpis"]

        # Downtime: overlap of the (stored-shift-1) ticket with shift 2's
        # own window -> full 2h (15:00-17:00 is entirely inside 14:00-22:00).
        assert kpis["downtime_seconds"] == 2 * 3600
        # Count: still selects tickets by STORED `shift` == "2" -> none.
        assert kpis["count"] == 0

    def test_path_shift_step_downtime_is_overlap_count_is_stored_shift(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        self._seed_mismatched_shift_ticket(fake_db, seed_uap, seed_production_line, seed_workstation)

        res = client.get(
            "/kpi/drilldown",
            params={**_period(15), "path": "shift:2"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        kpis = res.json()["data"]["kpis"]

        assert kpis["downtime_seconds"] == 2 * 3600
        assert kpis["count"] == 0


# --------------------------------------------------------------------------
# 15. `/kpi/daily?metric=duration`, with and without a `shift` filter.
# --------------------------------------------------------------------------


class TestDailyDurationMetricClipped:
    def _seed_overnight_ticket(self, fake_db):
        _seed_settings(fake_db, **TWO_SHIFTS)
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(20, day=15),
            resolved_at=_utc(8, day=16),
            resolved_by="agent-1",
        )

    def test_daily_duration_clipped_to_open_windows_per_day(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        self._seed_overnight_ticket(fake_db)

        res = client.get(
            "/kpi/daily",
            params={
                "metric": "duration",
                "scope_kind": "plant",
                "from": "2026-01-15",
                "to": "2026-01-16",
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        points = {p["date"]: p["value"] for p in res.json()["data"]["points"]}

        # 15th: 20:00-24:00 overlaps shift 2 (14-22) only for 20:00-22:00 =
        # 2h. 16th: 00:00-08:00 overlaps shift 1 (06-14) only for 06:00-08:00
        # = 2h.
        assert points["2026-01-15"] == 2 * 3600
        assert points["2026-01-16"] == 2 * 3600

    def test_daily_duration_with_shift_filter_uses_overlap_per_day(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        self._seed_overnight_ticket(fake_db)

        res = client.get(
            "/kpi/daily",
            params={
                "metric": "duration",
                "scope_kind": "plant",
                "shift": "2",
                "from": "2026-01-15",
                "to": "2026-01-16",
            },
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        points = {p["date"]: p["value"] for p in res.json()["data"]["points"]}

        # 15th: overlap with shift 2's own window is the same 2h. 16th: the
        # 00:00-08:00 slice never touches shift 2's window (14:00-22:00) ->
        # 0, unlike the unfiltered case above.
        assert points["2026-01-15"] == 2 * 3600
        assert points["2026-01-16"] == 0


# --------------------------------------------------------------------------
# 16. `by_location`/`by_type`/`pareto_by_process` downtime clipped.
# --------------------------------------------------------------------------


class TestByLocationByTypeParetoDowntimeClipped:
    def test_by_location_downtime_clipped_to_open_windows(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **TWO_SHIFTS)
        uap = seed_uap(namespace_id=NS)
        # A 2nd UAP forces `_pick_location_kind` to resolve `by_location` at
        # "uap" granularity, matching `test_kpi_dashboard.py`'s
        # `seeded_scenario` pattern (a single UAP would descend further).
        seed_uap(namespace_id=NS)
        seed_production_line(namespace_id=NS, uap_id=uap["id"])
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=uap["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(20, day=15),
            resolved_at=_utc(8, day=16),
            resolved_by="agent-1",
        )

        res = client.get(
            "/kpi/dashboard", params=_period(15, 16), headers=auth_headers(owner)
        )
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert by_location[uap["id"]]["kpis"]["downtime_seconds"] == 4 * 3600

    def test_by_type_downtime_clipped_to_open_windows(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **TWO_SHIFTS)
        _seed_issue(
            fake_db,
            down_time_type=DownTimeType.BREAKDOWN.value,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(20, day=15),
            resolved_at=_utc(8, day=16),
            resolved_by="agent-1",
        )

        res = client.get(
            "/kpi/dashboard", params=_period(15, 16), headers=auth_headers(owner)
        )
        assert res.status_code == 200, res.text
        by_type = _by_type(res)
        assert by_type["break_down"]["kpis"]["downtime_seconds"] == 4 * 3600

    def test_pareto_by_process_downtime_clipped_to_open_windows(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **TWO_SHIFTS)
        # Maintenance ticket: raw 12h, clipped to 4h (crosses closed time).
        _seed_issue(
            fake_db,
            process=Process.MAINTENANCE.value,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(20, day=15),
            resolved_at=_utc(8, day=16),
            resolved_by="agent-1",
        )
        # Quality ticket: raw 1h, fully inside shift 1 -> unaffected.
        _seed_issue(
            fake_db,
            process=Process.QUALITY.value,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7, day=16),
            resolved_at=_utc(8, day=16),
            resolved_by="agent-2",
        )

        res = client.get(
            "/kpi/dashboard", params=_period(15, 16), headers=auth_headers(owner)
        )
        assert res.status_code == 200, res.text
        pareto = res.json()["data"]["pareto_by_process"]

        # Clipped totals: maintenance = 4h, quality = 1h -> maintenance's
        # share is 4/5 = 0.8. Unclipped (raw 12h/1h) it would be ~0.923 --
        # the lower figure only holds if pareto itself is built off the
        # clipped downtime, not the raw interval.
        row = next(r for r in pareto if r["id"] == Process.MAINTENANCE.value)
        assert row["share"] == pytest.approx(0.8, abs=1e-4)


# --------------------------------------------------------------------------
# 17. Sum of `by_shift` downtime equals `overall` when shifts don't overlap.
# --------------------------------------------------------------------------


class TestSumByShiftEqualsOverall:
    def test_sum_by_shift_equals_overall_when_shifts_dont_overlap(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db, **TWO_SHIFTS)
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(20, day=15),
            resolved_at=_utc(8, day=16),
            resolved_by="agent-1",
        )
        # A second ticket, fully inside a single shift, to make the
        # reconciliation non-trivial.
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7, day=16),
            resolved_at=_utc(9, day=16),
            resolved_by="agent-2",
        )

        res = client.get(
            "/kpi/dashboard", params=_period(15, 16), headers=auth_headers(owner)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        total_by_shift = sum(row["kpis"]["downtime_seconds"] for row in data["by_shift"])
        assert total_by_shift == data["overall"]["downtime_seconds"]
