"""API tests for `GET /down-times/gantt`, per `.claude/specs/downtime-gantt.md`
§2 (test-first — the endpoint does not exist yet).

Scenarios are derived **only** from the BOM (§2.1-§2.5), never from an
implementation, per the test-first gate. Every test below is expected to
currently fail — most on a plain 404 (no `/down-times/gantt` route
registered yet; the request instead falls through to the existing
`GET /down-times/{issue_id}` route, matching `issue_id="gantt"`, which
returns its own 404 since no such ticket exists), a handful on their own
assertion once the endpoint is minimally reachable. See the per-test
docstring / the hand-off report for the exact reason each one currently
fails.

**Assumption, stated explicitly (not read from any implementation):** the
BOM says "service in the same package" as the router
(`src/app/routers/down_time`) — the only service module there today is
`services.py`, already wired into `tests/conftest.py::fake_db` and already
importing `datetime` by name. The one test that needs to freeze "now" (the
default-`day` test) assumes the gantt logic resolves "today" through that
same module's `datetime` name, mirroring the KPI suite's own pattern
(`kpi_services_module.datetime`). If the implementation resolves the
production day elsewhardse, that one test's time-freeze needs re-pointing —
an anomaly for the developer, not a fixture bug.

No real Firestore/Pub/Sub/network is touched: `fake_db` is the in-memory
double, wired for every module already known to this package (`down_time`,
`kpi`, ...).
"""

import importlib
import uuid
from datetime import date, datetime, timedelta

import pytest

from src.app.core.firestore import NAMESPACE_SETTINGS_COLLECTION, SETTINGS_SUBCOLLECTION
from src.app.globals.enum import DownTimeStatus, DownTimeType, Process, Role, WorkstationType
from src.app.routers.down_time import services as down_time_services_module

GANTT_URL = "/down-times/gantt"
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"

NS = "ns-gantt"
OTHER_NS = "ns-gantt-other"
TZ = "Europe/Paris"

# Same role set as `_kpi_scope` (§2 of the BOM): owner/admin/manager/production
# supervisor. Every other role must get 403.
ALLOWED_ROLES = [
    Role.OWNER.value,
    Role.ADMIN.value,
    Role.MANAGER.value,
    Role.PRODUCTION_SUPERVISOR.value,
]
# Reports downtimes but has no `_kpi_scope`-style visibility — a deliberately
# realistic forbidden role (not a role that plausibly "should" have access).
FORBIDDEN_ROLE = Role.PRODUCTION_AGENT.value


@pytest.fixture(autouse=True)
def _seed_namespace(seed_namespace):
    seed_namespace(id=NS, timezone=TZ, company_name="Acme Plant")
    seed_namespace(id=OTHER_NS, timezone=TZ, company_name="Other Plant")


def _user(seed_user, role, namespace_id=NS, **overrides):
    overrides.setdefault("namespace_id", namespace_id)
    overrides.setdefault("role", role)
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
    """A down-time issue document, in the exact shape `add_down_time` writes
    (see `tests/api/test_kpi_dashboard.py::_seed_issue` for the precedent)."""
    issue_id = overrides.pop("id", str(uuid.uuid4()))
    now_iso = datetime(2026, 1, 15, 9, 0).isoformat()
    issue = {
        "id": issue_id,
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
        "rejected_at": None,
        "rejected_by": None,
        "closed_at": None,
        "closed_by": None,
    }
    issue.update(overrides)
    fake_db.collection(DOWN_TIME_COLLECTION).document(namespace_id).collection(
        ISSUES_SUBCOLLECTION
    ).document(issue_id).set(issue)
    return issue


def _paris(day, hour, minute=0):
    return f"2026-01-{day:02d}T{hour:02d}:{minute:02d}:00+01:00"


@pytest.fixture
def freeze_today(monkeypatch):
    """Pins "now" to 2026-01-15 10:00 Paris time, for the `day`-omitted
    default test only — see the module docstring's assumption about where
    the gantt logic resolves "today"."""
    fixed = datetime(2026, 1, 15, 10, 0, 0)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.replace(tzinfo=tz) if tz else fixed

    monkeypatch.setattr(down_time_services_module, "datetime", _FixedDatetime)
    return fixed


# --------------------------------------------------------------------------- #
# Authentication / authorization / tenant isolation
# --------------------------------------------------------------------------- #


class TestDownTimeGanttAuthz:
    """GET /down-times/gantt — role scope, auth, tenant isolation."""

    def test_unauthenticated_returns_401(self, client, fake_db):
        res = client.get(GANTT_URL, params={"day": "2026-01-15"})
        assert res.status_code == 401

    def test_forbidden_role_returns_403(self, client, seed_user, auth_headers, fake_db):
        agent = _user(seed_user, FORBIDDEN_ROLE)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(agent)
        )
        assert res.status_code == 403

    @pytest.mark.parametrize("role", ALLOWED_ROLES)
    def test_allowed_role_returns_200(
        self, client, seed_user, auth_headers, fake_db, role
    ):
        _seed_settings(fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"})
        caller = _user(seed_user, role)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text

    def test_cross_namespace_resource_never_appears(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        """A workstation (and its downtime) belonging to another tenant must
        never leak into the caller's gantt, even indirectly."""
        _seed_settings(fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"})
        _seed_settings(fake_db, namespace_id=OTHER_NS, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"})
        other_station = seed_workstation(namespace_id=OTHER_NS)
        _seed_issue(
            fake_db,
            namespace_id=OTHER_NS,
            down_time_scope="work station",
            workstation_id=other_station["id"],
            created_at=_paris(15, 8),
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        all_ids = (
            [u["uap_id"] for u in data["uaps"]]
            + [l["line_id"] for l in data["lines"]]
            + [w["workstation_id"] for w in data["work_stations"]]
        )
        assert other_station["id"] not in all_ids


# --------------------------------------------------------------------------- #
# `day` / `type` query params
# --------------------------------------------------------------------------- #


class TestDownTimeGanttQueryParams:
    """`day` (optional, default today) and `type` (optional filter)."""

    def test_day_omitted_defaults_to_today_in_namespace_timezone(
        self, client, seed_user, auth_headers, fake_db, freeze_today
    ):
        _seed_settings(fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"})
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(GANTT_URL, headers=auth_headers(caller))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["day"] == "2026-01-15"

    def test_day_supplied_returns_that_production_day(
        self, client, seed_user, auth_headers, fake_db
    ):
        _seed_settings(fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"})
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-02-01"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["day"] == "2026-02-01"

    def test_malformed_day_returns_422(self, client, seed_user, auth_headers, fake_db):
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "15-01-2026"}, headers=auth_headers(caller)
        )
        assert res.status_code == 422

    def test_unknown_type_returns_422(self, client, seed_user, auth_headers, fake_db):
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL,
            params={"day": "2026-01-15", "type": "nonexistent"},
            headers=auth_headers(caller),
        )
        assert res.status_code == 422


# --------------------------------------------------------------------------- #
# The production-day window (§2.2)
# --------------------------------------------------------------------------- #


class TestDownTimeGanttWindow:
    """`window` / `shifts[]` — §2.2."""

    def test_single_shift_window_matches_shift_1_bounds(
        self, client, seed_user, auth_headers, fake_db
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        window = res.json()["data"]["window"]
        assert window["start"] == _paris(15, 6)
        assert window["end"] == _paris(15, 14)

    def test_wrapping_last_shift_carries_window_end_to_next_day(
        self, client, seed_user, auth_headers, fake_db
    ):
        """3-shift plant, shift 3 wraps past midnight -> `window.end` lands
        on the calendar day AFTER `day`."""
        _seed_settings(
            fake_db,
            shift_number=3,
            shift_1={"start_time": "06:00", "end_time": "14:00"},
            shift_2={"start_time": "14:00", "end_time": "22:00"},
            shift_3={"start_time": "22:00", "end_time": "06:00"},
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["window"]["start"] == _paris(15, 6)
        assert data["window"]["end"] == "2026-01-16T06:00:00+01:00"
        assert len(data["shifts"]) == 3
        shift_3 = next(s for s in data["shifts"] if s["shift"] == "3")
        assert shift_3["start"] == _paris(15, 22)
        assert shift_3["end"] == "2026-01-16T06:00:00+01:00"

    def test_shift_break_projected_onto_absolute_datetimes(
        self, client, seed_user, auth_headers, fake_db
    ):
        _seed_settings(
            fake_db,
            shift_number=1,
            shift_1={
                "start_time": "06:00",
                "end_time": "14:00",
                "break_start_time": "09:30",
                "break_end_time": "10:00",
            },
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        shift_1 = res.json()["data"]["shifts"][0]
        assert shift_1["break_start"] == _paris(15, 9, 30)
        assert shift_1["break_end"] == _paris(15, 10)

    def test_no_usable_shift_configuration_falls_back_to_calendar_day(
        self, client, seed_user, auth_headers, fake_db
    ):
        _seed_settings(fake_db, shift_number=1, shift_1=None)
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["window"]["start"] == _paris(15, 0)
        assert data["window"]["end"] == "2026-01-16T00:00:00+01:00"
        assert data["shifts"] == []

    def test_no_settings_document_falls_back_to_calendar_day(
        self, client, seed_user, auth_headers, fake_db
    ):
        """No `NamespaceSettings` doc at all for the namespace."""
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["window"]["start"] == _paris(15, 0)
        assert data["window"]["end"] == "2026-01-16T00:00:00+01:00"
        assert data["shifts"] == []

    def test_night_first_shift_declaration_still_spans_full_production_day(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        """§2.2 rev (review finding B1): a plant that numbers its NIGHT
        shift `shift_1` (declaration order: 22:00->06:00, 06:00->14:00,
        14:00->22:00) must not get a truncated/zero-length window just
        because `shift_1` isn't the chronologically-first shift.
        `window.start`/`window.end` are the min/max of the PROJECTED
        datetimes, never `shifts[0]`/`shifts[-1]` of declaration order — a
        bug that collapses the window to `[22:00, 22:00)` and empties the
        whole gantt. A downtime that falls squarely in the middle of the
        true production day must still be on the gantt."""
        _seed_settings(
            fake_db,
            shift_number=3,
            shift_1={"start_time": "22:00", "end_time": "06:00"},
            shift_2={"start_time": "06:00", "end_time": "14:00"},
            shift_3={"start_time": "14:00", "end_time": "22:00"},
        )
        station = seed_workstation(namespace_id=NS)
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 10),
            resolved_at=_paris(15, 11),
            status=DownTimeStatus.RESOLVED.value,
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["window"]["start"] == _paris(15, 6)
        assert data["window"]["end"] == "2026-01-16T06:00:00+01:00"
        row = next(
            w for w in data["work_stations"] if w["workstation_id"] == station["id"]
        )
        assert {
            "start_time": _paris(15, 10), "end_time": _paris(15, 11), "state": "down"
        } in row["down_times"]
        # `shifts[]` is ordered chronologically (2, 3, 1), never by the
        # declaration order (1, 2, 3) the namespace happened to number them.
        assert [s["shift"] for s in data["shifts"]] == ["2", "3", "1"]

    def test_degenerate_shift_window_falls_back_to_calendar_day(
        self, client, seed_user, auth_headers, fake_db
    ):
        """§2.2 rev (review finding B1): whenever the computed
        `window.end` is not strictly after `window.start` — here a shift
        misconfigured with an equal start/end — the endpoint must fall back
        to the calendar day rather than return a zero-length or inverted
        window."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "08:00", "end_time": "08:00"}
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["window"]["start"] == _paris(15, 0)
        assert data["window"]["end"] == "2026-01-16T00:00:00+01:00"

    def test_break_outside_its_own_shift_window_is_ignored(
        self, client, seed_user, auth_headers, fake_db
    ):
        """§2.2 (review finding W4): a break that does not fall inside its
        own shift (here 20:00->21:00 on a 06:00->14:00 shift) must be
        ignored exactly as the KPI services ignore it (`_valid_break`) —
        not projected as a non-planned band floating outside the shift."""
        _seed_settings(
            fake_db,
            shift_number=1,
            shift_1={
                "start_time": "06:00",
                "end_time": "14:00",
                "break_start_time": "20:00",
                "break_end_time": "21:00",
            },
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        shift_1 = res.json()["data"]["shifts"][0]
        assert shift_1["break_start"] is None
        assert shift_1["break_end"] is None

    def test_timestamps_are_full_iso_datetimes_not_hhmm(
        self, client, seed_user, auth_headers, fake_db
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        window = res.json()["data"]["window"]
        # A bare "HH:MM" is 5 chars; a full ISO datetime is much longer and
        # parses as a date, not just a time.
        assert datetime.fromisoformat(window["start"]).date() == date(2026, 1, 15)
        assert datetime.fromisoformat(window["end"]).date() == date(2026, 1, 15)


# --------------------------------------------------------------------------- #
# Response shape (§2.1)
# --------------------------------------------------------------------------- #


class TestDownTimeGanttShape:
    """The three keys, sorting, and "only resources with intervals" rule."""

    def test_three_keys_always_present_even_when_empty(
        self, client, seed_user, auth_headers, fake_db
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["uaps"] == []
        assert data["lines"] == []
        assert data["work_stations"] == []

    def test_resource_with_no_interval_that_day_is_absent(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        # A workstation exists but has no downtime ticket at all.
        seed_workstation(namespace_id=NS)
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["work_stations"] == []

    def test_down_times_sorted_by_start_time_ascending(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        station = seed_workstation(namespace_id=NS)
        # Two disjoint, non-touching down segments, seeded out of order.
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 11),
            resolved_at=_paris(15, 11, 30),
            status=DownTimeStatus.RESOLVED.value,
            closed_at=_paris(15, 11, 45),
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 7),
            resolved_at=_paris(15, 7, 30),
            status=DownTimeStatus.RESOLVED.value,
            closed_at=_paris(15, 7, 45),
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        row = next(
            w for w in res.json()["data"]["work_stations"] if w["workstation_id"] == station["id"]
        )
        starts = [dt["start_time"] for dt in row["down_times"]]
        assert starts == sorted(starts)


# --------------------------------------------------------------------------- #
# Interval states (§2.3)
# --------------------------------------------------------------------------- #


class TestDownTimeGanttIntervalStates:
    """down/unconfirmed segmentation, open-ended runs, clamping, merging."""

    def _get(self, client, seed_user, auth_headers):
        caller = _user(seed_user, Role.OWNER.value)
        return client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )

    def _row(self, res, station_id):
        return next(
            w
            for w in res.json()["data"]["work_stations"]
            if w["workstation_id"] == station_id
        )

    def test_down_state_from_created_to_resolved(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        """The ticket is resolved but never closed, so besides its `down`
        08:00-09:00 span it also contributes an open-ended `unconfirmed`
        tail 09:00-window.end (14:00, §2.3 "resolved but never closed")."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        station = seed_workstation(namespace_id=NS)
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        res = self._get(client, seed_user, auth_headers)
        assert res.status_code == 200, res.text
        row = self._row(res, station["id"])
        assert row["down_times"] == [
            {"start_time": _paris(15, 8), "end_time": _paris(15, 9), "state": "down"},
            {"start_time": _paris(15, 9), "end_time": _paris(15, 14), "state": "unconfirmed"},
        ]

    def test_unconfirmed_state_from_resolved_to_closed(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        station = seed_workstation(namespace_id=NS)
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            closed_at=_paris(15, 9, 30),
            status=DownTimeStatus.CLOSED.value,
        )
        res = self._get(client, seed_user, auth_headers)
        assert res.status_code == 200, res.text
        row = self._row(res, station["id"])
        assert {"start_time": _paris(15, 9), "end_time": _paris(15, 9, 30), "state": "unconfirmed"} in row["down_times"]

    def test_never_resolved_runs_down_to_window_end(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        station = seed_workstation(namespace_id=NS)
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 13),
            status=DownTimeStatus.ONGOING.value,
            acknowledged_at=_paris(15, 13, 5),
        )
        res = self._get(client, seed_user, auth_headers)
        assert res.status_code == 200, res.text
        row = self._row(res, station["id"])
        assert row["down_times"] == [
            {"start_time": _paris(15, 13), "end_time": _paris(15, 14), "state": "down"}
        ]

    def test_resolved_never_closed_unconfirmed_runs_to_window_end(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        station = seed_workstation(namespace_id=NS)
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 12),
            resolved_at=_paris(15, 13),
            status=DownTimeStatus.RESOLVED.value,
        )
        res = self._get(client, seed_user, auth_headers)
        assert res.status_code == 200, res.text
        row = self._row(res, station["id"])
        assert {"start_time": _paris(15, 13), "end_time": _paris(15, 14), "state": "unconfirmed"} in row["down_times"]

    def test_rejected_resolution_renders_one_continuous_down_bar(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        """§2.3 (developer ruling, 2026-09-11): `reject_resolution` nulls
        `resolved_at` (`resolved_at`/`resolved_by` -> None, `rejected_at`/
        `rejected_by` set, status back to `ongoing` — see
        `services.reject_resolution`), so the resolved->rejected
        `unconfirmed` slice is not recoverable from the stored document. A
        rejected ticket must therefore render as ONE continuous `down` bar
        from `created_at` to `window.end`, the conservative rendering since
        production itself said the resource was not back. This is the only
        legitimate seed shape for a rejected ticket — the application never
        writes a document carrying `resolved_at` and `rejected_at`
        together, so no test may seed one (that was the prior, deleted,
        version of this test)."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        station = seed_workstation(namespace_id=NS)
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 8),
            resolved_at=None,
            resolved_by=None,
            rejected_at=_paris(15, 9, 30),
            rejected_by="rejecter-1",
            status=DownTimeStatus.ONGOING.value,
            rejection_count=1,
        )
        res = self._get(client, seed_user, auth_headers)
        assert res.status_code == 200, res.text
        row = self._row(res, station["id"])
        assert row["down_times"] == [
            {"start_time": _paris(15, 8), "end_time": _paris(15, 14), "state": "down"}
        ]

    def test_ticket_started_before_window_is_clamped_to_window_start(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        station = seed_workstation(namespace_id=NS)
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 3),  # before window.start (06:00)
            resolved_at=_paris(15, 7),
            status=DownTimeStatus.RESOLVED.value,
        )
        res = self._get(client, seed_user, auth_headers)
        assert res.status_code == 200, res.text
        row = self._row(res, station["id"])
        down_segments = [dt for dt in row["down_times"] if dt["state"] == "down"]
        assert down_segments == [
            {"start_time": _paris(15, 6), "end_time": _paris(15, 7), "state": "down"}
        ]

    def test_interval_entirely_outside_window_is_dropped(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        station = seed_workstation(namespace_id=NS)
        # Fully resolved and closed the day before the queried window.
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(14, 8),
            resolved_at=_paris(14, 9),
            closed_at=_paris(14, 9, 30),
            status=DownTimeStatus.CLOSED.value,
        )
        res = self._get(client, seed_user, auth_headers)
        assert res.status_code == 200, res.text
        assert res.json()["data"]["work_stations"] == []

    def test_overlapping_same_state_intervals_are_merged(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        station = seed_workstation(namespace_id=NS)
        # Two independent tickets, both `down`, overlapping 08:30-09:00.
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 8, 30),
            resolved_at=_paris(15, 10),
            status=DownTimeStatus.RESOLVED.value,
        )
        res = self._get(client, seed_user, auth_headers)
        assert res.status_code == 200, res.text
        row = self._row(res, station["id"])
        down_segments = [dt for dt in row["down_times"] if dt["state"] == "down"]
        assert down_segments == [
            {"start_time": _paris(15, 8), "end_time": _paris(15, 10), "state": "down"}
        ]

    def test_down_is_subtracted_from_overlapping_unconfirmed(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        """A confirmed `down` stop beats an overlapping `unconfirmed` one —
        the overlap is removed from the `unconfirmed` segment. Ticket A
        contributes `down` 07:00-08:00 and `unconfirmed` 08:00-09:00
        (resolved 08:00, closed 09:00). Ticket B contributes `down`
        08:30-08:45 and, since it is never closed, an open-ended
        `unconfirmed` tail 08:45-window.end (14:00, §2.3). Merged per state:
        `unconfirmed` unions to 08:00-14:00 (08:00-09:00 touches/overlaps
        08:45-14:00), then has both `down` segments' overlap subtracted,
        splitting into 08:00-08:30 and 08:45-14:00."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        station = seed_workstation(namespace_id=NS)
        # Ticket A: down 07:00-08:00, unconfirmed 08:00-09:00 (resolved 08:00, closed 09:00).
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 7),
            resolved_at=_paris(15, 8),
            closed_at=_paris(15, 9),
            status=DownTimeStatus.CLOSED.value,
        )
        # Ticket B: down 08:30-08:45, overlapping ticket A's unconfirmed span,
        # and never closed so its own unconfirmed tail runs to window.end.
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 8, 30),
            resolved_at=_paris(15, 8, 45),
            status=DownTimeStatus.RESOLVED.value,
        )
        res = self._get(client, seed_user, auth_headers)
        assert res.status_code == 200, res.text
        row = self._row(res, station["id"])
        unconfirmed_segments = [dt for dt in row["down_times"] if dt["state"] == "unconfirmed"]
        down_segments = [dt for dt in row["down_times"] if dt["state"] == "down"]
        assert {
            "start_time": _paris(15, 7), "end_time": _paris(15, 8), "state": "down"
        } in down_segments
        assert {
            "start_time": _paris(15, 8, 30), "end_time": _paris(15, 8, 45), "state": "down"
        } in down_segments
        assert {"start_time": _paris(15, 8), "end_time": _paris(15, 8, 30), "state": "unconfirmed"} in unconfirmed_segments
        assert {"start_time": _paris(15, 8, 45), "end_time": _paris(15, 14), "state": "unconfirmed"} in unconfirmed_segments
        # The subtracted middle slice must not remain as its own segment.
        assert not any(
            dt["start_time"] == _paris(15, 8, 30) and dt["state"] == "unconfirmed"
            for dt in unconfirmed_segments
        )


# --------------------------------------------------------------------------- #
# Row attribution (§2.4)
# --------------------------------------------------------------------------- #


class TestDownTimeGanttRowAttribution:
    def test_scoped_ticket_appears_only_on_its_own_row(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        # A sibling workstation on the same line, with no ticket of its own.
        sibling = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            production_line_id=line["id"],
            uap_id=uap["id"],
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        station_ids = [w["workstation_id"] for w in data["work_stations"]]
        line_ids = [l["line_id"] for l in data["lines"]]
        uap_ids = [u["uap_id"] for u in data["uaps"]]
        assert station["id"] in station_ids
        assert sibling["id"] not in station_ids
        assert line["id"] not in line_ids
        assert uap["id"] not in uap_ids

    def test_plant_ticket_spreads_over_dominant_level_uaps(
        self, client, seed_user, auth_headers, fake_db, seed_uap
    ):
        """More than one UAP in the namespace -> a `plant` ticket is spread
        over every UAP (the dashboard's `by_location` dominant-level rule)."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        uap1 = seed_uap(namespace_id=NS)
        uap2 = seed_uap(namespace_id=NS)
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        uap_ids = {u["uap_id"] for u in res.json()["data"]["uaps"]}
        assert uap_ids == {uap1["id"], uap2["id"]}

    def test_plant_ticket_spread_excludes_archived_resources(
        self, client, seed_user, auth_headers, fake_db, seed_uap
    ):
        """§2.4 (review finding W3): the plant-wide spread covers ACTIVE
        resources only — an archived UAP must not receive a bar for a
        plant-wide ticket it never lived through. Three UAPs (two active,
        one archived) so the active count alone is still > 1, keeping the
        dominant-level pick at "UAPs" regardless of whether it counts
        active or total resources. Does not contradict §2.6: an archived
        resource's OWN ticket still appears — see
        test_archived_resource_still_included_with_stored_name."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        active_uap_1 = seed_uap(namespace_id=NS)
        active_uap_2 = seed_uap(namespace_id=NS)
        archived_uap = seed_uap(namespace_id=NS)
        owner = _user(seed_user, Role.OWNER.value)
        archive_res = client.delete(
            f"/uaps/{archived_uap['id']}", headers=auth_headers(owner)
        )
        assert archive_res.status_code == 200, archive_res.text
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(owner)
        )
        assert res.status_code == 200, res.text
        uap_ids = {u["uap_id"] for u in res.json()["data"]["uaps"]}
        assert uap_ids == {active_uap_1["id"], active_uap_2["id"]}

    def test_plant_ticket_spreads_over_lines_when_single_uap(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line
    ):
        """Exactly one UAP but more than one line -> spreads over lines."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        uap = seed_uap(namespace_id=NS)
        line1 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        line2 = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(caller)
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["uaps"] == []
        line_ids = {l["line_id"] for l in data["lines"]}
        assert line_ids == {line1["id"], line2["id"]}


# --------------------------------------------------------------------------- #
# Filters and visibility (§2.5)
# --------------------------------------------------------------------------- #


class TestDownTimeGanttFilters:
    """§2.5 rev2 — `type` switches to a workstation-only view: `uaps`/`lines`
    always come back empty, `work_stations` holds every matching-type
    station of the namespace (wherever it hangs), and ancestor downtime
    (station/line/uap/plant) propagates down onto it as a union, unlike the
    unfiltered §2.4 rule."""

    def test_type_filter_returns_empty_uaps_and_lines(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Even when the namespace has UAP/line-scoped tickets that would
        populate `uaps`/`lines` in the unfiltered view, supplying `type`
        forces both to empty — the question asked no longer concerns them."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        seed_workstation(namespace_id=NS, production_line_id=line["id"], type=WorkstationType.BOTTLENECK.value)
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=uap["id"],
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        _seed_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            uap_id=uap["id"],
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL,
            params={"day": "2026-01-15", "type": "bottleneck"},
            headers=auth_headers(caller),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["uaps"] == []
        assert data["lines"] == []

    def test_type_filter_includes_matching_stations_wherever_nested(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Matching-type stations of the whole namespace are returned
        regardless of how they hang: nested under a line, or standalone
        (no `production_line_id` at all). Non-matching types are excluded."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        nested_bottleneck = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=WorkstationType.BOTTLENECK.value
        )
        standalone_bottleneck = seed_workstation(
            namespace_id=NS, production_line_id=None, type=WorkstationType.BOTTLENECK.value
        )
        standard = seed_workstation(namespace_id=NS, type=WorkstationType.STANDARD.value)
        for station in (nested_bottleneck, standalone_bottleneck, standard):
            _seed_issue(
                fake_db,
                down_time_scope="work station",
                workstation_id=station["id"],
                created_at=_paris(15, 8),
                resolved_at=_paris(15, 9),
                status=DownTimeStatus.RESOLVED.value,
            )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL,
            params={"day": "2026-01-15", "type": "bottleneck"},
            headers=auth_headers(caller),
        )
        assert res.status_code == 200, res.text
        station_ids = {w["workstation_id"] for w in res.json()["data"]["work_stations"]}
        assert station_ids == {nested_bottleneck["id"], standalone_bottleneck["id"]}

    def test_type_filter_propagates_station_scoped_ticket(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=WorkstationType.BOTTLENECK.value
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            production_line_id=line["id"],
            uap_id=uap["id"],
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL,
            params={"day": "2026-01-15", "type": "bottleneck"},
            headers=auth_headers(caller),
        )
        assert res.status_code == 200, res.text
        row = next(w for w in res.json()["data"]["work_stations"] if w["workstation_id"] == station["id"])
        assert {"start_time": _paris(15, 8), "end_time": _paris(15, 9), "state": "down"} in row["down_times"]

    def test_type_filter_propagates_line_scoped_ticket(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """A line-scoped ticket must propagate onto its matching-type
        workstation — a bottleneck whose line is stopped IS unavailable."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=WorkstationType.BOTTLENECK.value
        )
        _seed_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            uap_id=uap["id"],
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL,
            params={"day": "2026-01-15", "type": "bottleneck"},
            headers=auth_headers(caller),
        )
        assert res.status_code == 200, res.text
        row = next(w for w in res.json()["data"]["work_stations"] if w["workstation_id"] == station["id"])
        assert {"start_time": _paris(15, 8), "end_time": _paris(15, 9), "state": "down"} in row["down_times"]

    def test_type_filter_propagates_uap_scoped_ticket(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=WorkstationType.BOTTLENECK.value
        )
        _seed_issue(
            fake_db,
            down_time_scope="uap",
            uap_id=uap["id"],
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL,
            params={"day": "2026-01-15", "type": "bottleneck"},
            headers=auth_headers(caller),
        )
        assert res.status_code == 200, res.text
        row = next(w for w in res.json()["data"]["work_stations"] if w["workstation_id"] == station["id"])
        assert {"start_time": _paris(15, 8), "end_time": _paris(15, 9), "state": "down"} in row["down_times"]

    def test_type_filter_propagates_plant_scoped_ticket(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """Unlike §2.4's "spread over the dominant location level", the
        plant ticket here is unioned directly onto every matching station,
        regardless of the namespace's dominant level."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=WorkstationType.BOTTLENECK.value
        )
        _seed_issue(
            fake_db,
            down_time_scope="plant",
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL,
            params={"day": "2026-01-15", "type": "bottleneck"},
            headers=auth_headers(caller),
        )
        assert res.status_code == 200, res.text
        row = next(w for w in res.json()["data"]["work_stations"] if w["workstation_id"] == station["id"])
        assert {"start_time": _paris(15, 8), "end_time": _paris(15, 9), "state": "down"} in row["down_times"]

    def test_type_filter_merges_overlapping_sources_per_state(
        self, client, seed_user, auth_headers, fake_db, seed_uap, seed_production_line, seed_workstation
    ):
        """The station-scoped ticket (created 08:00, resolved 09:00, never
        closed) contributes `down` 08:00-09:00 AND an open-ended
        `unconfirmed` tail 09:00-window.end (14:00, §2.3 "never closed").
        The line-scoped ticket (created 08:30, resolved 09:30, closed
        10:00) contributes `down` 08:30-09:30 and `unconfirmed` 09:30-10:00.
        Unioned onto the matching station and merged per state (§2.3/§2.5):
        `down` = 08:00-09:30 (the two `down` spans merge, touching/
        overlapping at 08:30-09:00); `unconfirmed` unions to 09:00-14:00,
        then has the `down` overlap (08:00-09:30) subtracted, leaving
        09:30-14:00."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(
            namespace_id=NS, production_line_id=line["id"], type=WorkstationType.BOTTLENECK.value
        )
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            production_line_id=line["id"],
            uap_id=uap["id"],
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        _seed_issue(
            fake_db,
            down_time_scope="production line",
            production_line_id=line["id"],
            uap_id=uap["id"],
            created_at=_paris(15, 8, 30),
            resolved_at=_paris(15, 9, 30),
            closed_at=_paris(15, 10),
            status=DownTimeStatus.CLOSED.value,
        )
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL,
            params={"day": "2026-01-15", "type": "bottleneck"},
            headers=auth_headers(caller),
        )
        assert res.status_code == 200, res.text
        row = next(w for w in res.json()["data"]["work_stations"] if w["workstation_id"] == station["id"])
        down_segments = [dt for dt in row["down_times"] if dt["state"] == "down"]
        unconfirmed_segments = [dt for dt in row["down_times"] if dt["state"] == "unconfirmed"]
        assert down_segments == [
            {"start_time": _paris(15, 8), "end_time": _paris(15, 9, 30), "state": "down"}
        ]
        assert unconfirmed_segments == [
            {"start_time": _paris(15, 9, 30), "end_time": _paris(15, 14), "state": "unconfirmed"}
        ]

    def test_type_filter_matching_station_with_no_interval_is_absent(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        station = seed_workstation(namespace_id=NS, type=WorkstationType.BOTTLENECK.value)
        caller = _user(seed_user, Role.OWNER.value)
        res = client.get(
            GANTT_URL,
            params={"day": "2026-01-15", "type": "bottleneck"},
            headers=auth_headers(caller),
        )
        assert res.status_code == 200, res.text
        station_ids = [w["workstation_id"] for w in res.json()["data"]["work_stations"]]
        assert station["id"] not in station_ids

    def test_archived_matching_station_still_included_with_type_filter(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        """§2.6 under the `type` filter too: an archived matching station
        that was down that day must still be drawn."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        station = seed_workstation(namespace_id=NS, name="Press 9", type=WorkstationType.CRITICAL.value)
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        owner = _user(seed_user, Role.OWNER.value)
        archive_res = client.delete(f"/workstations/{station['id']}", headers=auth_headers(owner))
        assert archive_res.status_code == 200, archive_res.text

        res = client.get(
            GANTT_URL,
            params={"day": "2026-01-15", "type": "critical"},
            headers=auth_headers(owner),
        )
        assert res.status_code == 200, res.text
        row = next(
            (w for w in res.json()["data"]["work_stations"] if w["workstation_id"] == station["id"]),
            None,
        )
        assert row is not None
        assert row["name"] == "Press 9"

    def test_archived_resource_still_included_with_stored_name(
        self, client, seed_user, auth_headers, fake_db, seed_workstation
    ):
        """Unlike `GET /down-times`, the gantt is a KPI-style read: an
        archived resource that was down that day must still be drawn."""
        _seed_settings(
            fake_db, shift_number=1, shift_1={"start_time": "06:00", "end_time": "14:00"}
        )
        station = seed_workstation(namespace_id=NS, name="Press 7")
        _seed_issue(
            fake_db,
            down_time_scope="work station",
            workstation_id=station["id"],
            created_at=_paris(15, 8),
            resolved_at=_paris(15, 9),
            status=DownTimeStatus.RESOLVED.value,
        )
        owner = _user(seed_user, Role.OWNER.value)
        archive_res = client.delete(
            f"/workstations/{station['id']}", headers=auth_headers(owner)
        )
        assert archive_res.status_code == 200, archive_res.text

        res = client.get(
            GANTT_URL, params={"day": "2026-01-15"}, headers=auth_headers(owner)
        )
        assert res.status_code == 200, res.text
        row = next(
            (w for w in res.json()["data"]["work_stations"] if w["workstation_id"] == station["id"]),
            None,
        )
        assert row is not None
        assert row["name"] == "Press 7"
