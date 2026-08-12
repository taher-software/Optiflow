"""API tests for the namespace plant-settings resource.

Covers `src/app/routers/settings/__init__.py` + `services.py`:
create (full doc, shift-window cross-validation, escalation default),
partial update (merge / 404 when absent), tenant-scoped get (own namespace
only), and the `require_roles(OWNER, ADMIN, MANAGER, PRODUCTION_SUPERVISOR)`
guard. No real Firestore is touched (see `tests/conftest.py::fake_db`, which
now also wires the settings services module).
"""

from src.app.core.firestore import (
    NAMESPACE_SETTINGS_COLLECTION,
    SETTINGS_SUBCOLLECTION,
)
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import Role

SETTINGS_URL = "/settings"

# A role NOT permitted to manage settings, used for 403 tests.
FORBIDDEN_ROLE = Role.MAINTENANCE_AGENT.value


def _actor(seed_user, **overrides):
    overrides.setdefault("role", Role.PRODUCTION_SUPERVISOR.value)
    return seed_user(**overrides)


def _stored(fake_db, namespace_id):
    return FirestoreClient(client=fake_db).get_subdocument(
        NAMESPACE_SETTINGS_COLLECTION, namespace_id, SETTINGS_SUBCOLLECTION, namespace_id
    )


class TestCreateSettings:
    def test_create_single_shift_defaults_escalation(
        self, client, fake_db, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL, json={"shift_number": 1}, headers=auth_headers(actor)
        )
        assert res.status_code == 201, res.text
        data = res.json()["data"]
        assert data["shift_number"] == 1
        assert data["time_to_escalate"] == 1800  # default
        assert data["shift_1"] is None

        stored = _stored(fake_db, actor["namespace_id"])
        assert stored["namespace_id"] == actor["namespace_id"]
        assert stored["shift_number"] == 1

    def test_create_multi_shift_with_windows(
        self, client, fake_db, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 2,
                "shift_1": {"start_time": "06:00", "end_time": "14:00"},
                "shift_2": {"start_time": "14:00", "end_time": "22:00"},
                "time_to_escalate": 900,
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 201, res.text
        data = res.json()["data"]
        assert data["shift_1"] == {"start_time": "06:00", "end_time": "14:00"}
        assert data["shift_2"] == {"start_time": "14:00", "end_time": "22:00"}
        assert data["time_to_escalate"] == 900

    def test_create_multi_shift_missing_window_is_422(
        self, client, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 2,
                "shift_1": {"start_time": "06:00", "end_time": "14:00"},
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 422

    def test_create_invalid_time_format_is_422(
        self, client, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        res = client.post(
            SETTINGS_URL,
            json={
                "shift_number": 1,
                "shift_1": {"start_time": "6am", "end_time": "14:00"},
            },
            headers=auth_headers(actor),
        )
        assert res.status_code == 422

    def test_create_forbidden_role_is_403(self, client, seed_user, auth_headers):
        actor = seed_user(role=FORBIDDEN_ROLE)
        res = client.post(
            SETTINGS_URL, json={"shift_number": 1}, headers=auth_headers(actor)
        )
        assert res.status_code == 403


class TestUpdateSettings:
    def test_patch_merges_only_provided_fields(
        self, client, fake_db, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        client.post(
            SETTINGS_URL,
            json={
                "shift_number": 2,
                "shift_1": {"start_time": "06:00", "end_time": "18:00"},
                "shift_2": {"start_time": "18:00", "end_time": "06:00"},
                "time_to_escalate": 1800,
            },
            headers=auth_headers(actor),
        )

        res = client.patch(
            SETTINGS_URL,
            json={"time_to_escalate": 600},
            headers=auth_headers(actor),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["time_to_escalate"] == 600
        # Untouched fields preserved.
        assert data["shift_number"] == 2
        assert data["shift_1"] == {"start_time": "06:00", "end_time": "18:00"}

    def test_patch_can_clear_a_shift_with_explicit_null(
        self, client, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        client.post(
            SETTINGS_URL,
            json={
                "shift_number": 2,
                "shift_1": {"start_time": "06:00", "end_time": "18:00"},
                "shift_2": {"start_time": "18:00", "end_time": "06:00"},
            },
            headers=auth_headers(actor),
        )
        res = client.patch(
            SETTINGS_URL,
            json={"shift_number": 1, "shift_2": None},
            headers=auth_headers(actor),
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["shift_number"] == 1
        assert data["shift_2"] is None

    def test_patch_without_existing_settings_is_404(
        self, client, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        res = client.patch(
            SETTINGS_URL,
            json={"time_to_escalate": 600},
            headers=auth_headers(actor),
        )
        assert res.status_code == 404


class TestGetSettings:
    def test_get_own_namespace_returns_settings(
        self, client, seed_user, auth_headers
    ):
        actor = _actor(seed_user)
        client.post(
            SETTINGS_URL, json={"shift_number": 1}, headers=auth_headers(actor)
        )
        res = client.get(
            f"{SETTINGS_URL}/{actor['namespace_id']}", headers=auth_headers(actor)
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["namespace_id"] == actor["namespace_id"]

    def test_get_before_create_is_404(self, client, seed_user, auth_headers):
        actor = _actor(seed_user)
        res = client.get(
            f"{SETTINGS_URL}/{actor['namespace_id']}", headers=auth_headers(actor)
        )
        assert res.status_code == 404

    def test_get_other_namespace_is_403(self, client, seed_user, auth_headers):
        actor = _actor(seed_user)
        res = client.get(
            f"{SETTINGS_URL}/some-other-namespace", headers=auth_headers(actor)
        )
        assert res.status_code == 403

    def test_get_forbidden_role_is_403(self, client, seed_user, auth_headers):
        actor = seed_user(role=FORBIDDEN_ROLE)
        res = client.get(
            f"{SETTINGS_URL}/{actor['namespace_id']}", headers=auth_headers(actor)
        )
        assert res.status_code == 403
