"""API-level coverage for `.claude/specs/kpi-workstation-type-slices.md` — the
two new optional `bottleneck` / `critical` slices carried by every `Kpis`
object (§3.1), alongside the 4 unchanged root headline figures.

TEST-FIRST MODE: written before `Kpis` gains `bottleneck`/`critical`
(`src/app/routers/kpi/modelsOut.py`) and before `services.py` computes them.
Every assertion here is derived from the contract's §5 scenario list only —
no implementation exists yet, so every test below is expected to fail either
on a `KeyError`/`AssertionError` reading a still-absent `bottleneck`/
`critical` key, or on a wrong (still-root-only) figure. None of this file's
own tests are expected to fail on a fixture/import error.

Two different JSON-serialization regimes matter here (see
`src/app/routers/kpi/__init__.py`):
- `GET /kpi/dashboard` has **no** `response_model_exclude_none` — a `None`
  slice is serialized as an explicit JSON `null`, so "not populated" is
  asserted as `row["kpis"]["bottleneck"] is None`.
- `GET /kpi/drilldown` **does** set `response_model_exclude_none=True` — a
  `None` slice is dropped from the payload entirely, so "not populated" is
  asserted as `"bottleneck" not in data["kpis"]` (key absence), not `is None`.

All tickets use fixed 2026-01-15 timestamps, in the past relative to
wall-clock "now" at test-run time (today's real date is 2026-09-03), so the
`min(natural_end, now)` clamp never kicks in for CLOSED tickets and no
`freeze_kpi_clock`-style patching is needed anywhere in this file — there is
no carry-over ticket in any scenario below.

REVISION 3 (2026-09-03, api-agent-raised anomaly, developer-adjudicated):
scenario 7's PERIMETER rule (revision 2, §3.1) is per-OBJECT, not per-plant —
a `uap`/`line` row's own perimeter is that UAP/line, never the whole
namespace. Six "populated" tests (scenarios 9, 11, 12) had accidentally
fixed only ONE of the two types on their perimeter, so under the revision-2
rule their untouched type would legitimately be `None` there too — a direct
contradiction with `TestSliceAbsentWhenPerimeterHasNoWorkstationOfType`'s own
UAP-B case, on the exact same perimeter shape. Fixed by SEEDING each
"populated" fixture with BOTH a bottleneck AND a critical workstation on the
object's own perimeter, preserving each test's original intent (population,
not absence) rather than flipping the assertions. The one test whose real
subject IS an empty perimeter of both types
(`TestLegacyWorkstationWithoutTypeCountsAsStandard`) is rewritten the other
way: both slices now assert `None`, while still pinning that the legacy
workstation feeds the root as `standard`.

Scenarios covered (§5, this file's classes in the same order):
 1. `overall` carries `bottleneck`/`critical`; root figures unchanged.
 2. Reconciliation: bottleneck + critical (+ standard) == root, both with
    and without `standard` workstations present.
 3. A plant-scope ticket over a mixed hierarchy weighs each slice by that
    slice's own workstation count (not the root's).
 4. A ticket declared ON a bottleneck workstation contributes to
    `bottleneck` only, never `critical`.
 5. `count` per slice: a ticket touching both a bottleneck and a critical
    workstation counts 1 in EACH slice — slices don't sum to root `count`.
 6. `mttr_seconds` per slice is that slice's own mean, not a share of root.
 7. REVISION 2 (2026-09-03, developer decision — reverses this file's first
    draft): no workstation of the type in the object's own PERIMETER
    (namespace for `overall`/`by_shift`, the UAP for a `uap` row, the line
    for a `line` row, the path's deepest location for a drill-down, §3.1)
    -> that slice is `None`, never a zeroed object. Conversely, a perimeter
    that DOES hold workstations of the type but they had no downtime in the
    period -> slice PRESENT with zeros — `0` genuinely means "no downtime"
    there. Both halves are asserted, plus the plant-wide-check trap: a `uap`
    row for a UAP with no bottleneck workstation is `None` even when a
    SIBLING UAP in the same namespace does have one.
 8. `by_location` kind `station` -> `bottleneck`/`critical` are `None`.
 9. `by_location` kind `uap` and kind `line` -> populated.
10. `by_shift` rows -> populated.
11. Drill-down: `uap`/`line`/`shift` path -> populated; `station` path ->
    absent (see the exclude_none note above).
12. `by_location` row slices carry `mtbf_seconds = None`, exactly like their
    own row's root (`by_shift` is deliberately excluded — its root already
    carries a REAL, non-`None` planned-time denominator today; unchanged,
    pre-existing behavior this contract does not touch, see §8 of the spec).
13. A workstation document with no stored `type` at all (legacy doc) counts
    as `standard`: feeds the root, neither slice.
14. Non-regression: the root fields' values are unaffected by this change
    (this one already passes today, noted in its own docstring).

This file does not re-test `401`/`403`/tenant-isolation on `/kpi/dashboard`
or `/kpi/drilldown` — those are not new endpoints and are already covered by
`tests/api/test_kpi_dashboard.py`.
"""

import uuid
from datetime import date

import pytest

from src.app.core.firestore import (
    NAMESPACE_SETTINGS_COLLECTION,
    SETTINGS_SUBCOLLECTION,
    WORKSTATION_COLLECTION,
)
from src.app.globals.enum import DownTimeStatus, DownTimeType, Process, Role, WorkstationType

NS = "ns-kpi-type-slices"
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"

BOTTLENECK = WorkstationType.BOTTLENECK.value
CRITICAL = WorkstationType.CRITICAL.value
STANDARD = WorkstationType.STANDARD.value


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS, timezone="UTC", company_name="Type Slices Plant")


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


def _seed_legacy_workstation_without_type(fake_db, namespace_id=NS, production_line_id=None):
    """A workstation document written before `type` existed: the field is
    entirely absent (not just `None`), mirroring a pre-migration Firestore
    doc. `seed_workstation`/`WorkstationDocFactory` always set a `type`, so
    this writes the raw doc directly."""
    station = {
        "id": str(uuid.uuid4()),
        "namespace_id": namespace_id,
        "name": "legacy-station",
        "description": "pre-type-field workstation",
        "production_line_id": production_line_id,
    }
    fake_db.collection(WORKSTATION_COLLECTION).document(station["id"]).set(station)
    return station


# --------------------------------------------------------------------------
# 1. `overall` carries the two slices; root figures unchanged.
# --------------------------------------------------------------------------


class TestOverallCarriesSlices:
    """Scenario 1."""

    def test_overall_bottleneck_and_critical_are_present_root_unchanged(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK)
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=CRITICAL)
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        overall = res.json()["data"]["overall"]

        # Root figures: unchanged shape/values (weight = 3 workstations).
        assert overall["downtime_seconds"] == 3 * 3600
        assert overall["count"] == 1
        assert overall["mttr_seconds"] == 3600

        assert "bottleneck" in overall
        assert "critical" in overall
        assert overall["bottleneck"] is not None
        assert overall["critical"] is not None


# --------------------------------------------------------------------------
# 2. Reconciliation.
# --------------------------------------------------------------------------


class TestReconciliation:
    """Scenario 2."""

    def test_bottleneck_plus_critical_equals_root_when_no_standard_workstations(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        for _ in range(3):
            seed_workstation(namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK)
        for _ in range(2):
            seed_workstation(namespace_id=NS, production_line_id=line["id"], type=CRITICAL)
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        overall = res.json()["data"]["overall"]

        assert overall["downtime_seconds"] == 5 * 3600
        assert overall["bottleneck"]["downtime_seconds"] == 3 * 3600
        assert overall["critical"]["downtime_seconds"] == 2 * 3600
        assert (
            overall["bottleneck"]["downtime_seconds"] + overall["critical"]["downtime_seconds"]
            == overall["downtime_seconds"]
        )

    def test_bottleneck_plus_critical_is_less_than_root_by_exactly_the_standard_share(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        for _ in range(2):
            seed_workstation(namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK)
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=CRITICAL)
        for _ in range(2):
            seed_workstation(namespace_id=NS, production_line_id=line["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        overall = res.json()["data"]["overall"]

        # root weight 5, bottleneck weight 2, critical weight 1, standard
        # (unexposed) weight 2 -> root - (bottleneck + critical) == 2 * 3600.
        assert overall["downtime_seconds"] == 5 * 3600
        assert overall["bottleneck"]["downtime_seconds"] == 2 * 3600
        assert overall["critical"]["downtime_seconds"] == 1 * 3600
        standard_share = overall["downtime_seconds"] - (
            overall["bottleneck"]["downtime_seconds"] + overall["critical"]["downtime_seconds"]
        )
        assert standard_share == 2 * 3600


# --------------------------------------------------------------------------
# 3. Own-share weighting over a mixed hierarchy.
# --------------------------------------------------------------------------


class TestSliceOwnShareWeighting:
    """Scenario 3."""

    def test_plant_ticket_over_mixed_hierarchy_weighs_each_slice_by_its_own_station_count(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap1 = seed_uap(namespace_id=NS)
        uap2 = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap1["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap2["id"])
        for _ in range(2):
            seed_workstation(namespace_id=NS, production_line_id=line1["id"], type=BOTTLENECK)
        seed_workstation(namespace_id=NS, production_line_id=line2["id"], type=CRITICAL)
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
        overall = res.json()["data"]["overall"]

        # root weight = 4 (all stations); bottleneck weight = 2 (its own
        # count), critical weight = 1 (its own count) -- neither equals the
        # root's weight of 4.
        assert overall["downtime_seconds"] == 4 * 3600
        assert overall["bottleneck"]["downtime_seconds"] == 2 * 3600
        assert overall["critical"]["downtime_seconds"] == 1 * 3600


# --------------------------------------------------------------------------
# 4. A station-declared ticket contributes to its own slice only.
# --------------------------------------------------------------------------


class TestStationDeclaredContributesToOwnSliceOnly:
    """Scenario 4."""

    def test_ticket_declared_on_bottleneck_station_contributes_to_bottleneck_only(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        bottleneck_station = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK
        )
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=CRITICAL)
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=bottleneck_station["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        overall = res.json()["data"]["overall"]

        assert overall["bottleneck"]["count"] == 1
        assert overall["bottleneck"]["downtime_seconds"] == 3600
        assert overall["critical"]["count"] == 0
        assert overall["critical"]["downtime_seconds"] == 0


# --------------------------------------------------------------------------
# 5. `count` per slice does not sum to the root's `count`.
# --------------------------------------------------------------------------


class TestSliceCountDoesNotSumToRootCount:
    """Scenario 5."""

    def test_ticket_touching_bottleneck_and_critical_counts_once_in_each_slice(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK)
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=CRITICAL)
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
        overall = res.json()["data"]["overall"]

        assert overall["count"] == 1
        assert overall["bottleneck"]["count"] == 1
        assert overall["critical"]["count"] == 1
        # 1 + 1 != 1 -- slices do not sum to the root count, exactly like the
        # location breakdown model (kpi-scope-spread §4).
        assert overall["bottleneck"]["count"] + overall["critical"]["count"] != overall["count"]


# --------------------------------------------------------------------------
# 6. MTTR per slice is its own mean, never a share of the root.
# --------------------------------------------------------------------------


class TestSliceMttrIsOwnMean:
    """Scenario 6."""

    def test_mttr_per_slice_is_own_mean_not_root_share(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station_a = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK
        )
        station_b = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK
        )
        station_c = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=CRITICAL
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station_a["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station_b["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(9),
            resolved_at=_utc(12),
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station_c["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(13),
            resolved_at=_utc(23),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        overall = res.json()["data"]["overall"]

        # root mean(1h, 3h, 10h) = 16800.
        assert overall["mttr_seconds"] == 16800
        # bottleneck mean(1h, 3h) = 7200 -- its own mean, not a share of 16800.
        assert overall["bottleneck"]["mttr_seconds"] == 7200
        # critical: single 10h ticket -> its own mean is exactly 36000.
        assert overall["critical"]["mttr_seconds"] == 36000


# --------------------------------------------------------------------------
# 7. No workstation of the type in the PERIMETER -> None (revision 2,
#    2026-09-03: reverses the first draft's "present, zeroed" behavior).
#    A perimeter that DOES hold workstations of the type, just with no
#    downtime in the period, is still present-with-zeros -- the other half
#    of the same distinction, asserted alongside it.
# --------------------------------------------------------------------------


class TestSliceAbsentWhenPerimeterHasNoWorkstationOfType:
    """Scenario 7 (revision 2) -- the core distinction of this contract, now
    inverted from this file's first draft: a slice is `None` when its OWN
    PERIMETER (namespace for `overall`/`by_shift`, the UAP for a `uap` row,
    the line for a `line` row, the path's deepest location for a
    drill-down -- §3.1) holds no workstation of that type at all, full stop.
    It is present-with-zeros only when the perimeter DOES hold workstations
    of the type and none of them had downtime in the period -- there, and
    only there, does `0` mean "no downtime" rather than "not applicable"."""

    def test_overall_bottleneck_is_none_when_no_bottleneck_workstation_in_namespace(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        critical_station = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=CRITICAL
        )
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=critical_station["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        overall = res.json()["data"]["overall"]

        # The namespace (overall's own perimeter) holds NO bottleneck
        # workstation at all -> None, not a zeroed object: a displayed `0h`
        # would misread as "no downtime on the bottlenecks" when the truth
        # is "there are no bottlenecks".
        assert overall["bottleneck"] is None
        assert overall["critical"] is not None

    def test_overall_bottleneck_present_zeroed_when_bottleneck_workstations_exist_but_had_no_downtime(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK)
        critical_station = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=CRITICAL
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=critical_station["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        overall = res.json()["data"]["overall"]

        # The namespace DOES hold a bottleneck workstation -- it just had no
        # downtime this period -- so the slice is PRESENT with zeros; `0`
        # here genuinely means "no downtime", the reading the front-end must
        # still render.
        assert overall["bottleneck"] is not None
        assert overall["bottleneck"]["downtime_seconds"] == 0
        assert overall["bottleneck"]["count"] == 0
        assert overall["bottleneck"]["mttr_seconds"] == 0
        # `_compute_kpis` returns `planned_seconds` itself when count == 0
        # (reused verbatim for the slice, §3.2) -- single 06:00-14:00 shift,
        # one full unproratable day -> 28800.
        assert overall["bottleneck"]["mtbf_seconds"] == 28800

    def test_uap_row_bottleneck_is_none_for_a_uap_with_no_bottleneck_even_though_the_plant_has_one(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """The perimeter for a `uap` row is that UAP, not the plant --
        pinning the case most likely to be implemented as a mistaken
        plant-wide check: UAP B has no bottleneck workstation of its own,
        even though UAP A (a sibling in the same namespace) does."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap_a = seed_uap(namespace_id=NS)
        uap_b = seed_uap(namespace_id=NS)
        line_a = seed_production_line(namespace_id=NS, uap_id=uap_a["id"])
        line_b = seed_production_line(namespace_id=NS, uap_id=uap_b["id"])
        seed_workstation(namespace_id=NS, production_line_id=line_a["id"], type=BOTTLENECK)
        critical_station_b = seed_workstation(
            namespace_id=NS, production_line_id=line_b["id"], type=CRITICAL
        )
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=critical_station_b["id"],
            production_line_id=line_b["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(9),
            resolved_at=_utc(10),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        rows = {row["id"]: row for row in res.json()["data"]["by_location"]}

        assert rows[uap_a["id"]]["kpis"]["bottleneck"] is not None
        # UAP B's own perimeter has no bottleneck workstation -- None, even
        # though the plant as a whole (UAP A) does.
        assert rows[uap_b["id"]]["kpis"]["bottleneck"] is None
        assert rows[uap_b["id"]]["kpis"]["critical"] is not None


# --------------------------------------------------------------------------
# 8/9. `by_location` applicability by kind.
# --------------------------------------------------------------------------


class TestByLocationSliceApplicability:
    """Scenarios 8 and 9."""

    def test_station_kind_rows_have_none_slices(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Single UAP, single line, multiple stations -> `_pick_location_kind`
        selects `station` -- a workstation already has exactly one type, so
        splitting its own row by type is meaningless (§3.3)."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK)
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=CRITICAL)
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        rows = res.json()["data"]["by_location"]
        assert rows, "expected station-kind by_location rows"
        assert all(row["kind"] == "station" for row in rows)
        for row in rows:
            assert row["kpis"]["bottleneck"] is None
            assert row["kpis"]["critical"] is None

    def test_uap_kind_rows_have_populated_slices(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """3 UAPs -> `_pick_location_kind` selects `uap`. Revision 3: a
        slice is populated for a `uap` row only when THAT UAP's own
        perimeter holds a workstation of the type (§3.1) -- so UAP A is
        seeded with BOTH a bottleneck AND a critical workstation, proving
        population is real, not an artifact of an empty-perimeter test."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap_a = seed_uap(namespace_id=NS)
        uap_b = seed_uap(namespace_id=NS)
        uap_c = seed_uap(namespace_id=NS)
        line_a = seed_production_line(namespace_id=NS, uap_id=uap_a["id"])
        line_b = seed_production_line(namespace_id=NS, uap_id=uap_b["id"])
        line_c = seed_production_line(namespace_id=NS, uap_id=uap_c["id"])
        seed_workstation(namespace_id=NS, production_line_id=line_a["id"], type=BOTTLENECK)
        seed_workstation(namespace_id=NS, production_line_id=line_a["id"], type=CRITICAL)
        seed_workstation(namespace_id=NS, production_line_id=line_b["id"], type=STANDARD)
        seed_workstation(namespace_id=NS, production_line_id=line_c["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        rows = {row["id"]: row for row in res.json()["data"]["by_location"]}
        assert set(rows) == {uap_a["id"], uap_b["id"], uap_c["id"]}
        assert all(row["kind"] == "uap" for row in rows.values())

        # UAP A's own perimeter holds both types -> both slices populated.
        assert rows[uap_a["id"]]["kpis"]["bottleneck"] is not None
        assert rows[uap_a["id"]]["kpis"]["bottleneck"]["downtime_seconds"] == 3600
        assert rows[uap_a["id"]]["kpis"]["critical"] is not None
        assert rows[uap_a["id"]]["kpis"]["critical"]["downtime_seconds"] == 3600

    def test_line_kind_rows_have_populated_slices(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Single UAP, multiple lines -> `_pick_location_kind` selects
        `line`. Revision 3: line1 is seeded with BOTH a bottleneck AND a
        critical workstation (its own perimeter), so population is proven
        for real rather than incidentally on an empty-perimeter fixture."""
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
        rows = {row["id"]: row for row in res.json()["data"]["by_location"]}
        assert set(rows) == {line1["id"], line2["id"]}
        assert all(row["kind"] == "line" for row in rows.values())

        assert rows[line1["id"]]["kpis"]["bottleneck"] is not None
        assert rows[line1["id"]]["kpis"]["bottleneck"]["downtime_seconds"] == 3600
        assert rows[line1["id"]]["kpis"]["critical"] is not None
        assert rows[line1["id"]]["kpis"]["critical"]["downtime_seconds"] == 3600


# --------------------------------------------------------------------------
# 10. `by_shift` rows.
# --------------------------------------------------------------------------


class TestByShiftSliceApplicability:
    """Scenario 10."""

    def test_by_shift_rows_have_populated_slices(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(
            fake_db,
            shift_number=2,
            shift_1={"start_time": "06:00", "end_time": "14:00"},
            shift_2={"start_time": "14:00", "end_time": "22:00"},
        )
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK)
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=CRITICAL)
        _seed_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            shift=1,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_shift = {row["id"]: row for row in res.json()["data"]["by_shift"]}
        assert "1" in by_shift
        assert by_shift["1"]["kpis"]["bottleneck"] is not None
        assert by_shift["1"]["kpis"]["critical"] is not None
        assert by_shift["1"]["kpis"]["bottleneck"]["count"] == 1
        assert by_shift["1"]["kpis"]["critical"]["count"] == 1


# --------------------------------------------------------------------------
# 11. Drill-down applicability by path kind.
# --------------------------------------------------------------------------


class TestDrilldownSliceApplicability:
    """Scenario 11. `/kpi/drilldown` sets `response_model_exclude_none=True`
    -- a `None` slice is DROPPED from the payload entirely, so "not
    populated" is a missing key, not a `null` value (unlike `/kpi/dashboard`,
    see the module docstring)."""

    def _hierarchy(self, fake_db, seed_uap, seed_production_line, seed_workstation):
        """Revision 3: the UAP/line/namespace perimeter each of the
        populated-path tests below drills into must hold BOTH a bottleneck
        AND a critical workstation of its own (§3.1) -- a single-type
        perimeter would make one of the two slices legitimately `None`,
        which is not what those tests are proving. `station` stays the
        bottleneck one; `station:<id>` targets exactly one workstation, so
        which type it is doesn't matter for the always-`None`-at-station-
        kind rule (§3.3) the leaf test pins."""
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        bottleneck_station = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK
        )
        critical_station = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=CRITICAL
        )
        _seed_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            shift=1,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )
        return {
            "uap": uap,
            "line": line,
            "station": bottleneck_station,
            "critical_station": critical_station,
        }

    def test_uap_path_kpis_are_populated(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        ctx = self._hierarchy(fake_db, seed_uap, seed_production_line, seed_workstation)

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"uap:{ctx['uap']['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        kpis = res.json()["data"]["kpis"]
        assert "bottleneck" in kpis
        assert "critical" in kpis

    def test_line_path_kpis_are_populated(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        ctx = self._hierarchy(fake_db, seed_uap, seed_production_line, seed_workstation)

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"line:{ctx['line']['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        kpis = res.json()["data"]["kpis"]
        assert "bottleneck" in kpis
        assert "critical" in kpis

    def test_shift_path_kpis_are_populated(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        self._hierarchy(fake_db, seed_uap, seed_production_line, seed_workstation)

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": "shift:1"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        kpis = res.json()["data"]["kpis"]
        assert "bottleneck" in kpis
        assert "critical" in kpis

    def test_station_path_kpis_have_no_slice_keys(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        ctx = self._hierarchy(fake_db, seed_uap, seed_production_line, seed_workstation)

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"station:{ctx['station']['id']}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        kpis = res.json()["data"]["kpis"]
        assert "bottleneck" not in kpis
        assert "critical" not in kpis


# --------------------------------------------------------------------------
# 12. Breakdown-row slices carry `mtbf_seconds = None`, same as their root.
# --------------------------------------------------------------------------


class TestBreakdownRowSliceMtbfIsAlwaysNone:
    """Scenario 12. Confined to `by_location` (and, by the same rule,
    `by_type`, out of scope for slices per §3.3) -- these are the rows whose
    OWN root `mtbf_seconds` is already `None` (they pass `planned = 0.0`,
    `kpi-dashboard` fix #5). `by_shift` rows are deliberately excluded here:
    unlike location/type rows, `_group_by_shift` already computes a REAL
    (non-`None`) planned-time denominator for its own root today (existing,
    frozen dashboard behavior, unrelated to this contract) -- so scenario
    12's premise ("exactly as their root does") does not apply to it, and
    asserting `None` there would pin a wrong expectation rather than this
    contract's own."""

    def test_by_location_slice_mtbf_is_none(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Revision 3: UAP A's own perimeter is seeded with BOTH a
        bottleneck AND a critical workstation, so both slices are populated
        on that row (not `None` for the wrong, empty-perimeter reason) --
        this test's actual subject is that a populated slice still carries
        `mtbf_seconds = None` on a `by_location` row."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap_a = seed_uap(namespace_id=NS)
        uap_b = seed_uap(namespace_id=NS)
        line_a = seed_production_line(namespace_id=NS, uap_id=uap_a["id"])
        line_b = seed_production_line(namespace_id=NS, uap_id=uap_b["id"])
        seed_workstation(namespace_id=NS, production_line_id=line_a["id"], type=BOTTLENECK)
        seed_workstation(namespace_id=NS, production_line_id=line_a["id"], type=CRITICAL)
        seed_workstation(namespace_id=NS, production_line_id=line_b["id"], type=STANDARD)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        rows = {row["id"]: row for row in res.json()["data"]["by_location"]}
        row_a = rows[uap_a["id"]]

        # Root of the row: unchanged existing behavior (by_location rows
        # always carry `mtbf_seconds = None`, `kpi-dashboard` fix #5).
        assert row_a["kpis"]["mtbf_seconds"] is None
        assert row_a["kpis"]["bottleneck"]["mtbf_seconds"] is None
        assert row_a["kpis"]["critical"]["mtbf_seconds"] is None


# --------------------------------------------------------------------------
# 13. A legacy workstation with no stored `type` counts as `standard`.
# --------------------------------------------------------------------------


class TestLegacyWorkstationWithoutTypeCountsAsStandard:
    """Scenario 13. Revision 3: this namespace's only workstation is the
    untyped legacy one, so its perimeter holds NO bottleneck and NO critical
    workstation at all -- under the revised §5.7/§3.1 rule both slices must
    now be `None`, not zeroed. What this test actually pins is unchanged:
    the legacy workstation still counts as `standard` and feeds the ROOT
    (downtime_seconds/count are non-zero) while contributing to NEITHER
    slice -- if the implementation mis-typed it as bottleneck/critical
    instead, one of the two would come back populated (and non-`None`)
    rather than absent, which is exactly what these assertions would catch."""

    def test_workstation_without_type_field_feeds_root_but_neither_slice_is_populated(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        legacy_station = _seed_legacy_workstation_without_type(
            fake_db, production_line_id=line["id"]
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=legacy_station["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        overall = res.json()["data"]["overall"]

        # Feeds the root: the legacy workstation still counts (as standard).
        assert overall["downtime_seconds"] == 3600
        assert overall["count"] == 1
        # Feeds NEITHER slice: the namespace has no bottleneck/critical
        # workstation at all -> both are `None`, not zeroed.
        assert overall["bottleneck"] is None
        assert overall["critical"] is None


# --------------------------------------------------------------------------
# 14. Non-regression: root fields are unaffected by this change.
# --------------------------------------------------------------------------


class TestNonRegressionRootFieldsUnaffected:
    """Scenario 14. This test already passes today, before `bottleneck`/
    `critical` exist: it only pins the 4 root figures' values, which this
    change (by design, §3.1 -- "the 4 fields stay at the ROOT") must not
    move. Kept here (rather than relying solely on the frozen suites) so the
    slices work unit has an explicit regression guard colocated with the
    rest of this contract's coverage."""

    def test_root_kpi_fields_unchanged_by_the_slice_addition(
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
        overall = res.json()["data"]["overall"]

        assert overall["downtime_seconds"] == 3 * 3600
        assert overall["count"] == 1
        assert overall["mttr_seconds"] == 3600
        assert overall["mtbf_seconds"] == 28800


# --------------------------------------------------------------------------
# REVISION 3 (2026-09-04, §9 of the contract, after cross-cutting review).
#
# §9.1 BLOCKING: the root's downtime weight (`_ticket_weight`/`_row_weight`)
# falls back to `_weight_from_ids` when a scope's own id field is missing;
# each slice's weight (`_type_weight_fn`, via `_locations_for_ticket`) has
# NO such fallback. The two functions disagree on exactly the ticket shapes
# that carry a scope but a missing/absent/unreachable id -- shapes this
# file's first 21 tests never exercised (they only ever used `plant` with no
# ids, or a ticket declared directly on a real workstation, the two shapes
# where the functions happen to agree). Scenarios 26-30 (§9.7) pin the
# invariant the developer chose as the fix: **the three type slices
# (bottleneck + critical + the unexposed standard) always sum to the root's
# own downtime_seconds, and no single exposed slice exceeds it** -- for
# every ticket shape, legacy documents included.
#
# Every fixture below is built with `standard` share KNOWN BY CONSTRUCTION:
# the hierarchy holds ONLY bottleneck/critical workstations (zero standard
# ones), so the invariant reduces to a plain, numerically checkable
# `root == bottleneck + critical` -- never a `<=` that a shape like #27
# (which UNDER-counts) would pass on the broken code by accident. `count`/
# `mttr_seconds` are deliberately NOT asserted for reconciliation here: a
# ticket touching two types counts 1 in EACH slice by design (scenario 5),
# so only `downtime_seconds` reconciles.
# --------------------------------------------------------------------------


class TestRootAndSliceWeightReconcileAcrossTicketShapes:
    """§9.1/§9.2, scenarios 26-30. Every test below is expected to FAIL
    against the current implementation: `_type_weight_fn` has no fallback
    chain, so it disagrees with `_ticket_weight`/`_row_weight` on any shape
    where a scope's own id is missing, absent from the hierarchy, or floored
    on an empty line/UAP."""

    def test_uap_scope_with_no_uap_id_but_a_production_line_id_reconciles(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Scenario 26. The measured defect's own shape: root falls back to
        `_weight_from_ids` (production_line_id's own 2 stations), while the
        slices spread from the ticket's RESOLVED uap (via `down_time_scope`)
        and reach the WHOLE UAP's 5 stations across both its lines --
        currently `bottleneck (3 stations) + critical (2 stations) = 5 !=
        root (2)`, and `bottleneck` alone (3 stations, 10800s) already
        exceeds the root (7200s) on its own."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        for _ in range(2):
            seed_workstation(namespace_id=NS, production_line_id=line1["id"], type=CRITICAL)
        for _ in range(3):
            seed_workstation(namespace_id=NS, production_line_id=line2["id"], type=BOTTLENECK)
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=None,
            production_line_id=line1["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        overall = res.json()["data"]["overall"]

        # Root: `_weight_from_ids` falls back to `production_line_id`'s own
        # 2 stations (its own id, `uap_id`, is missing) -> weight 2.
        assert overall["downtime_seconds"] == 2 * 3600
        # The invariant the fix must restore: no known standard share here
        # (only bottleneck/critical exist), so bottleneck + critical == root.
        assert overall["downtime_seconds"] == (
            overall["bottleneck"]["downtime_seconds"] + overall["critical"]["downtime_seconds"]
        )
        # And no single slice may exceed the root either.
        assert overall["bottleneck"]["downtime_seconds"] <= overall["downtime_seconds"]
        assert overall["critical"]["downtime_seconds"] <= overall["downtime_seconds"]

    def test_plant_scope_carrying_a_legacy_workstation_id_reconciles(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Scenario 27. `_ticket_weight`'s `plant` branch ignores any stored
        id and weighs the WHOLE namespace; `_locations_for_ticket` treats a
        `plant`-scope ticket's own id as authoritative (Addendum §8) and
        restricts attribution to that ONE workstation -- currently
        `bottleneck (1) + critical (0) = 1 != root (5)`, the exact
        under-count the developer measured (a plain `<=` would pass here by
        accident; the `==` below does not)."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        bottleneck_stations = [
            seed_workstation(namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK)
            for _ in range(2)
        ]
        for _ in range(3):
            seed_workstation(namespace_id=NS, production_line_id=line["id"], type=CRITICAL)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            workstation_id=bottleneck_stations[0]["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        overall = res.json()["data"]["overall"]

        # Root: `plant` branch -> the whole namespace's 5 stations.
        assert overall["downtime_seconds"] == 5 * 3600
        assert overall["downtime_seconds"] == (
            overall["bottleneck"]["downtime_seconds"] + overall["critical"]["downtime_seconds"]
        )

    def test_work_station_scope_with_no_workstation_id_but_a_production_line_id_reconciles(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Scenario 28. Root falls back to `_weight_from_ids` (the line's 4
        stations); `_locations_for_ticket` treats a `work station`-scope
        ticket with no location step reached (`scope_rank <= kind_rank` at
        `station` level) as reaching NOTHING -- currently
        `bottleneck (0) + critical (0) = 0 != root (4)`, the weight vanishes
        entirely rather than landing anywhere."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        for _ in range(2):
            seed_workstation(namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK)
        for _ in range(2):
            seed_workstation(namespace_id=NS, production_line_id=line["id"], type=CRITICAL)
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=None,
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        overall = res.json()["data"]["overall"]

        assert overall["downtime_seconds"] == 4 * 3600
        assert overall["downtime_seconds"] == (
            overall["bottleneck"]["downtime_seconds"] + overall["critical"]["downtime_seconds"]
        )

    def test_ticket_referencing_a_workstation_absent_from_the_hierarchy_reconciles(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Scenario 29. `_ticket_weight` floors a `work station`-scope
        ticket with a stored `workstation_id` at 1 regardless of whether
        that id resolves to a real document; `_locations_for_ticket` returns
        `{that ghost id}`, which no real type-station set will ever contain
        -- the floor never lands in `bottleneck` or `critical`, currently
        `0 + 0 = 0 != root (1)`."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        # Real bottleneck/critical workstations exist (so both slices are a
        # populated, non-`None` perimeter) but are untouched by any ticket.
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK)
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=CRITICAL)
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id="ghost-workstation-not-in-hierarchy",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        overall = res.json()["data"]["overall"]

        # Root: floored at 1 regardless of the id's existence.
        assert overall["downtime_seconds"] == 1 * 3600
        assert overall["bottleneck"] is not None
        assert overall["critical"] is not None
        assert overall["downtime_seconds"] == (
            overall["bottleneck"]["downtime_seconds"] + overall["critical"]["downtime_seconds"]
        )

    def test_line_with_no_workstations_under_it_floors_into_a_slice_not_nowhere(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Scenario 30. A `production line`-scope ticket declared on a line
        with ZERO workstations under it is floored at 1 by `_ticket_weight`
        (root); `_locations_for_ticket` returns the empty
        `stations_by_line[line]` set as-is (no floor), so the weight enters
        no slice at all -- currently `0 + 0 = 0 != root (1)`. The sibling
        line's real bottleneck/critical workstations exist (populated,
        non-`None` perimeter) but are untouched, so this is exactly §9.2's
        own trap: `bottleneck`/`critical` would read "present with zero
        downtime" while the root actually carries 3600s nobody accounts
        for."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line_with_stations = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        line_empty = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(
            namespace_id=NS, production_line_id=line_with_stations["id"], type=BOTTLENECK
        )
        seed_workstation(
            namespace_id=NS, production_line_id=line_with_stations["id"], type=CRITICAL
        )
        _seed_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line_empty["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        overall = res.json()["data"]["overall"]

        # Root: floored at 1 (the referenced line has 0 workstations).
        assert overall["downtime_seconds"] == 1 * 3600
        assert overall["bottleneck"] is not None
        assert overall["critical"] is not None
        assert overall["downtime_seconds"] == (
            overall["bottleneck"]["downtime_seconds"] + overall["critical"]["downtime_seconds"]
        )


# --------------------------------------------------------------------------
# §9.3, scenario 31 -- one populate rule for `shift` and location paths.
# --------------------------------------------------------------------------


class TestDrilldownShiftAndTypePathPopulatesLikeLocation:
    """Scenario 31. Today the code populates a drill-down's slices off the
    deepest LOCATION step anywhere in the path, but requires `shift` to be
    the LAST step specifically (`services.py`: `elif last_location_kind is
    None and steps[-1][0] == "shift"`) -- so `uap/<id>/type/<t>` is
    populated while `shift/<id>/type/<t>` silently isn't, even though a
    shift step exists in the path (`shift_in_path`, already computed). This
    test is expected to FAIL against the current implementation: `bottleneck`
    /`critical` should be present on `shift:1>type:...` exactly as they are
    on a `uap:.../type:...` path, but are currently absent."""

    def test_shift_then_type_path_kpis_are_populated(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=BOTTLENECK)
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=CRITICAL)
        _seed_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            shift=1,
            down_time_type=DownTimeType.BREAKDOWN.value,
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get(
            "/kpi/drilldown",
            params={**_period(), "path": f"shift:1>type:{DownTimeType.BREAKDOWN.value}"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        kpis = res.json()["data"]["kpis"]
        assert "bottleneck" in kpis
        assert "critical" in kpis
