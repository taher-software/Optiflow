"""API tests for the ProductionLine resource.

Covers `src/app/routers/production_line/__init__.py` + `services.py`:
create/list/get/update/delete, `uap_id` cross-reference validation
(existence + namespace scoping + blank rejection), namespace isolation, and
the `require_roles(OWNER, ADMIN, PRODUCTION_SUPERVISOR)` guard.

No real Firestore/network is touched — `get_firestore_client()` is monkeypatched to an
in-memory fake (see `tests/conftest.py::fake_db`). No timestamps are part of
the ProductionLine contract, so `freezegun` is not needed here.
"""

from src.app.core.firestore import PRODUCTION_LINE_COLLECTION
from src.app.globals.enum import Role

from tests.factories.production_line import ProductionLinePayloadFactory

PRODUCTION_LINES_URL = "/production-lines"

# A role NOT permitted to manage production lines, used for 403 tests.
FORBIDDEN_ROLE = Role.MAINTENANCE_AGENT.value


class TestCreateProductionLine:
    """POST /production-lines"""

    def test_create_production_line_success_returns_201(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        payload = ProductionLinePayloadFactory(name="Line 1", uap_id=uap["id"])

        response = client.post(
            PRODUCTION_LINES_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "Line 1"
        assert data["uap_id"] == uap["id"]
        assert data["namespace_id"] == owner["namespace_id"]
        assert data["description"] == payload["description"]

    def test_create_production_line_nonexistent_uap_id_returns_422(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        payload = ProductionLinePayloadFactory(uap_id="does-not-exist")

        response = client.post(
            PRODUCTION_LINES_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422

    def test_create_production_line_cross_namespace_uap_id_returns_422(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        other_namespace_uap = seed_uap()
        payload = ProductionLinePayloadFactory(uap_id=other_namespace_uap["id"])

        response = client.post(
            PRODUCTION_LINES_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422

    def test_create_production_line_blank_uap_id_returns_422(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        payload = ProductionLinePayloadFactory(uap_id="")

        response = client.post(
            PRODUCTION_LINES_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422

    def test_create_production_line_missing_name_returns_422(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        payload = ProductionLinePayloadFactory(uap_id=uap["id"])
        del payload["name"]

        response = client.post(
            PRODUCTION_LINES_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422

    def test_create_production_line_unauthenticated_returns_401(self, client, fake_db):
        response = client.post(
            PRODUCTION_LINES_URL, json=ProductionLinePayloadFactory()
        )

        assert response.status_code == 401

    def test_create_production_line_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(),
            headers=auth_headers(agent),
        )

        assert response.status_code == 403


class TestProductionLineNameUniqueness:
    """Name uniqueness is enforced per namespace, per resource type, on both
    create and update. Comparison is on the name stripped and lowercased."""

    def test_create_production_line_duplicate_name_returns_409(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Line 1", uap_id=uap["id"]),
            headers=auth_headers(owner),
        )

        response = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Line 1", uap_id=uap["id"]),
            headers=auth_headers(owner),
        )

        assert response.status_code == 409

    def test_create_production_line_duplicate_name_different_case_returns_409(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Line 1", uap_id=uap["id"]),
            headers=auth_headers(owner),
        )

        response = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="line 1", uap_id=uap["id"]),
            headers=auth_headers(owner),
        )

        assert response.status_code == 409

    def test_create_production_line_duplicate_name_with_surrounding_spaces_returns_409(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Line 1", uap_id=uap["id"]),
            headers=auth_headers(owner),
        )

        response = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="  Line 1  ", uap_id=uap["id"]),
            headers=auth_headers(owner),
        )

        assert response.status_code == 409

    def test_create_production_line_free_name_returns_201(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Line 1", uap_id=uap["id"]),
            headers=auth_headers(owner),
        )

        response = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Line 2", uap_id=uap["id"]),
            headers=auth_headers(owner),
        )

        assert response.status_code == 201

    def test_update_production_line_name_taken_by_another_line_returns_409(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Line 1", uap_id=uap["id"]),
            headers=auth_headers(owner),
        )
        other = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Line 2", uap_id=uap["id"]),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{PRODUCTION_LINES_URL}/{other['id']}",
            json={"name": "Line 1"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 409

    def test_update_production_line_keeping_own_name_different_case_returns_200(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        created = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Line 1", uap_id=uap["id"]),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{PRODUCTION_LINES_URL}/{created['id']}",
            json={"name": "line 1"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        assert response.json()["data"]["name"] == "line 1"

    def test_create_production_line_same_name_in_another_namespace_returns_201(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        other_owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        other_uap = seed_uap(namespace_id=other_owner["namespace_id"])
        client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Line 1", uap_id=uap["id"]),
            headers=auth_headers(owner),
        )

        response = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Line 1", uap_id=other_uap["id"]),
            headers=auth_headers(other_owner),
        )

        assert response.status_code == 201

    def test_create_production_line_blank_name_returns_422(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        payload = ProductionLinePayloadFactory(name="   ", uap_id=uap["id"])

        response = client.post(
            PRODUCTION_LINES_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422


class TestListProductionLines:
    """GET /production-lines"""

    def test_list_production_lines_returns_only_caller_namespace(
        self, client, seed_user, seed_uap, auth_headers, fake_db
    ):
        owner = seed_user(role=Role.OWNER.value)
        other_owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        other_uap = seed_uap(namespace_id=other_owner["namespace_id"])

        client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Mine", uap_id=uap["id"]),
            headers=auth_headers(owner),
        )
        client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Theirs", uap_id=other_uap["id"]),
            headers=auth_headers(other_owner),
        )

        response = client.get(PRODUCTION_LINES_URL, headers=auth_headers(owner))

        assert response.status_code == 200
        names = [line["name"] for line in response.json()["data"]]
        assert names == ["Mine"]

    def test_list_production_lines_unauthenticated_returns_401(self, client, fake_db):
        response = client.get(PRODUCTION_LINES_URL)

        assert response.status_code == 401

    def test_list_production_lines_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.get(PRODUCTION_LINES_URL, headers=auth_headers(agent))

        assert response.status_code == 403


class TestGetProductionLine:
    """GET /production-lines/{line_id}"""

    def test_get_production_line_success_returns_200(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        created = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(uap_id=uap["id"]),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.get(
            f"{PRODUCTION_LINES_URL}/{created['id']}", headers=auth_headers(owner)
        )

        assert response.status_code == 200
        assert response.json()["data"]["id"] == created["id"]

    def test_get_production_line_not_found_returns_404(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)

        response = client.get(
            f"{PRODUCTION_LINES_URL}/nope", headers=auth_headers(owner)
        )

        assert response.status_code == 404

    def test_get_production_line_cross_namespace_returns_404(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        other_owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        created = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(uap_id=uap["id"]),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.get(
            f"{PRODUCTION_LINES_URL}/{created['id']}",
            headers=auth_headers(other_owner),
        )

        assert response.status_code == 404

    def test_get_production_line_unauthenticated_returns_401(self, client, fake_db):
        response = client.get(f"{PRODUCTION_LINES_URL}/some-id")

        assert response.status_code == 401

    def test_get_production_line_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.get(
            f"{PRODUCTION_LINES_URL}/some-id", headers=auth_headers(agent)
        )

        assert response.status_code == 403


class TestUpdateProductionLine:
    """PUT /production-lines/{line_id}"""

    def test_update_production_line_name_only_leaves_uap_id_untouched(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        created = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Original", uap_id=uap["id"]),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{PRODUCTION_LINES_URL}/{created['id']}",
            json={"name": "Renamed"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["name"] == "Renamed"
        assert body["uap_id"] == uap["id"]

    def test_update_production_line_uap_id_to_another_valid_uap(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        other_uap = seed_uap(namespace_id=owner["namespace_id"])
        created = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(uap_id=uap["id"]),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{PRODUCTION_LINES_URL}/{created['id']}",
            json={"uap_id": other_uap["id"]},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        assert response.json()["data"]["uap_id"] == other_uap["id"]

    def test_update_production_line_invalid_uap_id_returns_422_and_leaves_doc_unchanged(
        self, client, seed_user, seed_uap, auth_headers, fake_db
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        created = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Original", uap_id=uap["id"]),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{PRODUCTION_LINES_URL}/{created['id']}",
            json={"name": "Hacked", "uap_id": "does-not-exist"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 422
        stored = (
            fake_db.collection(PRODUCTION_LINE_COLLECTION)
            .document(created["id"])
            .get()
            .to_dict()
        )
        assert stored["name"] == "Original"
        assert stored["uap_id"] == uap["id"]

    def test_update_production_line_not_found_returns_404(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)

        response = client.put(
            f"{PRODUCTION_LINES_URL}/nope",
            json={"name": "New name"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 404

    def test_update_production_line_unauthenticated_returns_401(self, client, fake_db):
        response = client.put(f"{PRODUCTION_LINES_URL}/some-id", json={"name": "x"})

        assert response.status_code == 401

    def test_update_production_line_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.put(
            f"{PRODUCTION_LINES_URL}/some-id",
            json={"name": "x"},
            headers=auth_headers(agent),
        )

        assert response.status_code == 403


class TestDeleteProductionLine:
    """DELETE /production-lines/{line_id}"""

    def test_delete_production_line_returns_deleted_line_then_get_404(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        created = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="To delete", uap_id=uap["id"]),
            headers=auth_headers(owner),
        ).json()["data"]

        delete_response = client.delete(
            f"{PRODUCTION_LINES_URL}/{created['id']}", headers=auth_headers(owner)
        )

        assert delete_response.status_code == 200
        assert delete_response.json()["data"]["id"] == created["id"]
        assert delete_response.json()["data"]["name"] == "To delete"

        get_response = client.get(
            f"{PRODUCTION_LINES_URL}/{created['id']}", headers=auth_headers(owner)
        )
        assert get_response.status_code == 404

    def test_delete_production_line_not_found_returns_404(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)

        response = client.delete(
            f"{PRODUCTION_LINES_URL}/nope", headers=auth_headers(owner)
        )

        assert response.status_code == 404

    def test_delete_production_line_unauthenticated_returns_401(self, client, fake_db):
        response = client.delete(f"{PRODUCTION_LINES_URL}/some-id")

        assert response.status_code == 401

    def test_delete_production_line_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.delete(
            f"{PRODUCTION_LINES_URL}/some-id", headers=auth_headers(agent)
        )

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Work Unit test.optional_uap_and_password, CHANGE 1: `uap_id` becomes
# OPTIONAL on `CreateProductionLineIn` -- a production line may be
# "independent", belonging to no UAP, mirroring `Workstation.production_line_id`
# already being optional. Written test-first: as of this revision
# `CreateProductionLineIn.uap_id` is still `str = Field(..., min_length=1)`,
# so every "omit it / send it null" case below is expected to fail on that
# mandatory-field `422`, never on a broken fixture.
#
# The existing blank-string case
# (`TestCreateProductionLine.test_create_production_line_blank_uap_id_returns_422`,
# frozen, not touched) already proves `""` is rejected; this class adds the
# still-missing whitespace-only case and the new "no UAP at all" cases.
# ---------------------------------------------------------------------------


class TestOptionalUap:
    """POST /production-lines -- `uap_id` is now optional."""

    def test_create_production_line_without_uap_id_key_returns_201(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        payload = ProductionLinePayloadFactory(name="Independent Line")
        del payload["uap_id"]

        response = client.post(
            PRODUCTION_LINES_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["uap_id"] is None
        assert data["namespace_id"] == owner["namespace_id"]

    def test_create_production_line_explicit_null_uap_id_returns_201(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        payload = ProductionLinePayloadFactory(name="Independent Line 2")
        payload["uap_id"] = None

        response = client.post(
            PRODUCTION_LINES_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 201
        assert response.json()["data"]["uap_id"] is None

    def test_create_production_line_whitespace_only_uap_id_returns_422(
        self, client, seed_user, auth_headers
    ):
        """Whitespace-only must not sneak through as a valid value, same
        emptiness semantics as the existing blank-string (`""`) case."""
        owner = seed_user(role=Role.OWNER.value)
        payload = ProductionLinePayloadFactory(uap_id="   ")

        response = client.post(
            PRODUCTION_LINES_URL, json=payload, headers=auth_headers(owner)
        )

        assert response.status_code == 422

    def test_update_production_line_omitting_uap_id_still_leaves_it_untouched(
        self, client, seed_user, seed_uap, auth_headers
    ):
        """Non-regression: optional-on-create must not change update's
        existing "omitted field = leave untouched" semantics. Duplicates the
        spirit of the frozen
        `test_update_production_line_name_only_leaves_uap_id_untouched` on
        purpose, as a guard specific to this Work Unit's change."""
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        created = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Has a UAP", uap_id=uap["id"]),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{PRODUCTION_LINES_URL}/{created['id']}",
            json={"description": "updated description only"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        assert response.json()["data"]["uap_id"] == uap["id"]

    # RESOLVED (was an open anomaly): how a caller DETACHES an already-UAP'd
    # line follows the exact precedent already established for
    # `UpdateWorkstationIn.production_line_id` (`src/app/routers/workstation
    # /modelsIn.py`): omitted == leave untouched, explicit JSON `null` ==
    # detach, via `model_fields_set` rather than the value alone. See
    # `TestUpdateProductionLineUapDetach` below.


class TestUpdateProductionLineUapDetach:
    """PUT /production-lines/{line_id} -- `uap_id` follows the same
    `model_fields_set` partial-update semantics already used by
    `UpdateWorkstationIn.production_line_id`: omitted = leave untouched,
    explicit `null` = detach (the line becomes independent), a non-empty
    value = attach/reattach (still existence-checked).

    Written test-first: `UpdateProductionLineIn.uap_id` is still a plain
    `Optional[str] = Field(default=None, min_length=1)` read with `if
    payload.uap_id is not None`, with no `model_fields_set` branching at
    all -- so every "explicit null detaches" case below is expected to fail
    because the service reads an explicit `null` exactly like an omitted
    field (no-op), never on a broken fixture.
    """

    def test_update_production_line_omitting_uap_id_vs_explicit_null_diverge(
        self, client, seed_user, seed_uap, auth_headers
    ):
        """The whole point of `model_fields_set`: two PUTs on the same
        starting line, one omitting `uap_id` and one sending it explicitly
        as `null`, must produce DIFFERENT outcomes."""
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        line_1 = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Line Omit", uap_id=uap["id"]),
            headers=auth_headers(owner),
        ).json()["data"]
        line_2 = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(name="Line Null", uap_id=uap["id"]),
            headers=auth_headers(owner),
        ).json()["data"]

        omit_response = client.put(
            f"{PRODUCTION_LINES_URL}/{line_1['id']}",
            json={"description": "touched, uap_id omitted"},
            headers=auth_headers(owner),
        )
        null_response = client.put(
            f"{PRODUCTION_LINES_URL}/{line_2['id']}",
            json={"uap_id": None},
            headers=auth_headers(owner),
        )

        assert omit_response.status_code == 200
        assert omit_response.json()["data"]["uap_id"] == uap["id"]

        assert null_response.status_code == 200
        assert null_response.json()["data"]["uap_id"] is None

    def test_update_production_line_explicit_null_uap_id_detaches_to_independent(
        self, client, seed_user, seed_uap, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        created = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(uap_id=uap["id"]),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{PRODUCTION_LINES_URL}/{created['id']}",
            json={"uap_id": None},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        assert response.json()["data"]["uap_id"] is None

        get_response = client.get(
            f"{PRODUCTION_LINES_URL}/{created['id']}", headers=auth_headers(owner)
        )
        assert get_response.json()["data"]["uap_id"] is None

    def test_update_production_line_sets_uap_id_on_an_independent_line(
        self, client, seed_user, seed_uap, seed_production_line, auth_headers
    ):
        """The starting independent line is seeded directly into `fake_db`
        (bypassing `POST /production-lines`) so this test is isolated to the
        update-side detach/attach logic, and does not also depend on
        Change 1's create-time `uap_id` becoming optional."""
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        created = seed_production_line(
            namespace_id=owner["namespace_id"], uap_id=None
        )

        response = client.put(
            f"{PRODUCTION_LINES_URL}/{created['id']}",
            json={"uap_id": uap["id"]},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        assert response.json()["data"]["uap_id"] == uap["id"]

    def test_update_production_line_nonexistent_uap_id_still_returns_422(
        self, client, seed_user, seed_uap, seed_production_line, auth_headers
    ):
        """The existence check is not weakened by the detach semantics."""
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        created = seed_production_line(namespace_id=owner["namespace_id"], uap_id=uap["id"])

        response = client.put(
            f"{PRODUCTION_LINES_URL}/{created['id']}",
            json={"uap_id": "does-not-exist"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 422

    def test_update_production_line_cross_namespace_uap_id_still_returns_422(
        self, client, seed_user, seed_uap, seed_production_line, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        other_namespace_uap = seed_uap()
        created = seed_production_line(namespace_id=owner["namespace_id"], uap_id=uap["id"])

        response = client.put(
            f"{PRODUCTION_LINES_URL}/{created['id']}",
            json={"uap_id": other_namespace_uap["id"]},
            headers=auth_headers(owner),
        )

        assert response.status_code == 422

    def test_update_production_line_whitespace_only_uap_id_still_returns_422(
        self, client, seed_user, seed_uap, auth_headers
    ):
        """Same emptiness rule as creation -- whitespace-only must not sneak
        through as a valid value here either."""
        owner = seed_user(role=Role.OWNER.value)
        uap = seed_uap(namespace_id=owner["namespace_id"])
        created = client.post(
            PRODUCTION_LINES_URL,
            json=ProductionLinePayloadFactory(uap_id=uap["id"]),
            headers=auth_headers(owner),
        ).json()["data"]

        response = client.put(
            f"{PRODUCTION_LINES_URL}/{created['id']}",
            json={"uap_id": "   "},
            headers=auth_headers(owner),
        )

        assert response.status_code == 422
