"""API-level coverage for the KPI slice of resource archiving (Work Unit
`test.kpi_resource_archiving`) — `GET /kpi/dashboard` only, since every
scenario below is reachable through the `overall`/`by_location` fields that
endpoint already returns.

TEST-FIRST MODE. `src/app/routers/kpi/services.py` has NO knowledge of
`archived_at` at all as of this revision (confirmed: no occurrence of the
string "archived" anywhere in that module) — `_ticket_downtime_seconds`
clamps a still-open ticket's end to `now`, `_location_hierarchy` loads every
UAP/line/workstation unconditionally, and `_pick_location_kind` counts every
loaded UAP/line with no regard for whether it is archived. Every test below
is therefore expected to fail on its OWN numeric/membership assertion (wrong
downtime seconds, wrong MTTR, a missing/extra row, a wrong `by_location`
`kind`) — never on a fixture/import error.

Scope boundary: this file is KPI OUTPUT only. It does not touch the
archiving endpoints, cascade, or list-visibility mechanics — those are
covered (and frozen) by `tests/api/test_resource_archiving.py`. Every
`archived_at` used here is seeded DIRECTLY into `fake_db` via the existing
`seed_uap`/`seed_production_line`/`seed_workstation` fixtures (plain dict
overrides — `factory.Factory(model=dict)` happily accepts an undeclared
`archived_at` kwarg), independent of whichever agent is building the
archiving endpoints themselves.

Boundary convention (created_at == archived_at), pinned by
`TestPerimeterBoundary` below: the rule is "still active at the ticket's
`created_at` (`archived_at` absent, or `archived_at` STRICTLY after
`created_at`)" — taken literally, equality does NOT satisfy "strictly
after", so a resource archived at the exact instant a ticket is created is
treated as already archived and excluded from that ticket's perimeter. This
is the one convention this suite pins for the equality case; any production
code disagreeing with it is an anomaly, not a fixture bug.

All tickets use fixed 2026-01-15 timestamps; `freeze_kpi_clock` (same
pattern as `test_kpi_scope_spread.py`) pins wall-clock "now" to
2026-01-15T18:00:00Z wherever a still-open ticket's `-> now` clamp matters
(the bounding scenarios) — every other scenario uses CLOSED tickets and
needs no clock freeze.
"""

import uuid
from datetime import date, datetime

import pytest

import src.app.routers.kpi.services as kpi_services_module
from src.app.core.firestore import NAMESPACE_SETTINGS_COLLECTION, SETTINGS_SUBCOLLECTION
from src.app.globals.enum import DownTimeStatus, DownTimeType, Process, Role

NS = "ns-kpi-resource-archiving"
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS, timezone="UTC", company_name="Archiving Plant")


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
    """Pins `services.datetime.now(tz)` to 2026-01-15 18:00 — only needed for
    the bounding scenarios, whose still-open tickets' downtime clamp has an
    upper bound of "now" that must be visibly different from `archived_at`."""
    fixed = datetime(2026, 1, 15, 18, 0, 0)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.replace(tzinfo=tz) if tz else fixed

    monkeypatch.setattr(kpi_services_module, "datetime", _FixedDatetime)
    return fixed


@pytest.fixture
def one_station_hierarchy(fake_db, seed_uap, seed_production_line, seed_workstation):
    """1 UAP / 1 line / 1 workstation — `_pick_location_kind` resolves to
    "station" for this shape, so `by_location` rows are keyed by station id."""
    _seed_settings(fake_db)
    uap = seed_uap(namespace_id=NS)
    line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
    station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
    return {"uap": uap, "line": line, "station": station}


def _two_station_hierarchy(fake_db, seed_uap, seed_production_line, seed_workstation, **station_overrides):
    """1 UAP / 1 line / 2 workstations (`station_a`, `station_b`) — used by
    the perimeter-at-ticket-date scenarios. `station_overrides` is a dict of
    `{"station_a": {...}, "station_b": {...}}` doc overrides (e.g.
    `archived_at`)."""
    _seed_settings(fake_db)
    uap = seed_uap(namespace_id=NS)
    line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
    station_a = seed_workstation(
        namespace_id=NS, production_line_id=line["id"], **station_overrides.get("station_a", {})
    )
    station_b = seed_workstation(
        namespace_id=NS, production_line_id=line["id"], **station_overrides.get("station_b", {})
    )
    return {"uap": uap, "line": line, "station_a": station_a, "station_b": station_b}


# --------------------------------------------------------------------------
# Bounding: an open ticket on an archived resource stops at `archived_at`,
# not `now`.
# --------------------------------------------------------------------------


class TestOpenTicketBoundedAtArchiving:
    def test_open_ticket_on_archived_workstation_bounds_at_archived_at(
        self, client, seed_user, auth_headers, fake_db, one_station_hierarchy, freeze_kpi_clock
    ):
        """Station archived at 10:00; ticket opened 07:00, never closed; "now"
        is frozen at 18:00. Expected downtime: 10:00 - 07:00 = 3h = 10800s
        (bounded at `archived_at`), NOT 07:00 -> 18:00 = 11h = 39600s (what
        today's `-> now` clamp would produce). The ticket's stored `status`
        is untouched (still PENDING) -- only the resource's `archived_at`
        produces the bound."""
        owner = _owner(seed_user)
        fake_db.collection("workstation").document(
            one_station_hierarchy["station"]["id"]
        ).update({"archived_at": "2026-01-15T10:00:00+00:00"})
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=one_station_hierarchy["station"]["id"],
            production_line_id=one_station_hierarchy["line"]["id"],
            status=DownTimeStatus.PENDING.value,
            created_at=_utc(7),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]

        assert data["overall"]["downtime_seconds"] == 10800
        by_location = _by_location(res)
        assert by_location[one_station_hierarchy["station"]["id"]]["kpis"]["downtime_seconds"] == 10800

    def test_same_open_ticket_on_an_active_workstation_runs_to_now(
        self, client, seed_user, auth_headers, fake_db, one_station_hierarchy, freeze_kpi_clock
    ):
        """Contrast case, same ticket shape, station NOT archived: the
        downtime runs its full 07:00 -> 18:00 ("now") = 11h = 39600s -- this
        is what makes the bounded test above meaningful rather than an
        accidental number."""
        owner = _owner(seed_user)
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=one_station_hierarchy["station"]["id"],
            production_line_id=one_station_hierarchy["line"]["id"],
            status=DownTimeStatus.PENDING.value,
            created_at=_utc(7),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 39600

    def test_closed_before_archive_keeps_its_real_duration(
        self, client, seed_user, auth_headers, fake_db, one_station_hierarchy, freeze_kpi_clock
    ):
        """Ticket CLOSED at 08:00, station archived later at 12:00: a closed
        ticket's natural end is always `resolved_at`, never `archived_at` or
        `now` -- real duration 07:00 -> 08:00 = 1h = 3600s, unaffected by the
        later archiving."""
        owner = _owner(seed_user)
        fake_db.collection("workstation").document(
            one_station_hierarchy["station"]["id"]
        ).update({"archived_at": "2026-01-15T12:00:00+00:00"})
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=one_station_hierarchy["station"]["id"],
            production_line_id=one_station_hierarchy["line"]["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 3600

    def test_open_ticket_archived_before_the_period_contributes_zero(
        self, client, seed_user, auth_headers, fake_db, one_station_hierarchy, freeze_kpi_clock
    ):
        """Carry-over ticket created the day before the queried period
        (2026-01-14 07:00, still PENDING), station archived later that same
        day at 20:00 -- BEFORE `period_start` (2026-01-15 00:00). Effective
        window = [max(created_at, period_start), min(archived_at,
        period_upper)] = [01-15 00:00, 01-14 20:00], which is empty/negative
        -> clamped to 0. This is the only ticket in the namespace, so the
        header downtime is exactly 0."""
        owner = _owner(seed_user)
        fake_db.collection("workstation").document(
            one_station_hierarchy["station"]["id"]
        ).update({"archived_at": "2026-01-14T20:00:00+00:00"})
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=one_station_hierarchy["station"]["id"],
            production_line_id=one_station_hierarchy["line"]["id"],
            status=DownTimeStatus.PENDING.value,
            created_at=_utc(7, day=14),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 0


# --------------------------------------------------------------------------
# MTTR: a bounded open ticket must stay out of MTTR; a ticket genuinely
# closed before the archive must keep its real duration there.
# --------------------------------------------------------------------------


class TestMttrUnaffectedByArchivingExceptViaStatus:
    def test_bounded_open_ticket_is_absent_from_mttr(
        self, client, seed_user, auth_headers, fake_db, one_station_hierarchy, freeze_kpi_clock
    ):
        """Same ticket as the first bounding scenario: its stored `status`
        stays PENDING (archiving never writes to the ticket), so
        `_mttr_seconds` -- CLOSED tickets only -- must still see zero closed
        tickets and report `mttr_seconds == 0`, exactly like today's "still
        open" case. A future change that "helpfully" closed a bounded ticket
        on archive would silently corrupt this."""
        owner = _owner(seed_user)
        fake_db.collection("workstation").document(
            one_station_hierarchy["station"]["id"]
        ).update({"archived_at": "2026-01-15T10:00:00+00:00"})
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=one_station_hierarchy["station"]["id"],
            production_line_id=one_station_hierarchy["line"]["id"],
            status=DownTimeStatus.PENDING.value,
            created_at=_utc(7),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["mttr_seconds"] is None

    def test_ticket_closed_before_the_archive_counts_in_mttr_with_real_duration(
        self, client, seed_user, auth_headers, fake_db, one_station_hierarchy, freeze_kpi_clock
    ):
        """Ticket CLOSED 07:00 -> 08:00 (1h), station archived later at
        12:00: MTTR = 3600s, the ticket's real (unbounded-by-archiving)
        duration, since it was genuinely CLOSED before the archive."""
        owner = _owner(seed_user)
        fake_db.collection("workstation").document(
            one_station_hierarchy["station"]["id"]
        ).update({"archived_at": "2026-01-15T12:00:00+00:00"})
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=one_station_hierarchy["station"]["id"],
            production_line_id=one_station_hierarchy["line"]["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["mttr_seconds"] == 3600

    def test_mttr_unchanged_when_every_ticket_on_an_archived_resource_is_closed(
        self, client, seed_user, auth_headers, fake_db, one_station_hierarchy, freeze_kpi_clock
    ):
        """Two CLOSED tickets (1h and 0.5h) on a station archived at 12:00,
        both resolved before the archive -- MTTR = mean(3600, 1800) = 2700s,
        identical to the unarchived case; archiving a resource whose
        tickets are all closed changes nothing about MTTR."""
        owner = _owner(seed_user)
        fake_db.collection("workstation").document(
            one_station_hierarchy["station"]["id"]
        ).update({"archived_at": "2026-01-15T12:00:00+00:00"})
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=one_station_hierarchy["station"]["id"],
            production_line_id=one_station_hierarchy["line"]["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(6),
            resolved_at=_utc(7),
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=one_station_hierarchy["station"]["id"],
            production_line_id=one_station_hierarchy["line"]["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(9),
            resolved_at=_utc(9, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["mttr_seconds"] == 2700  # (3600+1800)/2


# --------------------------------------------------------------------------
# Count: history is never erased by archiving.
# --------------------------------------------------------------------------


class TestCountPreservedOnArchivedResource:
    def test_bounded_ticket_still_counts_in_the_number_of_downtimes(
        self, client, seed_user, auth_headers, fake_db, one_station_hierarchy, freeze_kpi_clock
    ):
        """Same bounded ticket as the first scenario: it was created inside
        the queried period, so it is part of `current` regardless of status
        or archiving, and must still count once toward the header `count`."""
        owner = _owner(seed_user)
        fake_db.collection("workstation").document(
            one_station_hierarchy["station"]["id"]
        ).update({"archived_at": "2026-01-15T10:00:00+00:00"})
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=one_station_hierarchy["station"]["id"],
            production_line_id=one_station_hierarchy["line"]["id"],
            status=DownTimeStatus.PENDING.value,
            created_at=_utc(7),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["count"] == 1


# --------------------------------------------------------------------------
# Perimeter at ticket date (rule 4) -- the most expensive rule, most
# coverage. All tickets here are CLOSED (no clock-freeze needed).
# --------------------------------------------------------------------------


class TestPerimeterEvaluatedAtTicketDate:
    def test_plant_scope_ticket_created_after_archival_excludes_the_workstation(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """`station_a` archived 2026-01-10 (before the ticket's own
        2026-01-15 07:00 `created_at`); `station_b` stays active. A
        plant-scope ticket created AFTER that archival must weigh only
        `station_b` -> weight 1, downtime = 30min x 1 = 1800s (not 3600s,
        what counting both would give)."""
        owner = _owner(seed_user)
        hierarchy = _two_station_hierarchy(
            fake_db,
            seed_uap,
            seed_production_line,
            seed_workstation,
            station_a={"archived_at": "2026-01-10T00:00:00+00:00"},
        )
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 1800  # 30min x 1

    def test_plant_scope_ticket_created_before_archival_includes_the_workstation(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Same shape, `station_a` archived 2026-01-20 -- AFTER the ticket's
        2026-01-15 `created_at` -- so at ticket-date `station_a` was still
        active: weight 2, downtime = 30min x 2 = 3600s."""
        owner = _owner(seed_user)
        hierarchy = _two_station_hierarchy(
            fake_db,
            seed_uap,
            seed_production_line,
            seed_workstation,
            station_a={"archived_at": "2026-01-20T00:00:00+00:00"},
        )
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 3600  # 30min x 2

    def test_uap_scope_ticket_behaves_the_same_one_level_down(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Identical mechanics, but for a `uap`-scope ticket: `station_a`
        archived BEFORE the ticket's `created_at` is excluded from the UAP's
        weight -> weight 1, downtime = 30min x 1 = 1800s."""
        owner = _owner(seed_user)
        hierarchy = _two_station_hierarchy(
            fake_db,
            seed_uap,
            seed_production_line,
            seed_workstation,
            station_a={"archived_at": "2026-01-10T00:00:00+00:00"},
        )
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=hierarchy["uap"]["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 1800  # 30min x 1


class TestPerimeterBoundary:
    """Boundary convention, stated in this module's docstring: `archived_at
    == created_at` is NOT "strictly after" -- the resource is excluded, as
    if it were already archived at the instant the ticket was opened."""

    def test_workstation_archived_at_exactly_the_tickets_created_at_is_excluded(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        hierarchy = _two_station_hierarchy(
            fake_db,
            seed_uap,
            seed_production_line,
            seed_workstation,
            station_a={"archived_at": _utc(7)},  # == the ticket's own created_at below
        )
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["overall"]["downtime_seconds"] == 1800  # 30min x 1 (station_a excluded)

    def test_plant_ticket_where_every_workstation_was_already_archived_weighs_zero(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Both `station_a` and `station_b` archived before the ticket's
        `created_at` -- the resolved perimeter is empty. `_ticket_weight`'s
        `max(1, ...)` floor does NOT apply here: that floor exists for a
        perimeter empty because of MISSING data (a UAP with no workstation
        registered yet, or a ticket pointing at a since-deleted
        workstation), where returning 0 would silently erase a genuinely
        declared downtime. An entirely-archived perimeter is a different,
        KNOWN fact -- every resource concerned was legitimately taken out of
        service -- so the floor's justification does not carry over here.
        Flooring at 1 would invent a workstation that no longer exists and
        inflate the plant's downtime with time lost on a machine nobody
        operates any more. Expected: weight 0, downtime = 30min x 0 = 0s.
        The ticket still shows up on the dashboard though: `count` is not
        weighted by workstations, so it stays 1."""
        owner = _owner(seed_user)
        hierarchy = _two_station_hierarchy(
            fake_db,
            seed_uap,
            seed_production_line,
            seed_workstation,
            station_a={"archived_at": "2026-01-10T00:00:00+00:00"},
            station_b={"archived_at": "2026-01-11T00:00:00+00:00"},
        )
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
        assert data["overall"]["downtime_seconds"] == 0  # 30min x 0 (entirely-archived perimeter, not a floor case)
        assert data["overall"]["count"] == 1


# --------------------------------------------------------------------------
# Row visibility (rule 5): an archived resource is a `by_location` row only
# when it has >= 1 ticket in the queried period.
# --------------------------------------------------------------------------


class TestArchivedRowVisibility:
    def test_archived_resource_with_a_ticket_in_period_appears_as_a_row(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        archived_station = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], archived_at="2026-01-20T00:00:00+00:00"
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=archived_station["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert archived_station["id"] in by_location
        assert by_location[archived_station["id"]]["kpis"]["downtime_seconds"] == 1800

    def test_archived_resource_with_no_ticket_in_period_is_absent(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        active_station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        archived_station = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], archived_at="2026-01-05T00:00:00+00:00"
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=active_station["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert archived_station["id"] not in by_location
        assert active_station["id"] in by_location

    def test_archived_resource_whose_only_ticket_is_outside_the_period_is_absent(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        archived_station = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], archived_at="2026-01-20T00:00:00+00:00"
        )
        # Ticket dated day 16 -- outside the day-15 queried period below.
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=archived_station["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7, day=16),
            resolved_at=_utc(7, minute=30, day=16),
        )

        res = client.get("/kpi/dashboard", params=_period(day=15), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        assert archived_station["id"] not in _by_location(res)

    def test_archived_resource_with_no_tickets_does_not_push_breakdown_to_a_coarser_kind(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """1 real, active UAP (1 line, 2 stations) -> `_pick_location_kind`
        must resolve to "station" (today's existing rule for this shape). An
        extra ARCHIVED UAP with no lines/stations and no tickets anywhere
        must not count toward the UAP group total and push the breakdown up
        to "uap" -- it contributes zero rows, so it must not be counted
        when deciding the granularity either."""
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap_active = seed_uap(namespace_id=NS, name="UAP Active")
        seed_uap(namespace_id=NS, name="UAP Archived (empty)", archived_at="2026-01-01T00:00:00+00:00")
        line = seed_production_line(namespace_id=NS, uap_id=uap_active["id"])
        station_1 = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station_1["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(7, 30),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        by_location = _by_location(res)
        assert by_location, "expected at least one row"
        for row in by_location.values():
            assert row["kind"] == "station"


# --------------------------------------------------------------------------
# Reconciliation: a mix of archived and active resources must still sum
# `by_location` back to the header total (the existing invariant
# `test_kpi_scope_spread.py::TestOwnSharesWeighting` protects).
# --------------------------------------------------------------------------


class TestReconciliationWithMixedArchivedAndActiveResources:
    def test_plant_ticket_over_one_archived_and_one_active_station_still_reconciles(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """`station_a` archived 2026-01-20 (AFTER the ticket's 01-15
        `created_at`, so still active at ticket-date and included in the
        perimeter): weight 2, downtime 30min x 2 = 3600s. Spread into the
        2-station breakdown, each row gets its OWN share (1 station each) ->
        1800s per row, summing back to the header's 3600s."""
        owner = _owner(seed_user)
        hierarchy = _two_station_hierarchy(
            fake_db,
            seed_uap,
            seed_production_line,
            seed_workstation,
            station_a={"archived_at": "2026-01-20T00:00:00+00:00"},
        )
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

        header_downtime = data["overall"]["downtime_seconds"]
        assert header_downtime == 3600
        assert by_location[hierarchy["station_a"]["id"]]["kpis"]["downtime_seconds"] == 1800
        assert by_location[hierarchy["station_b"]["id"]]["kpis"]["downtime_seconds"] == 1800

        row_sum = sum(row["kpis"]["downtime_seconds"] for row in by_location.values())
        assert row_sum == header_downtime


# --------------------------------------------------------------------------
# Non-regression: no archived resource at all -> today's numbers, unchanged.
# These are expected to PASS already -- flagged as non-regression, not new
# behavior -- since nothing in this scenario touches `archived_at`.
# --------------------------------------------------------------------------


class TestNonRegressionNoArchivedResources:
    def test_namespace_with_no_archived_resource_produces_todays_numbers(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        owner = _owner(seed_user)
        _seed_settings(fake_db)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            production_line_id=line["id"],
            status=DownTimeStatus.CLOSED.value,
            created_at=_utc(7),
            resolved_at=_utc(8),
        )

        res = client.get("/kpi/dashboard", params=_period(), headers=auth_headers(owner))
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["overall"]["downtime_seconds"] == 3600
        assert data["overall"]["count"] == 1
        assert data["overall"]["mttr_seconds"] == 3600
        by_location = _by_location(res)
        assert by_location[station["id"]]["kpis"]["downtime_seconds"] == 3600
