"""API-level coverage for the reconciliation gap between `_row_weight` and
`_row_type_weights` (`src/app/routers/kpi/services.py`) on a `by_location`
breakdown row that a wide-scope ticket SPREADS into (the "spread" branch of
both functions, as opposed to a ticket declared directly "own" on that row).

THE GAP (see `_row_type_weights`'s own "KNOWN GAP" docstring paragraph,
`src/app/routers/kpi/services.py`, resource-archiving rule 4): `_row_weight`'s
spread branch filters a row's raw station list down to the ones still active
at the ticket's own `created_at` before counting/flooring. `_row_type_weights`'s
spread branch instead returns the row's STATIC, unfiltered per-type station
counts (`type_counts_by_line`/`type_counts_by_uap`, precomputed once in
`_location_hierarchy` with no regard for archiving). Whenever a spread row
mixes archived and active stations, the three type slices (bottleneck +
critical + the unexposed standard share) OVER-COUNT relative to the row's own
weight — the row's `downtime_seconds` no longer equals
`bottleneck.downtime_seconds + critical.downtime_seconds + <standard share>`.

TEST-EXISTING-BUG MODE (not test-first): the implementation already exists
and the rest of the suite is green (904 passed prior to this file). Every
test below asserts the STANDING invariant the developer stated: for any
`by_location` row, at any scope, the sum of the type slices equals the row's
own weight, and the sum of the rows equals the header total — including rows
that mix several workstation types and a mix of active/archived resources.
Tests that exercise the "spread" branch on a mixed row are expected to FAIL
against the current implementation (the gap above); tests that exercise the
"own" branch, or a row with no archival at all, already satisfy the
invariant today and are included as non-regression / behavior-pinning
guards, not to prove the bug.

No `xfail` markers here: this Work Unit's deliverable is the failing suite
itself (its own hand-back explains, per test, why it currently fails), not a
documented-and-skipped known issue — the fix is a separate, later Work Unit.

Every fixture below uses `down_time_scope="plant"` with NO stored location
id, the shape that reliably lands a ticket in EVERY row of a `by_location`
breakdown via `_locations_for_ticket`'s spread rule (§2), so each row's slice
computation always takes the "spread" branch under test (`own is None` for
that row's `kind`) rather than the "own" branch (already correct, covered by
`tests/api/test_kpi_type_slices.py`).

All tickets use fixed 2026-01-15 timestamps in the past relative to the real
wall-clock "now" at test-run time (today's real date is 2026-09-10, tickets
are CLOSED), so no `now`-clamp/freeze-time patching is needed.

Scope boundary: `GET /kpi/dashboard` only, same boundary as
`tests/api/test_kpi_resource_archiving.py` (KPI OUTPUT only; archiving
endpoints/cascade/visibility are covered and frozen elsewhere). Does not
touch `tests/api/test_kpi_type_slices.py`, `tests/api/test_kpi_scope_spread.py`,
`tests/api/test_kpi_resource_archiving.py`, `tests/api/test_resource_archiving.py`
or `tests/api/test_down_time_archived_scope_rejection.py` — all frozen,
none edited.
"""

import uuid
from datetime import date

import pytest

from src.app.core.firestore import NAMESPACE_SETTINGS_COLLECTION, SETTINGS_SUBCOLLECTION
from src.app.globals.enum import DownTimeStatus, DownTimeType, Process, Role, WorkstationType

NS = "ns-kpi-archiving-type-slice-gap"
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"

BOTTLENECK = WorkstationType.BOTTLENECK.value
CRITICAL = WorkstationType.CRITICAL.value
STANDARD = WorkstationType.STANDARD.value

ARCHIVED_BEFORE_TICKET = "2026-01-10T00:00:00+00:00"  # strictly before every ticket's created_at


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS, timezone="UTC", company_name="Archiving Type Slice Gap Plant")


def _owner(seed_user, namespace_id=NS, **overrides):
    overrides.setdefault("namespace_id", namespace_id)
    overrides.setdefault("role", Role.OWNER.value)
    return seed_user(**overrides)


def _seed_settings(fake_db, namespace_id=NS, **overrides):
    doc = {
        "namespace_id": namespace_id,
        "shift_number": 1,
        "shift_1": {"start_time": "06:00", "end_time": "14:00"},
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


# --------------------------------------------------------------------------
# 1. `line`-kind spread row, mixed archived/active stations of DIFFERENT
#    types -- the exact shape the KNOWN GAP paragraph describes.
# --------------------------------------------------------------------------


class TestLineKindSpreadRowMixedArchivalDifferentTypes:
    """A plant-scope ticket spreads into every `line` row (`_locations_for_
    ticket`'s spread rule, §2) -- neither line is the ticket's own declared
    location, so both rows take `_row_weight`'s/`_row_type_weights`'s SPREAD
    branch, the one carrying the gap."""

    def test_type_slices_sum_to_the_row_weight_on_a_mixed_archived_active_line(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """line1 (the row under test): 1 active BOTTLENECK station + 1
        CRITICAL station archived before the ticket. line2: 1 active
        STANDARD station, present only so 2 active lines exist under the
        single UAP and `_pick_location_kind` selects "line" (>1 active
        line) rather than collapsing to "uap".

        Arithmetic for line1's row:
        - raw stations under line1 = 2 (bottleneck + critical).
        - active-at-ticket-date stations = 1 (only the bottleneck one; the
          critical one was archived 2026-01-10, before the ticket's own
          2026-01-15 07:00 `created_at`).
        - `_row_weight` (correct, already filters) = 1 -> downtime =
          1 * 3600s = 3600s.
        - `_row_type_weights` (buggy, static `type_counts_by_line`) reports
          bottleneck=1, critical=1 (both count the archived station too) ->
          bottleneck downtime = 1*3600 = 3600, critical downtime = 1*3600 =
          3600, summing to 7200s -- DOUBLE the row's real 3600s weight.
        - The invariant: bottleneck + critical downtime_seconds must equal
          the row's own downtime_seconds (3600). Currently 7200 != 3600 ->
          this assertion is expected to FAIL.
        """
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line1["id"], type=BOTTLENECK)
        seed_workstation(
            namespace_id=NS,
            production_line_id=line1["id"],
            type=CRITICAL,
            archived_at=ARCHIVED_BEFORE_TICKET,
        )
        seed_workstation(namespace_id=NS, production_line_id=line2["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        rows = _by_location(res)
        row1 = rows[line1["id"]]
        assert row1["kind"] == "line"

        # The row's own weight (correct today): only the active bottleneck
        # station counts.
        assert row1["kpis"]["downtime_seconds"] == 3600

        # The invariant the developer pinned: the type slices must sum back
        # to the row's own weight. Expected to FAIL: the static
        # `type_counts_by_line` total (2 stations) over-counts the archived
        # critical station, giving 7200 instead of 3600.
        bottleneck_dt = row1["kpis"]["bottleneck"]["downtime_seconds"]
        critical_dt = row1["kpis"]["critical"]["downtime_seconds"]
        assert bottleneck_dt + critical_dt == row1["kpis"]["downtime_seconds"]

        # The critical slice specifically should read 0 (its only station
        # was archived before the ticket) -- pins the exact wrong number the
        # static total currently reports (3600) against the correct one (0).
        assert critical_dt == 0

    def test_row_sum_still_reconciles_with_the_header_total(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Same fixture as above. `_row_weight` itself is NOT part of the
        gap (only `_row_type_weights` is), so `by_location` downtime rows
        summing back to the header total is untouched and already correct
        today -- included as a non-regression guard alongside the type-slice
        assertion above, per the developer's invariant statement ("... and
        the sum of the rows equals the header total").

        Arithmetic: namespace has 3 stations total -- 1 active bottleneck
        (line1), 1 archived-before-ticket critical (line1), 1 active
        standard (line2). Active count = 2 -> header downtime =
        2 * 3600 = 7200s. line1's own row weight = 1 (3600s), line2's raw
        stations = [standard] (non-empty, active) -> weight 1 (3600s).
        Row sum = 3600 + 3600 = 7200 = header.
        """
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line1["id"], type=BOTTLENECK)
        seed_workstation(
            namespace_id=NS,
            production_line_id=line1["id"],
            type=CRITICAL,
            archived_at=ARCHIVED_BEFORE_TICKET,
        )
        seed_workstation(namespace_id=NS, production_line_id=line2["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        rows = _by_location(res)

        header_downtime = data["overall"]["downtime_seconds"]
        assert header_downtime == 7200
        row_sum = sum(row["kpis"]["downtime_seconds"] for row in rows.values())
        assert row_sum == header_downtime


# --------------------------------------------------------------------------
# 2. Same shape, `uap`-kind spread row (`type_counts_by_uap` path).
# --------------------------------------------------------------------------


class TestUapKindSpreadRowMixedArchivalDifferentTypes:
    """Identical mechanics to the `line`-kind case, but exercising the
    `type_counts_by_uap` branch of `_row_type_weights` -- the gap is present
    in both, `_row_type_weights` reads whichever static table matches
    `kind`."""

    def test_type_slices_sum_to_the_row_weight_on_a_mixed_archived_active_uap(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """uap1 (the row under test): 1 line with 1 active BOTTLENECK
        station + 1 CRITICAL station archived before the ticket. uap2: 1
        line with 1 active STANDARD station, present only so 2 active UAPs
        exist and `_pick_location_kind` selects "uap".

        Same arithmetic as the `line`-kind case: uap1's row weight = 1
        (3600s, only the active bottleneck counts); static
        `type_counts_by_uap[uap1]` reports bottleneck=1, critical=1 ->
        bottleneck+critical downtime = 7200s != row weight 3600s -- expected
        to FAIL.
        """
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap1 = seed_uap(namespace_id=NS)
        uap2 = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap1["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap2["id"])
        seed_workstation(namespace_id=NS, production_line_id=line1["id"], type=BOTTLENECK)
        seed_workstation(
            namespace_id=NS,
            production_line_id=line1["id"],
            type=CRITICAL,
            archived_at=ARCHIVED_BEFORE_TICKET,
        )
        seed_workstation(namespace_id=NS, production_line_id=line2["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        rows = _by_location(res)
        row1 = rows[uap1["id"]]
        assert row1["kind"] == "uap"

        assert row1["kpis"]["downtime_seconds"] == 3600

        bottleneck_dt = row1["kpis"]["bottleneck"]["downtime_seconds"]
        critical_dt = row1["kpis"]["critical"]["downtime_seconds"]
        assert bottleneck_dt + critical_dt == row1["kpis"]["downtime_seconds"]
        assert critical_dt == 0


# --------------------------------------------------------------------------
# 3. Archived stations all of ONE type -- that slice should drop to 0 while
#    the other keeps its real (correct) value; the static total silently
#    inflates only the archived type's slice.
# --------------------------------------------------------------------------


class TestArchivedStationsAllOneTypeOnlyThatSliceOvercounts:
    def test_bottleneck_slice_drops_to_zero_when_every_bottleneck_station_is_archived(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """line1 (row under test): 2 BOTTLENECK stations, BOTH archived
        before the ticket, + 1 active CRITICAL station. line2: 1 active
        STANDARD station (2nd active line, so `_pick_location_kind` picks
        "line").

        Arithmetic for line1:
        - raw stations = 3 (2 bottleneck + 1 critical).
        - active-at-ticket-date = 1 (the critical station only).
        - `_row_weight` (correct) = 1 -> row downtime = 3600s.
        - static `type_counts_by_line[line1]` = bottleneck:2, critical:1.
          - bottleneck slice (buggy) = 2 * 3600 = 7200s -- should be 0 (its
            only 2 stations are both archived) -> expected to FAIL.
          - critical slice = 1 * 3600 = 3600s -- happens to already be
            correct here (the critical station isn't archived, so the
            static count and the active count coincide) -> this half is
            NOT expected to fail, it demonstrates the "other type keeps its
            real value" half of the scenario.
        """
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(
            namespace_id=NS,
            production_line_id=line1["id"],
            type=BOTTLENECK,
            archived_at=ARCHIVED_BEFORE_TICKET,
        )
        seed_workstation(
            namespace_id=NS,
            production_line_id=line1["id"],
            type=BOTTLENECK,
            archived_at=ARCHIVED_BEFORE_TICKET,
        )
        seed_workstation(namespace_id=NS, production_line_id=line1["id"], type=CRITICAL)
        seed_workstation(namespace_id=NS, production_line_id=line2["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        row1 = _by_location(res)[line1["id"]]
        assert row1["kind"] == "line"
        assert row1["kpis"]["downtime_seconds"] == 3600

        # The type that is ENTIRELY archived must drop to 0 -- currently
        # over-counted at 7200 by the static total. Expected to FAIL.
        assert row1["kpis"]["bottleneck"]["downtime_seconds"] == 0

        # The untouched type keeps its real value, matching the row's own
        # weight exactly -- already true today (not part of the gap).
        assert row1["kpis"]["critical"]["downtime_seconds"] == 3600

        # The reconciliation invariant, restated for this shape.
        bottleneck_dt = row1["kpis"]["bottleneck"]["downtime_seconds"]
        critical_dt = row1["kpis"]["critical"]["downtime_seconds"]
        assert bottleneck_dt + critical_dt == row1["kpis"]["downtime_seconds"]


# --------------------------------------------------------------------------
# 4. Every station in the row archived before the ticket -- weight 0, every
#    type slice 0, ticket still counted once.
# --------------------------------------------------------------------------


class TestEntireRowArchivedBeforeTicket:
    def test_weight_and_every_type_slice_are_zero_but_the_ticket_still_counts_once(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """line1 (row under test): 1 BOTTLENECK + 1 CRITICAL station, BOTH
        archived before the ticket. line2: 1 active STANDARD station (2nd
        active line, so `_pick_location_kind` picks "line").

        Arithmetic for line1:
        - raw stations = 2 (non-empty -> NOT the missing-data floor case).
        - active-at-ticket-date = 0 (both archived) -> `_row_weight`
          (correct) = 0 -> row downtime = 0 * 3600 = 0s, never floored
          (resource-archiving rule 4 -- "something WAS resolved, then all
          of it was archived before the ticket" is NOT the floor's case).
        - static `type_counts_by_line[line1]` = bottleneck:1, critical:1
          (unfiltered) -- buggy slices report 1*3600=3600s EACH, instead of
          0 -- both expected to FAIL.
        - The row's own `count` is NOT weighted by workstations (`_compute_
          base_kpis`: `count = len(count_source)`, the number of tickets
          landing in the row, regardless of weight) -- the ticket still
          shows up once, matching `TestPerimeterBoundary`'s equivalent
          header-level pin in the frozen `test_kpi_resource_archiving.py`.
        """
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(
            namespace_id=NS,
            production_line_id=line1["id"],
            type=BOTTLENECK,
            archived_at=ARCHIVED_BEFORE_TICKET,
        )
        seed_workstation(
            namespace_id=NS,
            production_line_id=line1["id"],
            type=CRITICAL,
            archived_at=ARCHIVED_BEFORE_TICKET,
        )
        seed_workstation(namespace_id=NS, production_line_id=line2["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        row1 = _by_location(res)[line1["id"]]
        assert row1["kind"] == "line"

        assert row1["kpis"]["downtime_seconds"] == 0
        assert row1["kpis"]["count"] == 1
        # Both slices must read 0 -- expected to FAIL (currently 3600 each).
        assert row1["kpis"]["bottleneck"]["downtime_seconds"] == 0
        assert row1["kpis"]["critical"]["downtime_seconds"] == 0


# --------------------------------------------------------------------------
# 5. Non-regression: a spread row with NO archived station at all -- numbers
#    identical to today (the static total and the active-filtered count
#    coincide when nothing is archived, so this passes both before and
#    after a fix).
# --------------------------------------------------------------------------


class TestNoArchivedStationNonRegression:
    def test_type_slices_reconcile_exactly_as_they_do_without_any_archiving(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """line1 (row under test): 1 active BOTTLENECK + 1 active CRITICAL
        station, neither archived. line2: 1 active STANDARD station (2nd
        active line, so `_pick_location_kind` picks "line").

        Arithmetic: raw stations = active stations = 2 for line1 -> row
        weight 2 -> downtime = 2*3600 = 7200s. Static type counts equal the
        active-filtered ones here (nothing archived) -> bottleneck =
        1*3600 = 3600s, critical = 1*3600 = 3600s, summing to 7200s = the
        row's own weight. This test is NOT expected to fail -- it pins that
        the invariant already holds in the ordinary, no-archiving case,
        exactly as `tests/api/test_kpi_type_slices.py::
        TestSliceOwnShareWeighting` already established for a different
        (own-branch) shape.
        """
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line1["id"], type=BOTTLENECK)
        seed_workstation(namespace_id=NS, production_line_id=line1["id"], type=CRITICAL)
        seed_workstation(namespace_id=NS, production_line_id=line2["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        row1 = _by_location(res)[line1["id"]]
        assert row1["kind"] == "line"

        assert row1["kpis"]["downtime_seconds"] == 7200
        bottleneck_dt = row1["kpis"]["bottleneck"]["downtime_seconds"]
        critical_dt = row1["kpis"]["critical"]["downtime_seconds"]
        assert bottleneck_dt == 3600
        assert critical_dt == 3600
        assert bottleneck_dt + critical_dt == row1["kpis"]["downtime_seconds"]


# --------------------------------------------------------------------------
# 6. The missing-data floor is untouched by any of the above -- a line with
#    no workstation registered at all still yields the floored weight.
#
# Where the floored weight's type ownership is ambiguous (the contract never
# specifies which slice a floored-at-1 phantom workstation belongs to), this
# test does NOT invent an answer -- it pins what the code does TODAY: an
# empty line's own perimeter (`type_counts_by_line`) holds no workstation of
# any type, so BOTH slices come back `None` (not populated, not zeroed) via
# `_compute_type_slice`'s `perimeter_type_counts.get(type_key, 0) <= 0 ->
# None` rule, exactly like the no-workstation-of-that-type case already
# pinned by `test_kpi_type_slices.py::TestSliceAbsentWhenPerimeterHasNoWork
# stationOfType`. This is the "own" branch for `_row_type_weights` (the
# ticket is declared directly on the empty line), so it is unaffected by the
# spread-branch gap under test elsewhere in this file, and is NOT expected
# to fail.
# --------------------------------------------------------------------------


class TestMissingDataFloorUnaffectedByTheGap:
    def test_line_with_no_workstation_still_floors_to_one_with_no_type_slice_populated(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """line1 (row under test): zero workstations registered under it at
        all. line2: 1 active STANDARD station (2nd active line, so
        `_pick_location_kind` picks "line" rather than "station").

        The ticket is declared directly ON line1 (`down_time_scope=
        "production line"`, `production_line_id=line1["id"]`) -- an "own"
        row for `_row_weight`/`_row_type_weights`, not a spread one.
        `_ticket_stations_raw` resolves to the empty
        `stations_by_line[line1]` -> `_ticket_weight` floors to 1 (the
        floor's ORIGINAL case: nothing was resolvable at all, not "resolved
        then archived") -> row downtime = 1*3600 = 3600s, unaffected by
        archiving.

        Existing (pinned) behavior for the floor's type ownership: line1's
        own perimeter (`type_counts_by_line[line1]`) is all-zero (no
        workstation of any type under it) -> `_compute_type_slice` returns
        `None` for both bottleneck and critical -- the floored weight is
        attributed to NEITHER an exposed slice NOR made to look like a
        populated-and-zeroed one; it is simply absorbed by the unexposed
        `standard` share as `_ticket_type_weights` computes it, with no
        `by_location`-visible slice claiming it.
        """
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line2["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line1["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        row1 = _by_location(res)[line1["id"]]
        assert row1["kind"] == "line"

        assert row1["kpis"]["downtime_seconds"] == 3600
        assert row1["kpis"]["bottleneck"] is None
        assert row1["kpis"]["critical"] is None
