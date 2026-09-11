"""API tests for CORE resource-archiving mechanics: `DELETE /uaps/{id}`,
`DELETE /production-lines/{id}`, `DELETE /workstations/{id}`.

This is the Work Unit `test.resource_archiving_core` suite — written
test-first, BEFORE the archiving implementation exists. The three hard
`DELETE` endpoints on UAP / production line / workstation
(`src/app/routers/{uap,production_line,workstation}/{__init__,services}.py`)
are replaced by archiving: the document is never removed, it gets an
`archived_at` ISO-8601 timestamp (see `down_time`'s timestamp convention for
the string format) and is excluded from every list/read from then on. There
is no unarchive endpoint. The same path/verb (`DELETE`) and the same role
restrictions as today's hard-delete endpoints are kept.

Scope boundary: this suite covers archiving MECHANICS only — endpoints,
cascade, visibility, guards, tenant isolation. KPI behaviour (bounded
downtime, MTTR, breakdown rows, ticket weighting) is a SEPARATE Work Unit
and is deliberately NOT exercised here; no `/kpi/dashboard` assertions
appear in this file.

Cascade rules under test (see the Work Unit brief):
- Archiving a UAP archives the UAP, every production line whose `uap_id` is
  that UAP, and every workstation whose `production_line_id` is one of
  those lines.
- Archiving a production line archives the line and every workstation whose
  `production_line_id` is that line.
- Archiving a workstation archives only that workstation.
- Independent lines/workstations (no `uap_id` / no `production_line_id`)
  are never swept into a cascade that does not target them directly.
- Every resource archived within one cascade call gets the exact same
  `archived_at` value.
- Children keep their parent id references unchanged (nothing is detached).

Guards under test:
- Re-archiving an already-archived resource must not overwrite the original
  `archived_at` (idempotence).
- Creating a downtime ticket that targets an archived workstation is
  rejected.
- Creating/updating a resource so it points at an archived parent (a new
  line under an archived UAP, a workstation (re)pointed at an archived
  line) is rejected.
- Cross-namespace archiving returns 404, exactly like the current hard
  deletes.
- The former delete endpoints' role restrictions (owner/admin/production
  supervisor) still apply.

Because none of this exists yet in `src/`, every test below is expected to
fail on its own assertion (usually the endpoint still hard-deleting, or the
missing `archived_at`/rejection behavior) rather than on a broken fixture —
see the hand-back notes for the one-line reason per test.

No real Firestore/network is touched — `get_firestore_client()` is
monkeypatched to an in-memory fake (see `tests/conftest.py::fake_db`).
`freezegun` is not installed; the "one cascade, one timestamp" scenario is
verified by reading the *same* stored value back for every cascaded
document, not by pinning wall-clock time.
"""

from src.app.core.firestore import (
    PRODUCTION_LINE_COLLECTION,
    UAP_COLLECTION,
    WORKSTATION_COLLECTION,
)
from src.app.globals.enum import DownTimeType, ProductionScope, Role

from tests.factories.production_line import ProductionLinePayloadFactory
from tests.factories.workstation import WorkstationPayloadFactory

UAPS_URL = "/uaps"
PRODUCTION_LINES_URL = "/production-lines"
WORKSTATIONS_URL = "/workstations"
DOWN_TIMES_URL = "/down-times"

# A role NOT permitted to manage/archive these resources, used for 403 tests
# — mirrors FORBIDDEN_ROLE in test_uap.py / test_production_line.py /
# test_workstation.py.
FORBIDDEN_ROLE = Role.MAINTENANCE_AGENT.value

NS = "ns-archiving"


def _owner(seed_user, **overrides):
    overrides.setdefault("namespace_id", NS)
    overrides.setdefault("role", Role.OWNER.value)
    return seed_user(**overrides)


def _agent(seed_user, **overrides):
    """A production agent, the role allowed to declare downtime tickets."""
    overrides.setdefault("namespace_id", NS)
    overrides.setdefault("role", Role.PRODUCTION_AGENT.value)
    return seed_user(**overrides)


def _doc(fake_db, collection: str, doc_id: str) -> dict:
    """Read a document back as a dict. Returns `{}` (never `None`) when the
    document is missing, so `_doc(...).get("archived_at")` reads cleanly as
    falsy/`None` on a missing document instead of raising `TypeError` —
    relevant today because the pre-archiving implementation still
    hard-`DELETE`s the document."""
    snapshot = fake_db.collection(collection).document(doc_id).get().to_dict()
    return snapshot if snapshot is not None else {}


# ---------------------------------------------------------------------------
# Cascade
# ---------------------------------------------------------------------------


class TestArchiveUapCascade:
    """DELETE /uaps/{uap_id} — cascades to lines and workstations."""

    def test_archive_uap_archives_lines_and_workstations(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])

        response = client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        assert response.status_code == 200
        assert _doc(fake_db, UAP_COLLECTION, uap["id"]).get("archived_at")
        assert _doc(fake_db, PRODUCTION_LINE_COLLECTION, line["id"]).get("archived_at")
        assert _doc(fake_db, WORKSTATION_COLLECTION, station["id"]).get("archived_at")

    def test_archive_uap_does_not_touch_an_independent_line(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        auth_headers,
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        independent_line = seed_production_line(namespace_id=NS, uap_id=None)

        response = client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        assert response.status_code == 200
        stored = _doc(fake_db, PRODUCTION_LINE_COLLECTION, independent_line["id"])
        assert not stored.get("archived_at")

    def test_archive_uap_does_not_touch_an_independent_workstation(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        seed_production_line(namespace_id=NS, uap_id=uap["id"])
        independent_station = seed_workstation(namespace_id=NS, production_line_id=None)

        response = client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        assert response.status_code == 200
        stored = _doc(fake_db, WORKSTATION_COLLECTION, independent_station["id"])
        assert not stored.get("archived_at")

    def test_archive_uap_cascade_shares_one_timestamp(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])

        client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        uap_ts = _doc(fake_db, UAP_COLLECTION, uap["id"]).get("archived_at")
        line_ts = _doc(fake_db, PRODUCTION_LINE_COLLECTION, line["id"]).get("archived_at")
        station_ts = _doc(fake_db, WORKSTATION_COLLECTION, station["id"]).get("archived_at")
        assert uap_ts, "archive did not set archived_at"
        assert uap_ts == line_ts == station_ts

    def test_archive_uap_leaves_child_parent_references_intact(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])

        client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        assert _doc(fake_db, PRODUCTION_LINE_COLLECTION, line["id"])["uap_id"] == uap["id"]
        assert (
            _doc(fake_db, WORKSTATION_COLLECTION, station["id"])["production_line_id"]
            == line["id"]
        )

    def test_archive_uap_reports_cascaded_ids_in_response(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
    ):
        """The brief requires the response to 'report what was archived,
        including the cascade'. The exact response shape is left open by the
        contract, so this test checks the cascaded ids surface *somewhere*
        in the JSON body rather than binding to an undocumented field name.
        """
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])

        response = client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        assert response.status_code == 200
        body_text = response.text
        assert line["id"] in body_text
        assert station["id"] in body_text


class TestArchiveProductionLineCascade:
    """DELETE /production-lines/{line_id} — cascades to its workstations."""

    def test_archive_line_archives_its_workstations(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])

        response = client.delete(
            f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 200
        assert _doc(fake_db, PRODUCTION_LINE_COLLECTION, line["id"]).get("archived_at")
        assert _doc(fake_db, WORKSTATION_COLLECTION, station["id"]).get("archived_at")

    def test_archive_line_does_not_touch_an_independent_workstation(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        independent_station = seed_workstation(namespace_id=NS, production_line_id=None)

        response = client.delete(
            f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 200
        stored = _doc(fake_db, WORKSTATION_COLLECTION, independent_station["id"])
        assert not stored.get("archived_at")

    def test_archive_line_does_not_touch_a_workstation_on_another_line(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        other_line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        other_station = seed_workstation(namespace_id=NS, production_line_id=other_line["id"])

        response = client.delete(
            f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 200
        stored = _doc(fake_db, WORKSTATION_COLLECTION, other_station["id"])
        assert not stored.get("archived_at")

    def test_archive_line_leaves_workstation_parent_reference_intact(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])

        client.delete(f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner))

        assert (
            _doc(fake_db, WORKSTATION_COLLECTION, station["id"])["production_line_id"]
            == line["id"]
        )


class TestArchiveWorkstationAlone:
    """DELETE /workstations/{station_id} — archives only itself."""

    def test_archive_workstation_only_archives_itself(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        sibling = seed_workstation(namespace_id=NS, production_line_id=line["id"])

        response = client.delete(
            f"{WORKSTATIONS_URL}/{station['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 200
        assert _doc(fake_db, WORKSTATION_COLLECTION, station["id"]).get("archived_at")
        assert not _doc(fake_db, PRODUCTION_LINE_COLLECTION, line["id"]).get("archived_at")
        assert not _doc(fake_db, WORKSTATION_COLLECTION, sibling["id"]).get("archived_at")


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------


class TestArchiveVisibility:
    def test_archived_uap_is_gone_from_list(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        response = client.get(UAPS_URL, headers=auth_headers(owner))

        assert response.status_code == 200
        ids = [row["id"] for row in response.json()["data"]]
        assert uap["id"] not in ids

    def test_archived_uap_get_by_id_behaves_as_not_found(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        response = client.get(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        assert response.status_code == 404

    def test_archived_production_line_is_gone_from_list(
        self, client, seed_user, seed_production_line, auth_headers
    ):
        owner = _owner(seed_user)
        line = seed_production_line(namespace_id=NS, uap_id=None)
        client.delete(f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner))

        response = client.get(PRODUCTION_LINES_URL, headers=auth_headers(owner))

        assert response.status_code == 200
        ids = [row["id"] for row in response.json()["data"]]
        assert line["id"] not in ids

    def test_archived_production_line_get_by_id_behaves_as_not_found(
        self, client, seed_user, seed_production_line, auth_headers
    ):
        owner = _owner(seed_user)
        line = seed_production_line(namespace_id=NS, uap_id=None)
        client.delete(f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner))

        response = client.get(
            f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 404

    def test_archived_workstation_is_gone_from_list(
        self, client, seed_user, seed_workstation, auth_headers
    ):
        owner = _owner(seed_user)
        station = seed_workstation(namespace_id=NS, production_line_id=None)
        client.delete(f"{WORKSTATIONS_URL}/{station['id']}", headers=auth_headers(owner))

        response = client.get(WORKSTATIONS_URL, headers=auth_headers(owner))

        assert response.status_code == 200
        ids = [row["id"] for row in response.json()["data"]]
        assert station["id"] not in ids

    def test_archived_workstation_get_by_id_behaves_as_not_found(
        self, client, seed_user, seed_workstation, auth_headers
    ):
        owner = _owner(seed_user)
        station = seed_workstation(namespace_id=NS, production_line_id=None)
        client.delete(f"{WORKSTATIONS_URL}/{station['id']}", headers=auth_headers(owner))

        response = client.get(
            f"{WORKSTATIONS_URL}/{station['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 404

    def test_workstation_archived_by_cascade_is_gone_from_workstation_list(
        self,
        client,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])

        client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        response = client.get(WORKSTATIONS_URL, headers=auth_headers(owner))

        assert response.status_code == 200
        ids = [row["id"] for row in response.json()["data"]]
        assert station["id"] not in ids

    def test_resource_with_no_archived_at_key_at_all_is_still_listed(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation, auth_headers
    ):
        """The missing-field trap: `seed_*` fixtures write docs with no
        `archived_at` key at all (today's shape for every pre-existing
        document). A naive `where("archived_at", "==", None)` Firestore
        query would make these vanish; filtering must happen in Python."""
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        station = seed_workstation(namespace_id=NS, production_line_id=line["id"])
        assert "archived_at" not in uap
        assert "archived_at" not in line
        assert "archived_at" not in station

        uap_ids = [row["id"] for row in client.get(UAPS_URL, headers=auth_headers(owner)).json()["data"]]
        line_ids = [
            row["id"]
            for row in client.get(PRODUCTION_LINES_URL, headers=auth_headers(owner)).json()["data"]
        ]
        station_ids = [
            row["id"]
            for row in client.get(WORKSTATIONS_URL, headers=auth_headers(owner)).json()["data"]
        ]

        assert uap["id"] in uap_ids
        assert line["id"] in line_ids
        assert station["id"] in station_ids


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


class TestArchiveIdempotence:
    """A second archive of the same resource must not overwrite
    `archived_at`, and must not look like a failure to the caller.

    Open decision (flagged to the developer at the gate): this suite pins
    the re-archive response to `200` — the same status the first archive
    call returns — on the grounds that `DELETE` is conventionally
    idempotent in this codebase's other endpoints and the brief explicitly
    says a repeat archive "should not look like a failure to the caller".
    If the developer prefers `409` (conflicting state transition, the
    convention this codebase otherwise uses for illegal transitions) this
    single assertion is the only one that needs to change.
    """

    def test_rearchiving_a_uap_does_not_change_its_archived_at(
        self, client, fake_db, seed_user, seed_uap, auth_headers
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)

        first = client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))
        original_ts = _doc(fake_db, UAP_COLLECTION, uap["id"]).get("archived_at")
        assert original_ts, "first archive did not set archived_at"

        second = client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        assert first.status_code == 200
        assert second.status_code == 200
        assert _doc(fake_db, UAP_COLLECTION, uap["id"]).get("archived_at") == original_ts

    def test_rearchiving_a_production_line_does_not_change_its_archived_at(
        self, client, fake_db, seed_user, seed_production_line, auth_headers
    ):
        owner = _owner(seed_user)
        line = seed_production_line(namespace_id=NS, uap_id=None)

        client.delete(f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner))
        original_ts = _doc(fake_db, PRODUCTION_LINE_COLLECTION, line["id"]).get("archived_at")
        assert original_ts, "first archive did not set archived_at"

        second = client.delete(
            f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner)
        )

        assert second.status_code == 200
        assert (
            _doc(fake_db, PRODUCTION_LINE_COLLECTION, line["id"]).get("archived_at")
            == original_ts
        )

    def test_rearchiving_a_workstation_does_not_change_its_archived_at(
        self, client, fake_db, seed_user, seed_workstation, auth_headers
    ):
        owner = _owner(seed_user)
        station = seed_workstation(namespace_id=NS, production_line_id=None)

        client.delete(f"{WORKSTATIONS_URL}/{station['id']}", headers=auth_headers(owner))
        original_ts = _doc(fake_db, WORKSTATION_COLLECTION, station["id"]).get("archived_at")
        assert original_ts, "first archive did not set archived_at"

        second = client.delete(
            f"{WORKSTATIONS_URL}/{station['id']}", headers=auth_headers(owner)
        )

        assert second.status_code == 200
        assert (
            _doc(fake_db, WORKSTATION_COLLECTION, station["id"]).get("archived_at")
            == original_ts
        )


class TestTicketRejectedOnArchivedWorkstation:
    """POST /down-times must reject a ticket targeting an archived
    workstation. `create_down_time` already validates `workstation_id`
    existence/namespace with a `422` (`_validate_workstation` in
    `src/app/routers/down_time/services.py`); archiving is expected to be
    rejected at that same layer with the same status code, since it is the
    same kind of "this id does not resolve to a usable workstation" refusal.
    """

    def test_create_ticket_on_archived_workstation_returns_422(
        self, client, seed_user, seed_workstation, auth_headers, publish_spy
    ):
        agent = _agent(seed_user)
        station = seed_workstation(namespace_id=NS, production_line_id=None)
        client.delete(
            f"{WORKSTATIONS_URL}/{station['id']}",
            headers=auth_headers(_owner(seed_user)),
        )

        response = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.WORK_STATION.value,
                "workstation_id": station["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )

        assert response.status_code == 422
        assert len(publish_spy) == 0

    def test_create_ticket_on_active_workstation_still_succeeds(
        self, client, seed_user, seed_workstation, auth_headers, publish_spy
    ):
        """Non-regression companion to the rejection test above: an active
        (non-archived) workstation must still accept a ticket."""
        agent = _agent(seed_user)
        station = seed_workstation(namespace_id=NS, production_line_id=None)

        response = client.post(
            DOWN_TIMES_URL,
            headers=auth_headers(agent),
            json={
                "production_scope": ProductionScope.WORK_STATION.value,
                "workstation_id": station["id"],
                "down_time_type": DownTimeType.BREAKDOWN.value,
            },
        )

        assert response.status_code == 202
        assert len(publish_spy) == 1


class TestCreateOrUpdateAgainstArchivedParentRejected:
    """Creating/attaching a resource to an archived parent is rejected."""

    def test_create_production_line_under_archived_uap_returns_422(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        response = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(uap_id=uap["id"]),
            headers=auth_headers(owner),
        )

        assert response.status_code == 422

    def test_create_workstation_under_archived_line_returns_422(
        self, client, seed_user, seed_uap, seed_production_line, auth_headers
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        client.delete(f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner))

        response = client.post(
            WORKSTATIONS_URL,
            json=WorkstationPayloadFactory(production_line_id=line["id"]),
            headers=auth_headers(owner),
        )

        assert response.status_code == 422

    def test_update_production_line_onto_archived_uap_returns_422(
        self, client, seed_user, seed_uap, seed_production_line, auth_headers
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))
        line = seed_production_line(namespace_id=NS, uap_id=None)

        response = client.put(
            f"{PRODUCTION_LINES_URL}/{line['id']}",
            json={"uap_id": uap["id"]},
            headers=auth_headers(owner),
        )

        assert response.status_code == 422

    def test_update_workstation_onto_archived_line_returns_422(
        self, client, seed_user, seed_uap, seed_production_line, seed_workstation, auth_headers
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=uap["id"])
        client.delete(f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner))
        station = seed_workstation(namespace_id=NS, production_line_id=None)

        response = client.put(
            f"{WORKSTATIONS_URL}/{station['id']}",
            json={"production_line_id": line["id"]},
            headers=auth_headers(owner),
        )

        assert response.status_code == 422


class TestArchiveTenantIsolation:
    def test_archive_uap_cross_namespace_returns_404(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = _owner(seed_user)
        other_owner = seed_user(role=Role.OWNER.value)
        other_namespace_uap = seed_uap(namespace_id=other_owner["namespace_id"])

        response = client.delete(
            f"{UAPS_URL}/{other_namespace_uap['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 404

    def test_archive_production_line_cross_namespace_returns_404(
        self, client, seed_user, seed_production_line, auth_headers
    ):
        owner = _owner(seed_user)
        other_owner = seed_user(role=Role.OWNER.value)
        other_namespace_line = seed_production_line(
            namespace_id=other_owner["namespace_id"], uap_id=None
        )

        response = client.delete(
            f"{PRODUCTION_LINES_URL}/{other_namespace_line['id']}",
            headers=auth_headers(owner),
        )

        assert response.status_code == 404

    def test_archive_workstation_cross_namespace_returns_404(
        self, client, seed_user, seed_workstation, auth_headers
    ):
        owner = _owner(seed_user)
        other_owner = seed_user(role=Role.OWNER.value)
        other_namespace_station = seed_workstation(
            namespace_id=other_owner["namespace_id"], production_line_id=None
        )

        response = client.delete(
            f"{WORKSTATIONS_URL}/{other_namespace_station['id']}",
            headers=auth_headers(owner),
        )

        assert response.status_code == 404


class TestArchiveRoleGuards:
    """The role restrictions of the former delete endpoints must still
    apply (owner/admin/production supervisor for all three resources)."""

    def test_archive_uap_forbidden_role_returns_403(
        self, client, seed_user, seed_uap, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE, namespace_id=NS)
        uap = seed_uap(namespace_id=NS)

        response = client.delete(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(agent))

        assert response.status_code == 403

    def test_archive_production_line_forbidden_role_returns_403(
        self, client, seed_user, seed_production_line, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE, namespace_id=NS)
        line = seed_production_line(namespace_id=NS, uap_id=None)

        response = client.delete(
            f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(agent)
        )

        assert response.status_code == 403

    def test_archive_workstation_forbidden_role_returns_403(
        self, client, seed_user, seed_workstation, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE, namespace_id=NS)
        station = seed_workstation(namespace_id=NS, production_line_id=None)

        response = client.delete(
            f"{WORKSTATIONS_URL}/{station['id']}", headers=auth_headers(agent)
        )

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Non-regression — expected to PASS immediately, even before the archiving
# implementation lands, because they exercise behavior that already exists
# today (hard delete of one resource does not touch a sibling's tree; an
# active/never-archived resource is listed/readable exactly as before).
# ---------------------------------------------------------------------------


class TestArchiveNonRegression:
    def test_archiving_one_uap_leaves_another_uaps_tree_untouched(
        self,
        client,
        fake_db,
        seed_user,
        seed_uap,
        seed_production_line,
        seed_workstation,
        auth_headers,
    ):
        owner = _owner(seed_user)
        uap_a = seed_uap(namespace_id=NS)
        uap_b = seed_uap(namespace_id=NS)
        line_b = seed_production_line(namespace_id=NS, uap_id=uap_b["id"])
        station_b = seed_workstation(namespace_id=NS, production_line_id=line_b["id"])

        response = client.delete(f"{UAPS_URL}/{uap_a['id']}", headers=auth_headers(owner))

        assert response.status_code == 200
        assert not _doc(fake_db, UAP_COLLECTION, uap_b["id"]).get("archived_at")
        assert not _doc(fake_db, PRODUCTION_LINE_COLLECTION, line_b["id"]).get("archived_at")
        assert not _doc(fake_db, WORKSTATION_COLLECTION, station_b["id"]).get("archived_at")

    def test_active_uap_is_still_listed_and_readable(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = _owner(seed_user)
        uap = seed_uap(namespace_id=NS)

        list_response = client.get(UAPS_URL, headers=auth_headers(owner))
        get_response = client.get(f"{UAPS_URL}/{uap['id']}", headers=auth_headers(owner))

        assert uap["id"] in [row["id"] for row in list_response.json()["data"]]
        assert get_response.status_code == 200

    def test_active_production_line_is_still_listed_and_readable(
        self, client, seed_user, seed_production_line, auth_headers
    ):
        owner = _owner(seed_user)
        line = seed_production_line(namespace_id=NS, uap_id=None)

        list_response = client.get(PRODUCTION_LINES_URL, headers=auth_headers(owner))
        get_response = client.get(
            f"{PRODUCTION_LINES_URL}/{line['id']}", headers=auth_headers(owner)
        )

        assert line["id"] in [row["id"] for row in list_response.json()["data"]]
        assert get_response.status_code == 200

    def test_active_workstation_is_still_listed_and_readable(
        self, client, seed_user, seed_workstation, auth_headers
    ):
        owner = _owner(seed_user)
        station = seed_workstation(namespace_id=NS, production_line_id=None)

        list_response = client.get(WORKSTATIONS_URL, headers=auth_headers(owner))
        get_response = client.get(
            f"{WORKSTATIONS_URL}/{station['id']}", headers=auth_headers(owner)
        )

        assert station["id"] in [row["id"] for row in list_response.json()["data"]]
        assert get_response.status_code == 200
