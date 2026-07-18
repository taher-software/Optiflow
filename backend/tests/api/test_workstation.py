"""API tests for the Workstation resource.

Covers `src/app/routers/workstation/__init__.py` + `services.py`:
create/list/get/update/delete, `production_line_id` cross-reference
validation (existence + namespace scoping + blank rejection + nullable
"independent" semantics), `type` enum validation, the tri-state partial
update of `production_line_id` (omitted / explicit null / value), namespace
isolation, and the `require_roles(OWNER, ADMIN, PRODUCTION_SUPERVISOR)` guard.

No real Firestore/network is touched — `get_db()` is monkeypatched to an
in-memory fake (see `tests/conftest.py::fake_db`). No timestamps are part of
the Workstation contract, so `freezegun` is not needed here.
"""

from src.app.core.firestore import WORKSTATION_COLLECTION
from src.app.globals.enum import Role, WorkstationType

from tests.factories.production_line import ProductionLinePayloadFactory
from tests.factories.workstation import WorkstationPayloadFactory

WORKSTATIONS_URL = "/workstations"
PRODUCTION_LINES_URL = "/production-lines"

# A role NOT permitted to manage workstations, used for 403 tests.
FORBIDDEN_ROLE = Role.MAINTENANCE_AGENT.value


def _create_line(client, seed_uap, auth_headers, owner) -> dict:
    """Helper: create a production line in `owner`'s namespace via the API,
    used to attach workstations to a real line."""
    uap = seed_uap(namespace_id=owner["namespace_id"])
    return client.post(
        PRODUCTION_LINES_URL,
        json=ProductionLinePayloadFactory(uap_id=uap["id"]),
        headers=auth_headers(owner),
    ).json()["data"]


class TestCreateWorkstation:
    """POST /workstations"""

    def test_create_workstation_independent_returns_201(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        payload = WorkstationPayloadFactory(name="Press 1")

        response = client.post(
            WORKSTATIONS_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "Press 1"
        assert data["production_line_id"] is None
        assert data["namespace_id"] == owner["namespace_id"]

    def test_create_workstation_attached_to_line_returns_201(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        line = _create_line(client, seed_uap, auth_headers, owner)
        payload = WorkstationPayloadFactory(production_line_id=line["id"])

        response = client.post(
            WORKSTATIONS_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 201
        assert response.json()["data"]["production_line_id"] == line["id"]

    def test_create_workstation_nonexistent_line_id_returns_422(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        payload = WorkstationPayloadFactory(production_line_id="does-not-exist")

        response = client.post(
            WORKSTATIONS_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422

    def test_create_workstation_cross_namespace_line_id_returns_422(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        other_owner = seed_user(role=Role.OWNER.value)
        other_line = _create_line(client, seed_uap, auth_headers, other_owner)
        payload = WorkstationPayloadFactory(production_line_id=other_line["id"])

        response = client.post(
            WORKSTATIONS_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422

    def test_create_workstation_blank_line_id_returns_422(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        payload = WorkstationPayloadFactory(production_line_id="")

        response = client.post(
            WORKSTATIONS_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422

    def test_create_workstation_invalid_type_returns_422(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        payload = WorkstationPayloadFactory(type="not-a-real-type")

        response = client.post(
            WORKSTATIONS_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422

    def test_create_workstation_missing_name_returns_422(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        payload = WorkstationPayloadFactory()
        del payload["name"]

        response = client.post(
            WORKSTATIONS_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422

    def test_create_workstation_unauthenticated_returns_401(self, client, fake_db):
        response = client.post(WORKSTATIONS_URL, json=WorkstationPayloadFactory())

        assert response.status_code == 401

    def test_create_workstation_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.post(
            WORKSTATIONS_URL,
            json=WorkstationPayloadFactory(),
            headers=auth_headers(agent),
        )

        assert response.status_code == 403


class TestListWorkstations:
    """GET /workstations"""

    def test_list_workstations_returns_only_caller_namespace(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = seed_user(role=Role.OWNER.value)
        other_owner = seed_user(role=Role.OWNER.value)

        client.post(
            WORKSTATIONS_URL,
            json=WorkstationPayloadFactory(name="Mine"),
            headers=auth_headers(owner),
        )
        client.post(
            WORKSTATIONS_URL,
            json=WorkstationPayloadFactory(name="Theirs"),
            headers=auth_headers(other_owner),
        )

        response = client.get(WORKSTATIONS_URL, headers=auth_headers(owner))

        assert response.status_code == 200
        names = [s["name"] for s in response.json()["data"]]
        assert names == ["Mine"]

    def test_list_workstations_unauthenticated_returns_401(self, client, fake_db):
        response = client.get(WORKSTATIONS_URL)

        assert response.status_code == 401

    def test_list_workstations_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.get(WORKSTATIONS_URL, headers=auth_headers(agent))

        assert response.status_code == 403


class TestGetWorkstation:
    """GET /workstations/{station_id}"""

    def test_get_workstation_success_returns_200(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        created = client.post(
            WORKSTATIONS_URL,
            json=WorkstationPayloadFactory(),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.get(
            f"{WORKSTATIONS_URL}/{created['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 200
        assert response.json()["data"]["id"] == created["id"]

    def test_get_workstation_not_found_returns_404(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)

        response = client.get(f"{WORKSTATIONS_URL}/nope", headers=auth_headers(owner))

        assert response.status_code == 404

    def test_get_workstation_cross_namespace_returns_404(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        other_owner = seed_user(role=Role.OWNER.value)
        created = client.post(
            WORKSTATIONS_URL,
            json=WorkstationPayloadFactory(),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.get(
            f"{WORKSTATIONS_URL}/{created['id']}", headers=auth_headers(other_owner)
        )

        assert response.status_code == 404

    def test_get_workstation_unauthenticated_returns_401(self, client, fake_db):
        response = client.get(f"{WORKSTATIONS_URL}/some-id")

        assert response.status_code == 401

    def test_get_workstation_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.get(
            f"{WORKSTATIONS_URL}/some-id", headers=auth_headers(agent)
        )

        assert response.status_code == 403


class TestUpdateWorkstation:
    """PUT /workstations/{station_id}"""

    def test_update_workstation_name_only_leaves_line_and_type_intact(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        line = _create_line(client, seed_uap, auth_headers, owner)
        created = client.post(
            WORKSTATIONS_URL,
            json=WorkstationPayloadFactory(
                name="Original",
                production_line_id=line["id"],
                type=WorkstationType.BOTTLENECK.value,
            ),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{WORKSTATIONS_URL}/{created['id']}",
            json={"name": "Renamed"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["name"] == "Renamed"
        assert body["production_line_id"] == line["id"]
        assert body["type"] == WorkstationType.BOTTLENECK.value

    def test_update_workstation_explicit_null_line_id_detaches_to_independent(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        line = _create_line(client, seed_uap, auth_headers, owner)
        created = client.post(
            WORKSTATIONS_URL,
            json=WorkstationPayloadFactory(production_line_id=line["id"]),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{WORKSTATIONS_URL}/{created['id']}",
            json={"production_line_id": None},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        assert response.json()["data"]["production_line_id"] is None

    def test_update_workstation_sets_line_to_a_valid_line(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        line = _create_line(client, seed_uap, auth_headers, owner)
        created = client.post(
            WORKSTATIONS_URL,
            json=WorkstationPayloadFactory(),
            headers=auth_headers(owner),
        ).json()["data"]
        assert created["production_line_id"] is None

        response = client.put(
            f"{WORKSTATIONS_URL}/{created['id']}",
            json={"production_line_id": line["id"]},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        assert response.json()["data"]["production_line_id"] == line["id"]

    def test_update_workstation_invalid_line_id_returns_422_and_leaves_doc_unchanged(
        self, client, seed_user, seed_uap, auth_headers, fake_db
    ):
        owner = seed_user(role=Role.OWNER.value)
        line = _create_line(client, seed_uap, auth_headers, owner)
        created = client.post(
            WORKSTATIONS_URL,
            json=WorkstationPayloadFactory(
                name="Original", production_line_id=line["id"]
            ),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{WORKSTATIONS_URL}/{created['id']}",
            json={"name": "Hacked", "production_line_id": "does-not-exist"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 422
        stored = (
            fake_db.collection(WORKSTATION_COLLECTION)
            .document(created["id"])
            .get()
            .to_dict()
        )
        assert stored["name"] == "Original"
        assert stored["production_line_id"] == line["id"]

    def test_update_workstation_not_found_returns_404(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)

        response = client.put(
            f"{WORKSTATIONS_URL}/nope",
            json={"name": "New name"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 404

    def test_update_workstation_unauthenticated_returns_401(self, client, fake_db):
        response = client.put(f"{WORKSTATIONS_URL}/some-id", json={"name": "x"})

        assert response.status_code == 401

    def test_update_workstation_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.put(
            f"{WORKSTATIONS_URL}/some-id",
            json={"name": "x"},
            headers=auth_headers(agent),
        )

        assert response.status_code == 403


class TestDeleteWorkstation:
    """DELETE /workstations/{station_id}"""

    def test_delete_workstation_returns_deleted_station_then_get_404(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        created = client.post(
            WORKSTATIONS_URL,
            json=WorkstationPayloadFactory(name="To delete"),
            headers=auth_headers(owner),
        ).json()["data"]

        delete_response = client.delete(
            f"{WORKSTATIONS_URL}/{created['id']}", headers=auth_headers(owner)
        )

        assert delete_response.status_code == 200
        assert delete_response.json()["data"]["id"] == created["id"]
        assert delete_response.json()["data"]["name"] == "To delete"

        get_response = client.get(
            f"{WORKSTATIONS_URL}/{created['id']}", headers=auth_headers(owner)
        )
        assert get_response.status_code == 404

    def test_delete_workstation_not_found_returns_404(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)

        response = client.delete(
            f"{WORKSTATIONS_URL}/nope", headers=auth_headers(owner)
        )

        assert response.status_code == 404

    def test_delete_workstation_unauthenticated_returns_401(self, client, fake_db):
        response = client.delete(f"{WORKSTATIONS_URL}/some-id")

        assert response.status_code == 401

    def test_delete_workstation_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.delete(
            f"{WORKSTATIONS_URL}/some-id", headers=auth_headers(agent)
        )

        assert response.status_code == 403
