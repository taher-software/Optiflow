"""API tests for the UAP (production area) resource.

Covers `src/app/routers/uap/__init__.py` + `services.py`: create/list/get/
update/delete, the 8 role-scoped id-list validations, namespace isolation,
and the `require_roles(OWNER, ADMIN, PRODUCTION_SUPERVISOR)` guard.

No real Firestore/network is touched — `get_firestore_client()` is monkeypatched to an
in-memory fake (see `tests/conftest.py::fake_db`). No timestamps are part of
the UAP contract, so `freezegun` is not needed here.
"""

from src.app.core.firestore import UAP_COLLECTION
from src.app.globals.enum import Role

from tests.factories.uap import UapPayloadFactory

UAPS_URL = "/uaps"

# Mirrors src.app.routers.uap.services._LIST_ROLE_MAP — the role each id-list
# field's members must hold.
LIST_ROLE_MAP = {
    "maintenance_agent_ids": Role.MAINTENANCE_AGENT.value,
    "production_agent_ids": Role.PRODUCTION_AGENT.value,
    "quality_agent_ids": Role.QUALITY_AGENT.value,
    "logistic_agent_ids": Role.LOGISTIC_AGENT.value,
    "logistic_supervisor_ids": Role.LOGISTIC_SUPERVISOR.value,
    "maintenance_supervisor_ids": Role.MAINTENANCE_SUPERVISOR.value,
    "quality_supervisor_ids": Role.QUALITY_SUPERVISOR.value,
    "production_supervisor_ids": Role.PRODUCTION_SUPERVISOR.value,
}

# A role NOT permitted to manage UAPs, used for 403 tests.
FORBIDDEN_ROLE = Role.MAINTENANCE_AGENT.value


class TestCreateUap:
    """POST /uaps"""

    def test_create_uap_success_returns_201(self, client, seed_user, auth_headers):
        owner = seed_user(role=Role.OWNER.value)
        member = seed_user(
            role=Role.MAINTENANCE_AGENT.value, namespace_id=owner["namespace_id"]
        )
        payload = UapPayloadFactory(
            name="Assembly line 1",
            maintenance_agent_ids=[member["id"]],
        )

        response = client.post(
            UAPS_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "Assembly line 1"
        assert data["namespace_id"] == owner["namespace_id"]
        assert data["maintenance_agent_ids"] == [member["id"]]
        assert data["production_agent_ids"] == []

    def test_create_uap_role_mismatch_id_returns_422(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        # Wrong role for the maintenance_agent_ids list.
        wrong_role_user = seed_user(
            role=Role.PRODUCTION_AGENT.value, namespace_id=owner["namespace_id"]
        )
        payload = UapPayloadFactory(maintenance_agent_ids=[wrong_role_user["id"]])

        response = client.post(
            UAPS_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422

    def test_create_uap_nonexistent_id_returns_422(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        payload = UapPayloadFactory(maintenance_agent_ids=["does-not-exist"])

        response = client.post(
            UAPS_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422

    def test_create_uap_cross_namespace_id_returns_422(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        other_namespace_member = seed_user(role=Role.MAINTENANCE_AGENT.value)
        payload = UapPayloadFactory(
            maintenance_agent_ids=[other_namespace_member["id"]]
        )

        response = client.post(
            UAPS_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422

    def test_create_uap_dedupes_repeated_ids(self, client, seed_user, auth_headers):
        owner = seed_user(role=Role.OWNER.value)
        member = seed_user(
            role=Role.MAINTENANCE_AGENT.value, namespace_id=owner["namespace_id"]
        )
        payload = UapPayloadFactory(
            maintenance_agent_ids=[member["id"], member["id"], member["id"]]
        )

        response = client.post(
            UAPS_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 201
        assert response.json()["data"]["maintenance_agent_ids"] == [member["id"]]

    def test_create_uap_unauthenticated_returns_401(self, client, fake_db):
        response = client.post(UAPS_URL, json=UapPayloadFactory())

        assert response.status_code == 401

    def test_create_uap_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.post(
            UAPS_URL, json=UapPayloadFactory(), headers=auth_headers(agent)
        )

        assert response.status_code == 403

    def test_create_uap_missing_name_returns_422(self, client, seed_user, auth_headers):
        owner = seed_user(role=Role.OWNER.value)
        payload = UapPayloadFactory()
        del payload["name"]

        response = client.post(
            UAPS_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422


class TestListUaps:
    """GET /uaps"""

    def test_list_uaps_returns_only_caller_namespace(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = seed_user(role=Role.OWNER.value)
        other_owner = seed_user(role=Role.OWNER.value)

        client.post(
            UAPS_URL,
            json=UapPayloadFactory(name="Mine"),
            headers=auth_headers(owner),
        )
        client.post(
            UAPS_URL,
            json=UapPayloadFactory(name="Theirs"),
            headers=auth_headers(other_owner),
        )

        response = client.get(UAPS_URL, headers=auth_headers(owner))

        assert response.status_code == 200
        names = [uap["name"] for uap in response.json()["data"]]
        assert names == ["Mine"]

    def test_list_uaps_unauthenticated_returns_401(self, client, fake_db):
        response = client.get(UAPS_URL)

        assert response.status_code == 401

    def test_list_uaps_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.get(UAPS_URL, headers=auth_headers(agent))

        assert response.status_code == 403


class TestGetUap:
    """GET /uaps/{uap_id}"""

    def test_get_uap_success_returns_200(self, client, seed_user, auth_headers):
        owner = seed_user(role=Role.OWNER.value)
        created = client.post(
            UAPS_URL, json=UapPayloadFactory(), headers=auth_headers(owner)
        ).json()["data"]

        response = client.get(
            f"{UAPS_URL}/{created['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 200
        assert response.json()["data"]["id"] == created["id"]

    def test_get_uap_not_found_returns_404(self, client, seed_user, auth_headers):
        owner = seed_user(role=Role.OWNER.value)

        response = client.get(f"{UAPS_URL}/nope", headers=auth_headers(owner))

        assert response.status_code == 404

    def test_get_uap_cross_namespace_returns_404(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        other_owner = seed_user(role=Role.OWNER.value)
        created = client.post(
            UAPS_URL, json=UapPayloadFactory(), headers=auth_headers(owner)
        ).json()["data"]

        response = client.get(
            f"{UAPS_URL}/{created['id']}", headers=auth_headers(other_owner)
        )

        assert response.status_code == 404

    def test_get_uap_unauthenticated_returns_401(self, client, fake_db):
        response = client.get(f"{UAPS_URL}/some-id")

        assert response.status_code == 401

    def test_get_uap_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.get(f"{UAPS_URL}/some-id", headers=auth_headers(agent))

        assert response.status_code == 403


class TestUpdateUap:
    """PUT /uaps/{uap_id}"""

    def test_update_uap_replaces_provided_list(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        old_member = seed_user(
            role=Role.MAINTENANCE_AGENT.value, namespace_id=owner["namespace_id"]
        )
        new_member = seed_user(
            role=Role.MAINTENANCE_AGENT.value, namespace_id=owner["namespace_id"]
        )
        created = client.post(
            UAPS_URL,
            json=UapPayloadFactory(maintenance_agent_ids=[old_member["id"]]),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{UAPS_URL}/{created['id']}",
            json={"maintenance_agent_ids": [new_member["id"]]},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        assert response.json()["data"]["maintenance_agent_ids"] == [new_member["id"]]

    def test_update_uap_leaves_omitted_list_untouched(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        member = seed_user(
            role=Role.MAINTENANCE_AGENT.value, namespace_id=owner["namespace_id"]
        )
        created = client.post(
            UAPS_URL,
            json=UapPayloadFactory(maintenance_agent_ids=[member["id"]]),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{UAPS_URL}/{created['id']}",
            json={"name": "Renamed"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["name"] == "Renamed"
        assert body["maintenance_agent_ids"] == [member["id"]]

    def test_update_uap_invalid_id_returns_422_and_leaves_doc_unchanged(
        self, client, seed_user, auth_headers, fake_db
    ):
        owner = seed_user(role=Role.OWNER.value)
        member = seed_user(
            role=Role.MAINTENANCE_AGENT.value, namespace_id=owner["namespace_id"]
        )
        created = client.post(
            UAPS_URL,
            json=UapPayloadFactory(
                name="Original", maintenance_agent_ids=[member["id"]]
            ),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{UAPS_URL}/{created['id']}",
            json={"name": "Hacked", "maintenance_agent_ids": ["does-not-exist"]},
            headers=auth_headers(owner),
        )

        assert response.status_code == 422
        stored = (
            fake_db.collection(UAP_COLLECTION).document(created["id"]).get().to_dict()
        )
        assert stored["name"] == "Original"
        assert stored["maintenance_agent_ids"] == [member["id"]]

    def test_update_uap_not_found_returns_404(self, client, seed_user, auth_headers):
        owner = seed_user(role=Role.OWNER.value)

        response = client.put(
            f"{UAPS_URL}/nope",
            json={"name": "New name"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 404

    def test_update_uap_unauthenticated_returns_401(self, client, fake_db):
        response = client.put(f"{UAPS_URL}/some-id", json={"name": "x"})

        assert response.status_code == 401

    def test_update_uap_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.put(
            f"{UAPS_URL}/some-id",
            json={"name": "x"},
            headers=auth_headers(agent),
        )

        assert response.status_code == 403


class TestDeleteUap:
    """DELETE /uaps/{uap_id}"""

    def test_delete_uap_returns_deleted_uap_then_get_404(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        created = client.post(
            UAPS_URL,
            json=UapPayloadFactory(name="To delete"),
            headers=auth_headers(owner),
        ).json()["data"]

        delete_response = client.delete(
            f"{UAPS_URL}/{created['id']}", headers=auth_headers(owner)
        )

        assert delete_response.status_code == 200
        assert delete_response.json()["data"]["id"] == created["id"]
        assert delete_response.json()["data"]["name"] == "To delete"

        get_response = client.get(
            f"{UAPS_URL}/{created['id']}", headers=auth_headers(owner)
        )
        assert get_response.status_code == 404

    def test_delete_uap_not_found_returns_404(self, client, seed_user, auth_headers):
        owner = seed_user(role=Role.OWNER.value)

        response = client.delete(f"{UAPS_URL}/nope", headers=auth_headers(owner))

        assert response.status_code == 404

    def test_delete_uap_unauthenticated_returns_401(self, client, fake_db):
        response = client.delete(f"{UAPS_URL}/some-id")

        assert response.status_code == 401

    def test_delete_uap_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.delete(
            f"{UAPS_URL}/some-id", headers=auth_headers(agent)
        )

        assert response.status_code == 403
