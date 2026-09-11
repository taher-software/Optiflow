"""API tests: downtime tickets whose resource has been archived must stop
showing up as work to do.

Covers `list_down_times`, `get_down_time_summary` and `get_down_time`
(`src/app/routers/down_time/services.py`) together with the shared
`is_active` predicate (`src/app/core/archiving.py`). None of this filtering
exists yet — `_fetch_visible_issues` / `list_down_times` /
`get_down_time_summary` only filter by namespace, role-process visibility and
status today (see the module under test) — so every assertion below is
expected to fail on its own assertion (an archived-resource ticket still
showing up, or a pagination/summary count that still includes it), never on a
broken fixture.

Scope, per the Work Unit brief:
- Hidden everywhere, web included: one behaviour for every caller, no
  `include_archived` parameter, no role-dependent filtering.
- `GET /down-times/{id}` is the one deliberate exception and keeps returning
  the ticket even when its resource is archived.
- The filter must resolve the resource the way the rest of the code does
  (following the UAP -> production line -> workstation cascade already
  implemented by `DELETE /uaps/{id}` / `DELETE /production-lines/{id}`, see
  the frozen `tests/api/test_resource_archiving.py`), not just read the
  workstation document directly.
- `total` / pagination and the summary counts must stay consistent with the
  rows actually returned — a filter applied only to rows (not to `total`)
  yields short pages; a filter missed in the summary shows stale counts.
- The resources needed to resolve archived state must be read in a bounded
  number of Firestore calls, not one per ticket.

Archiving itself (cascade, idempotence, role/tenant guards) is already
implemented and covered by the frozen `test_resource_archiving.py` — this
suite exercises it only through the real `DELETE` endpoints, as a black box,
to get a resource into the archived state.

No real Firestore/network is touched — `get_firestore_client()` is
monkeypatched to an in-memory fake via `tests/conftest.py::fake_db`. Ticket
timestamps are built with fixed, explicit offsets (`_iso`), not frozen
wall-clock time, since only relative ordering (newest first) matters here.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.app.routers.down_time import services as down_time_services_module
from src.app.globals.enum import Role

NS = "ns-archived-resource-exclusion"

DOWN_TIMES_URL = "/down-times"
UAPS_URL = "/uaps"
PRODUCTION_LINES_URL = "/production-lines"
WORKSTATIONS_URL = "/workstations"

# A role NOT granted full namespace visibility (mirrors test_down_time_lifecycle.py) —
# used to prove the exclusion is not tangled up with process-visibility filtering.
PROCESS_SCOPED_ROLE = Role.MAINTENANCE_AGENT.value


def _iso(minutes_ago=0):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def _owner(seed_user, **overrides):
    overrides.setdefault("namespace_id", NS)
    overrides.setdefault("role", Role.OWNER.value)
    return seed_user(**overrides)


@pytest.fixture
def seed_issue(fake_db):
    """Seed an issue document directly into down_time/{NS}/issues/{id} —
    mirrors `tests/api/test_down_time_lifecycle.py::seed_issue`."""

    def _seed(issue_id, **fields):
        doc = {
            "id": issue_id,
            "namespace_id": NS,
            "created_at": _iso(30),
            "updated_at": _iso(30),
            "down_time_scope": "plant",
            "uap_id": None,
            "production_line_id": None,
            "workstation_id": None,
            "down_time_type": "break down",
            "department": None,
            "process": "maintenance",
            "status": "pending",
            "created_by": "opener",
        }
        doc.update(fields)
        (
            fake_db.collection("down_time")
            .document(NS)
            .collection("issues")
            .document(issue_id)
            .set(doc)
        )
        return doc

    return _seed


@pytest.fixture
def archive(client, seed_user, auth_headers):
    """archive(url, resource_id) -> response. Archives through the real
    endpoint (DELETE), re-using the already-implemented/frozen archiving
    mechanics rather than re-deriving them here."""
    owner = _owner(seed_user, id="owner-" + NS)

    def _archive(url, resource_id):
        return client.delete(f"{url}/{resource_id}", headers=auth_headers(owner))

    return _archive


# --------------------------------------------------------------------------- #
# Lists: archived-resource tickets are absent
# --------------------------------------------------------------------------- #


class TestListExcludesArchivedResourceTickets:
    """GET /down-times must not return a ticket whose resource is archived."""

    def test_ticket_on_archived_workstation_is_absent(
        self, client, seed_user, seed_production_line, seed_workstation,
        seed_issue, auth_headers, archive,
    ):
        caller = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        line = seed_production_line(namespace_id=NS, uap_id=None)
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        seed_issue(
            "t-archived-station",
            down_time_scope="work station",
            production_line_id=line["id"],
            workstation_id=station["id"],
        )

        archive(WORKSTATIONS_URL, station["id"])

        res = client.get(DOWN_TIMES_URL, headers=auth_headers(caller))
        assert res.status_code == 200
        assert "t-archived-station" not in {
            i["id"] for i in res.json()["data"]["items"]
        }

    def test_ticket_on_workstation_cascade_archived_via_its_line_is_absent(
        self, client, seed_user, seed_production_line, seed_workstation,
        seed_issue, auth_headers, archive,
    ):
        caller = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        line = seed_production_line(namespace_id=NS, uap_id=None)
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        seed_issue(
            "t-cascade-line",
            down_time_scope="work station",
            production_line_id=line["id"],
            workstation_id=station["id"],
        )

        # The workstation itself is never archived directly — only its line is.
        archive(PRODUCTION_LINES_URL, line["id"])

        res = client.get(DOWN_TIMES_URL, headers=auth_headers(caller))
        assert res.status_code == 200
        assert "t-cascade-line" not in {
            i["id"] for i in res.json()["data"]["items"]
        }

    def test_ticket_on_workstation_cascade_archived_via_its_uap_is_absent(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation,
        seed_issue, auth_headers, archive,
    ):
        caller = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        seed_issue(
            "t-cascade-uap",
            down_time_scope="work station",
            uap_id=uap["id"],
            production_line_id=line["id"],
            workstation_id=station["id"],
        )

        # Two levels up: only the UAP is archived directly.
        archive(UAPS_URL, uap["id"])

        res = client.get(DOWN_TIMES_URL, headers=auth_headers(caller))
        assert res.status_code == 200
        assert "t-cascade-uap" not in {
            i["id"] for i in res.json()["data"]["items"]
        }

    def test_ticket_on_archived_uap_scope_is_absent(
        self, client, seed_user, seed_uap, seed_issue, auth_headers, archive,
    ):
        caller = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        uap = seed_uap(namespace_id=NS)
        seed_issue("t-uap-scope", down_time_scope="uap", uap_id=uap["id"])

        archive(UAPS_URL, uap["id"])

        res = client.get(DOWN_TIMES_URL, headers=auth_headers(caller))
        assert res.status_code == 200
        assert "t-uap-scope" not in {i["id"] for i in res.json()["data"]["items"]}

    def test_ticket_on_archived_production_line_scope_is_absent(
        self, client, seed_user, seed_production_line, seed_issue, auth_headers, archive,
    ):
        caller = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        line = seed_production_line(namespace_id=NS, uap_id=None)
        seed_issue(
            "t-line-scope", down_time_scope="production line",
            production_line_id=line["id"],
        )

        archive(PRODUCTION_LINES_URL, line["id"])

        res = client.get(DOWN_TIMES_URL, headers=auth_headers(caller))
        assert res.status_code == 200
        assert "t-line-scope" not in {i["id"] for i in res.json()["data"]["items"]}

    def test_plant_scope_ticket_is_never_hidden(
        self, client, seed_user, seed_issue, auth_headers,
    ):
        """A plant-scope ticket carries no resource id at all, so there is
        nothing to resolve/archive — it must never be swept into the
        exclusion by an overly broad implementation."""
        caller = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        seed_issue("t-plant-scope", down_time_scope="plant")

        res = client.get(DOWN_TIMES_URL, headers=auth_headers(caller))
        assert res.status_code == 200
        assert "t-plant-scope" in {i["id"] for i in res.json()["data"]["items"]}

    def test_tickets_on_active_resources_are_returned_as_today(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation,
        seed_issue, auth_headers,
    ):
        """Non-regression: nothing archived in this scenario, every ticket
        (at every scope) still comes back exactly like today."""
        caller = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        seed_issue("t-active-plant", down_time_scope="plant")
        seed_issue("t-active-uap", down_time_scope="uap", uap_id=uap["id"])
        seed_issue(
            "t-active-line", down_time_scope="production line",
            uap_id=uap["id"], production_line_id=line["id"],
        )
        seed_issue(
            "t-active-station", down_time_scope="work station",
            uap_id=uap["id"], production_line_id=line["id"], workstation_id=station["id"],
        )

        res = client.get(DOWN_TIMES_URL, headers=auth_headers(caller))
        assert res.status_code == 200
        assert {i["id"] for i in res.json()["data"]["items"]} == {
            "t-active-plant", "t-active-uap", "t-active-line", "t-active-station",
        }


# --------------------------------------------------------------------------- #
# Pagination: total + page length stay consistent with the hidden tickets
# --------------------------------------------------------------------------- #


class TestListPaginationWithHiddenTickets:
    """GET /down-times?limit=&offset= — `total` and page contents must both
    reflect only visible (non-archived-resource) tickets, even when hidden
    tickets sit interleaved among them in storage order."""

    def _seed_interleaved(
        self, seed_user, seed_production_line, seed_workstation, seed_issue, archive,
    ):
        caller = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        active_line = seed_production_line(namespace_id=NS, uap_id=None)
        active_station = seed_workstation(
            namespace_id=NS, production_line_id=active_line["id"]
        )
        hidden_line = seed_production_line(namespace_id=NS, uap_id=None)
        hidden_station = seed_workstation(
            namespace_id=NS, production_line_id=hidden_line["id"]
        )
        archive(WORKSTATIONS_URL, hidden_station["id"])

        # Newest (i=0) -> oldest (i=5): t0, t2, t4, t5 visible; t1, t3 hidden —
        # interleaved, not grouped, so a naive "filter after slicing"
        # implementation produces a short page.
        for i, visible in enumerate([True, False, True, False, True, True]):
            station = active_station if visible else hidden_station
            seed_issue(
                f"t{i}",
                down_time_scope="work station",
                workstation_id=station["id"],
                created_at=_iso(i),
            )
        return caller

    def test_total_counts_only_visible_tickets(
        self, client, seed_user, seed_production_line, seed_workstation,
        seed_issue, auth_headers, archive,
    ):
        caller = self._seed_interleaved(
            seed_user, seed_production_line, seed_workstation, seed_issue, archive
        )
        res = client.get(DOWN_TIMES_URL, headers=auth_headers(caller))
        assert res.status_code == 200
        assert res.json()["data"]["total"] == 4

    def test_page_is_full_length_despite_interleaved_hidden_tickets(
        self, client, seed_user, seed_production_line, seed_workstation,
        seed_issue, auth_headers, archive,
    ):
        caller = self._seed_interleaved(
            seed_user, seed_production_line, seed_workstation, seed_issue, archive
        )
        res = client.get(
            f"{DOWN_TIMES_URL}?limit=3&offset=0", headers=auth_headers(caller)
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert [i["id"] for i in data["items"]] == ["t0", "t2", "t4"]

    def test_paging_to_the_end_terminates_correctly(
        self, client, seed_user, seed_production_line, seed_workstation,
        seed_issue, auth_headers, archive,
    ):
        caller = self._seed_interleaved(
            seed_user, seed_production_line, seed_workstation, seed_issue, archive
        )
        res = client.get(
            f"{DOWN_TIMES_URL}?limit=3&offset=3", headers=auth_headers(caller)
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert [i["id"] for i in data["items"]] == ["t5"]
        assert data["total"] == 4


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #


class TestSummaryExcludesArchivedResourceTickets:
    def test_summary_counts_exclude_archived_resource_tickets(
        self, client, seed_user, seed_production_line, seed_workstation,
        seed_issue, auth_headers, archive,
    ):
        caller = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        active_line = seed_production_line(namespace_id=NS, uap_id=None)
        active_station = seed_workstation(
            namespace_id=NS, production_line_id=active_line["id"]
        )
        hidden_line = seed_production_line(namespace_id=NS, uap_id=None)
        hidden_station = seed_workstation(
            namespace_id=NS, production_line_id=hidden_line["id"]
        )
        archive(WORKSTATIONS_URL, hidden_station["id"])

        seed_issue(
            "visible-pending", status="pending",
            workstation_id=active_station["id"], down_time_scope="work station",
        )
        seed_issue(
            "hidden-pending", status="pending",
            workstation_id=hidden_station["id"], down_time_scope="work station",
        )
        seed_issue(
            "hidden-ongoing", status="ongoing",
            workstation_id=hidden_station["id"], down_time_scope="work station",
            acknowledged_at=_iso(5),
        )

        res = client.get(f"{DOWN_TIMES_URL}/summary", headers=auth_headers(caller))
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["pending"]["count"] == 1
        assert data["ongoing"]["count"] == 0

    def test_summary_agrees_with_the_list_for_the_same_data(
        self, client, seed_user, seed_production_line, seed_workstation,
        seed_issue, auth_headers, archive,
    ):
        caller = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        active_line = seed_production_line(namespace_id=NS, uap_id=None)
        active_station = seed_workstation(
            namespace_id=NS, production_line_id=active_line["id"]
        )
        hidden_line = seed_production_line(namespace_id=NS, uap_id=None)
        hidden_station = seed_workstation(
            namespace_id=NS, production_line_id=hidden_line["id"]
        )
        archive(WORKSTATIONS_URL, hidden_station["id"])

        for i in range(3):
            seed_issue(
                f"visible-{i}", status="pending",
                workstation_id=active_station["id"], down_time_scope="work station",
                created_at=_iso(i),
            )
        for i in range(2):
            seed_issue(
                f"hidden-{i}", status="pending",
                workstation_id=hidden_station["id"], down_time_scope="work station",
                created_at=_iso(i),
            )

        list_res = client.get(DOWN_TIMES_URL, headers=auth_headers(caller))
        summary_res = client.get(f"{DOWN_TIMES_URL}/summary", headers=auth_headers(caller))
        assert list_res.status_code == 200
        assert summary_res.status_code == 200
        assert list_res.json()["data"]["total"] == 3
        assert summary_res.json()["data"]["pending"]["count"] == 3


# --------------------------------------------------------------------------- #
# Single read: the one deliberate exception
# --------------------------------------------------------------------------- #


class TestSingleReadStillWorksOnArchivedResource:
    def test_get_down_time_returns_200_for_a_ticket_on_an_archived_workstation(
        self, client, seed_user, seed_production_line, seed_workstation,
        seed_issue, auth_headers, archive,
    ):
        """A deep link / push notification sent just before the archive must
        not open an error screen: GET /down-times/{id} keeps working even
        though the same ticket is now excluded from the list and summary."""
        caller = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)
        line = seed_production_line(namespace_id=NS, uap_id=None)
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        seed_issue(
            "t-deep-link", down_time_scope="work station",
            production_line_id=line["id"], workstation_id=station["id"],
        )

        archive(WORKSTATIONS_URL, station["id"])

        res = client.get(f"{DOWN_TIMES_URL}/t-deep-link", headers=auth_headers(caller))
        assert res.status_code == 200
        assert res.json()["data"]["id"] == "t-deep-link"


# --------------------------------------------------------------------------- #
# Role independence — no role-dependent filtering
# --------------------------------------------------------------------------- #


class TestExclusionIsRoleIndependent:
    @pytest.mark.parametrize(
        "role",
        [Role.MAINTENANCE_AGENT.value, Role.OWNER.value, Role.ADMIN.value],
    )
    def test_ticket_on_archived_resource_is_hidden_for_every_role(
        self, client, seed_user, seed_production_line, seed_workstation,
        seed_issue, auth_headers, archive, role,
    ):
        caller = seed_user(namespace_id=NS, role=role)
        line = seed_production_line(namespace_id=NS, uap_id=None)
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        seed_issue(
            "t-role-independent", down_time_scope="work station",
            process="maintenance", production_line_id=line["id"],
            workstation_id=station["id"],
        )

        archive(WORKSTATIONS_URL, station["id"])

        res = client.get(DOWN_TIMES_URL, headers=auth_headers(caller))
        assert res.status_code == 200
        assert "t-role-independent" not in {
            i["id"] for i in res.json()["data"]["items"]
        }


# --------------------------------------------------------------------------- #
# Performance: resolving archived state must not cost one read per ticket
# --------------------------------------------------------------------------- #


@pytest.fixture
def firestore_read_counter(fake_db, monkeypatch):
    """Counts calls (not documents) to the Firestore round-trip methods the
    down_time services module could use to resolve a ticket's resource:
    `get_document` (single), `get_documents` (batched-by-ids, one round trip
    regardless of how many ids) and `find_documents` (collection scan, also
    one round trip). Patches the SAME `FirestoreClient` instance
    `down_time_services_module.get_firestore_client()` already returns (wired
    by the `fake_db` fixture), so every call the module makes is captured."""
    dt_client = down_time_services_module.get_firestore_client()
    counts = {"get_document": 0, "get_documents": 0, "find_documents": 0}

    for name in counts:
        original = getattr(dt_client, name)

        def _make_counting(name, original):
            def _counting(*args, **kwargs):
                counts[name] += 1
                return original(*args, **kwargs)

            return _counting

        monkeypatch.setattr(dt_client, name, _make_counting(name, original))

    return counts


class TestArchivedResourceResolutionIsBounded:
    def test_list_down_times_does_not_read_once_per_ticket(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation,
        seed_issue, auth_headers, firestore_read_counter,
    ):
        caller = seed_user(namespace_id=NS, role=Role.PRODUCTION_AGENT.value)

        # Only a handful of DISTINCT resources...
        uaps = [seed_uap(namespace_id=NS) for _ in range(3)]
        lines = [
            seed_production_line(namespace_id=NS, uap_id=uaps[i]["id"])
            for i in range(3)
        ]
        stations = [
            seed_workstation(namespace_id=NS, production_line_id=lines[i]["id"])
            for i in range(3)
        ]

        # ...referenced by MANY tickets. A per-ticket lookup would cost one
        # extra read per ticket on top of whatever fetches the issues
        # themselves; a bounded implementation costs a small, fixed number of
        # calls regardless of how many tickets exist.
        ticket_count = 60
        for i in range(ticket_count):
            station = stations[i % 3]
            line = lines[i % 3]
            uap = uaps[i % 3]
            seed_issue(
                f"t-bulk-{i}",
                down_time_scope="work station",
                uap_id=uap["id"],
                production_line_id=line["id"],
                workstation_id=station["id"],
                created_at=_iso(i),
            )

        res = client.get(DOWN_TIMES_URL, headers=auth_headers(caller))
        assert res.status_code == 200

        total_reads = sum(firestore_read_counter.values())
        assert total_reads < ticket_count, (
            f"list_down_times made {total_reads} Firestore round-trips for "
            f"{ticket_count} tickets referencing only 9 distinct resources — "
            "looks like one read per ticket instead of a bounded resolution."
        )
