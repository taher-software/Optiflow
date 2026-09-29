"""API-level coverage for decision **A5** of
`.claude/specs/kpi-shift-downtime-overlap.md` — when `GET /kpi/drilldown` is
narrowed by a shift filter (`query.shift` or the path step `shift:N`), every
downtime figure BELOW the header (`children` rows, `pareto_by_process`,
`downtime_by_type`) is computed over ALL scope tickets, clipped to shift N's
own open windows — the same overlap rule as the header — regardless of each
ticket's stored `issue["shift"]`. `count`/`mttr` in those rows keep selecting
tickets by the STORED `shift` (A2), unaffected.

TEST-FIRST MODE. `src/app/routers/kpi/services.py` does not implement A5 as
of this revision: drilldown breakdown rows below the header still attribute
a ticket's downtime to its STORED `shift` (or ignore the shift filter
entirely for `pareto_by_process`/`downtime_by_type`), so every value-bearing
assertion below is expected to fail on its own numeric assertion — never on
a fixture/import error. Scenarios are derived only from the BOM
(`.claude/specs/kpi-shift-downtime-overlap.md` §6/A5) and this suite's own
fixtures — never from `services.py`. Local seeding/clock helpers are copied
from `tests/api/test_kpi_open_time.py` (module-private there, so re-declared
here rather than imported).

Fixed scenario shared by every test below: 2 shifts, 06:00-14:00 (shift 1)
and 14:00-22:00 (shift 2), no night shift, no break. One UAP with two lines
(A and B), one workstation each. "Ticket A" is stored on line A with
`shift=1` but its raw interval (12:00-18:00, same day) actually straddles
BOTH shift windows (2h in shift 1's window, 4h in shift 2's) — the
mismatch the whole suite exploits to tell the overlap rule apart from the
stored-`shift` rule. "Ticket B" (pareto/type-bar scenarios only) is stored
on line B with `shift=2` but sits entirely inside shift 1's window
(07:00-10:00, 3h) — the opposite mismatch, so a shift filter's ranking
flips depending on which rule (overlap vs. stored-shift) computed it.

Scenarios covered, one class per bullet of the Work Unit's scenario list:
 1/2. `TestDrilldownShiftFilterHeaderAndChildren` — `shift=2` (header 4h,
      line-A child 4h) and `shift=1` (header 2h, line-A child 2h, not the
      raw 6h) via the `query.shift` param; Σ children == header both ways.
 3.   `TestDrilldownShiftPathStepBreakdowns` — the same `shift=1` case via
      the path step `uap:X>shift:1` instead of the query param.
 4.   `TestDrilldownParetoUnderShiftFilterUsesOverlap` — `pareto_by_process`
      under `shift=1` ranks/weighs processes by shift-clipped overlap
      (quality > maintenance), the opposite of what filtering tickets by
      their stored `shift` would produce (which would show maintenance
      alone, ticket A, and drop quality/ticket B entirely).
 5.   `TestDrilldownDowntimeByTypeUnderShiftFilterUsesOverlap` —
      `downtime_by_type` bars under `shift=1` reflect the same overlap
      values.
 6.   `TestDrilldownChildrenCountMttrKeepStoredShift` — the line-A child
      row's `count`/`mttr_seconds` stay keyed by the ticket's STORED
      `shift` (1) even though its downtime now also appears, via overlap,
      under a `shift=2` filter.
 7.   `TestDrilldownNoShiftFilterNonRegression` — without any shift filter,
      `children`/`pareto_by_process`/`downtime_by_type` are unchanged
      (plant-open-window clipping only, no shift-window split); the ranking
      differs from both shift-filtered cases above, which is the point.
"""

import uuid
from datetime import date

import pytest

from src.app.core.firestore import NAMESPACE_SETTINGS_COLLECTION, SETTINGS_SUBCOLLECTION
from src.app.globals.enum import DownTimeStatus, DownTimeType, Process, Role

NS = "ns-kpi-shift-filter-breakdowns"
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"

TWO_SHIFTS = {
    "shift_number": 2,
    "shift_1": {"start_time": "06:00", "end_time": "14:00"},
    "shift_2": {"start_time": "14:00", "end_time": "22:00"},
}


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS, timezone="UTC", company_name="Shift Filter Plant")


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


def _seed_scope(fake_db, seed_uap, seed_production_line, seed_workstation):
    """One UAP with two lines (A/B), one workstation each — the shared
    drilldown scope for every test in this module."""
    _seed_settings(fake_db, **TWO_SHIFTS)
    uap = seed_uap(namespace_id=NS)
    line_a = seed_production_line(namespace_id=NS, uap_id=uap["id"])
    line_b = seed_production_line(namespace_id=NS, uap_id=uap["id"])
    station_a = seed_workstation(namespace_id=NS, production_line_id=line_a["id"])
    station_b = seed_workstation(namespace_id=NS, production_line_id=line_b["id"])
    return {
        "uap": uap,
        "line_a": line_a,
        "line_b": line_b,
        "station_a": station_a,
        "station_b": station_b,
    }


def _seed_ticket_a(fake_db, scope, **overrides):
    """Stored `shift=1`, on line A, raw interval 12:00-18:00 (6h) straddling
    BOTH shift windows: 2h inside shift 1's window, 4h inside shift 2's."""
    defaults = dict(
        down_time_scope="work station",
        workstation_id=scope["station_a"]["id"],
        production_line_id=scope["line_a"]["id"],
        shift=1,
        down_time_type=DownTimeType.BREAKDOWN.value,
        process=Process.MAINTENANCE.value,
        status=DownTimeStatus.CLOSED.value,
        created_at=_utc(12),
        resolved_at=_utc(18),
        resolved_by="agent-1",
    )
    defaults.update(overrides)
    return _seed_issue(fake_db, **defaults)


def _seed_ticket_b(fake_db, scope, **overrides):
    """Stored `shift=2`, on line B, raw interval 07:00-10:00 (3h), entirely
    inside shift 1's window (the mirror-image mismatch of ticket A)."""
    defaults = dict(
        down_time_scope="work station",
        workstation_id=scope["station_b"]["id"],
        production_line_id=scope["line_b"]["id"],
        shift=2,
        down_time_type=DownTimeType.QUALITY_ISSUE.value,
        process=Process.QUALITY.value,
        status=DownTimeStatus.CLOSED.value,
        created_at=_utc(7),
        resolved_at=_utc(10),
        resolved_by="agent-2",
    )
    defaults.update(overrides)
    return _seed_issue(fake_db, **defaults)


def _children(res):
    return {row["id"]: row for row in res.json()["data"]["children"]}


def _pareto(res):
    return {row["id"]: row for row in res.json()["data"]["pareto_by_process"]}


def _type_bars(res):
    return {bar["id"]: bar["value"] for bar in res.json()["data"]["downtime_by_type"]}


# --------------------------------------------------------------------------
# 1/2. `shift=2` and `shift=1` (query param): header + line-A child downtime
#      is the overlap, not the ticket's raw duration; Σ children == header.
# --------------------------------------------------------------------------


class TestDrilldownShiftFilterHeaderAndChildren:
    def test_shift_two_header_and_line_a_child_downtime_is_four_hours(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        scope = _seed_scope(fake_db, seed_uap, seed_production_line, seed_workstation)
        _seed_ticket_a(fake_db, scope)

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{scope['uap']['id']}", "shift": "2"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # 14:00-18:00 of ticket A's raw 12:00-18:00 interval overlaps shift
        # 2's window (14:00-22:00) -> 4h, not the raw 6h.
        assert data["kpis"]["downtime_seconds"] == 4 * 3600
        children = _children(res)
        assert children[scope["line_a"]["id"]]["kpis"]["downtime_seconds"] == 4 * 3600
        # Line B has no ticket at all; whether a zero-downtime child row is
        # still returned is not asserted here — only that IF it is, its
        # downtime is 0 (never KeyError on an absent row).
        assert children.get(scope["line_b"]["id"], {"kpis": {"downtime_seconds": 0}})[
            "kpis"
        ]["downtime_seconds"] == 0
        total_children = sum(row["kpis"]["downtime_seconds"] for row in data["children"])
        assert total_children == data["kpis"]["downtime_seconds"]

    def test_shift_one_header_and_line_a_child_downtime_is_two_hours_not_six(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        scope = _seed_scope(fake_db, seed_uap, seed_production_line, seed_workstation)
        _seed_ticket_a(fake_db, scope)

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{scope['uap']['id']}", "shift": "1"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # 12:00-14:00 overlaps shift 1's window (06:00-14:00) -> 2h. The
        # ticket is stored with `shift=1` too, but the point of the overlap
        # rule is that this is NOT the reason it counts here: the full raw
        # duration (6h) must NOT appear.
        assert data["kpis"]["downtime_seconds"] == 2 * 3600
        children = _children(res)
        assert children[scope["line_a"]["id"]]["kpis"]["downtime_seconds"] == 2 * 3600
        total_children = sum(row["kpis"]["downtime_seconds"] for row in data["children"])
        assert total_children == data["kpis"]["downtime_seconds"]


# --------------------------------------------------------------------------
# 3. Same as the `shift=1` case above, via the path step `shift:N` instead
#    of the query param.
# --------------------------------------------------------------------------


class TestDrilldownShiftPathStepBreakdowns:
    def test_path_shift_step_header_and_line_a_child_downtime_is_two_hours(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        scope = _seed_scope(fake_db, seed_uap, seed_production_line, seed_workstation)
        _seed_ticket_a(fake_db, scope)

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{scope['uap']['id']}>shift:1"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        assert data["kpis"]["downtime_seconds"] == 2 * 3600
        children = _children(res)
        assert children[scope["line_a"]["id"]]["kpis"]["downtime_seconds"] == 2 * 3600


# --------------------------------------------------------------------------
# 4. `pareto_by_process` under a shift filter uses the overlap, not the
#    stored-shift rule (ranking flips depending on which is used).
# --------------------------------------------------------------------------


class TestDrilldownParetoUnderShiftFilterUsesOverlap:
    def test_pareto_ranks_by_overlap_not_stored_shift(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        scope = _seed_scope(fake_db, seed_uap, seed_production_line, seed_workstation)
        _seed_ticket_a(fake_db, scope)  # maintenance, stored shift=1
        _seed_ticket_b(fake_db, scope)  # quality, stored shift=2

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{scope['uap']['id']}", "shift": "1"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        pareto = _pareto(res)

        # Overlap with shift 1's window over ALL scope tickets: ticket A
        # (maintenance) contributes 2h, ticket B (quality, entirely inside
        # shift 1 though stored shift=2) contributes 3h -> quality ranks
        # FIRST with the larger share. A stored-shift rule would instead
        # keep only ticket A (stored shift=1) and drop quality entirely,
        # with maintenance at 100% share -- the opposite of this.
        # Assert presence first (an AssertionError, not a KeyError) — under
        # today's stored-shift rule quality is absent from the shift=1
        # pareto entirely, since ticket B's STORED shift is 2.
        assert Process.QUALITY.value in pareto
        assert pareto[Process.QUALITY.value]["share"] == pytest.approx(3 / 5, abs=1e-4)
        assert pareto[Process.MAINTENANCE.value]["share"] == pytest.approx(2 / 5, abs=1e-4)
        ranking = [row["id"] for row in res.json()["data"]["pareto_by_process"]]
        assert ranking[0] == Process.QUALITY.value


# --------------------------------------------------------------------------
# 5. `downtime_by_type` bars under a shift filter use the overlap.
# --------------------------------------------------------------------------


class TestDrilldownDowntimeByTypeUnderShiftFilterUsesOverlap:
    def test_downtime_by_type_bars_reflect_overlap_not_stored_shift(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        scope = _seed_scope(fake_db, seed_uap, seed_production_line, seed_workstation)
        _seed_ticket_a(fake_db, scope)  # break_down, stored shift=1
        _seed_ticket_b(fake_db, scope)  # quality_issue, stored shift=2

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{scope['uap']['id']}", "shift": "1"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        bars = _type_bars(res)

        # `downtime_by_type` bar ids are the frontend type slugs
        # ("break_down"/"quality_issue"), NOT `DownTimeType.<X>.value`
        # ("break down"/"quality issue" with spaces) — see how existing
        # suites assert this (`test_kpi_open_time.py`,
        # `test_kpi_dashboard.py`, `test_kpi_weighting.py`).
        assert bars["break_down"] == 2 * 3600
        assert bars["quality_issue"] == 3 * 3600


# --------------------------------------------------------------------------
# 6. `count`/`mttr` in children rows keep the stored `shift` (A2),
#    unaffected by where the downtime itself lands via overlap.
# --------------------------------------------------------------------------


class TestDrilldownChildrenCountMttrKeepStoredShift:
    def test_line_a_count_is_zero_under_mismatched_shift_filter_despite_downtime(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        scope = _seed_scope(fake_db, seed_uap, seed_production_line, seed_workstation)
        _seed_ticket_a(fake_db, scope)  # stored shift=1

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{scope['uap']['id']}", "shift": "2"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        children = _children(res)

        # Downtime lands here via overlap (4h), but `count` still selects by
        # the STORED `shift` (1, not 2) -> 0.
        assert children[scope["line_a"]["id"]]["kpis"]["downtime_seconds"] == 4 * 3600
        assert children[scope["line_a"]["id"]]["kpis"]["count"] == 0

    def test_line_a_count_and_mttr_under_matching_shift_filter(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        scope = _seed_scope(fake_db, seed_uap, seed_production_line, seed_workstation)
        _seed_ticket_a(fake_db, scope)  # stored shift=1

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{scope['uap']['id']}", "shift": "1"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        children = _children(res)
        row = children[scope["line_a"]["id"]]["kpis"]

        assert row["downtime_seconds"] == 2 * 3600
        assert row["count"] == 1
        # `mttr_seconds` is the raw created_at -> resolved_at of the CLOSED
        # ticket (6h), unaffected by the shift-window clip applied to
        # `downtime_seconds`.
        assert row["mttr_seconds"] == 6 * 3600


# --------------------------------------------------------------------------
# 7. Non-regression: without any shift filter, children/pareto/by-type
#    values are unchanged (plant-open-window clipping only).
# --------------------------------------------------------------------------


class TestDrilldownNoShiftFilterNonRegression:
    def test_children_pareto_and_type_bars_use_plant_window_clip_only(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        scope = _seed_scope(fake_db, seed_uap, seed_production_line, seed_workstation)
        _seed_ticket_a(fake_db, scope)  # 12:00-18:00, 6h, maintenance/break_down
        _seed_ticket_b(fake_db, scope)  # 07:00-10:00, 3h, quality/quality_issue

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{scope['uap']['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        # No shift filter -> each ticket's downtime is its full raw
        # duration, clipped only to the plant's open windows (06:00-22:00,
        # which both raw intervals sit fully inside) -- NOT split per shift
        # window. Ticket A = 6h, ticket B = 3h.
        assert data["kpis"]["downtime_seconds"] == 9 * 3600
        children = _children(res)
        assert children[scope["line_a"]["id"]]["kpis"]["downtime_seconds"] == 6 * 3600
        assert children[scope["line_b"]["id"]]["kpis"]["downtime_seconds"] == 3 * 3600

        # Ranking here (maintenance > quality) is the OPPOSITE of the
        # shift=1-filtered case above (quality > maintenance) -- proof the
        # two code paths are genuinely different, not coincidentally equal.
        pareto = _pareto(res)
        assert pareto[Process.MAINTENANCE.value]["share"] == pytest.approx(6 / 9, abs=1e-4)
        assert pareto[Process.QUALITY.value]["share"] == pytest.approx(3 / 9, abs=1e-4)
        ranking = [row["id"] for row in data["pareto_by_process"]]
        assert ranking[0] == Process.MAINTENANCE.value

        bars = _type_bars(res)
        assert bars["break_down"] == 6 * 3600
        assert bars["quality_issue"] == 3 * 3600
