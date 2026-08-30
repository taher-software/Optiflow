"""API tests for the self-service "online" toggle.

Covers the not-yet-built contract in `.claude/specs/mobile-online-toggle.md`:

- `PATCH /users/me/online` (`src/app/routers/user/__init__.py` /
  `services.py`, to be added as `set_own_online`) — any authenticated user
  flips their own `online` flag, idempotently, self-service (no role check).
- `AuthUserOut.online` (`src/app/routers/auth/modelsOut.py` /
  `services.py`) — logins must surface the caller's current `online` state,
  defaulting to `True` when the field is absent from the Firestore document
  (the exact default already relied on by the notification filters in
  `src/app/async_jobs/add_down_time.py`, `notify_down_time_update.py`, and
  `escalate_down_time.py`).

Written test-first: none of `PATCH /users/me/online`, `SetOnlineIn`, or
`AuthUserOut.online` exist yet, so every test in this module is expected to
fail — on the route not existing (404, since no `/users/{user_id}` route
accepts PATCH either) or on the `online` key being absent from the response
body — never on a broken fixture.

Scenario 12 of the contract ("existing notification filters keep excluding
`online: false` users and including users with no `online` key") is a
non-regression check on code that already exists and is already exercised by
the frozen suites in `tests/async_jobs/test_add_down_time.py`,
`test_notify_down_time_update.py`, and `test_escalate_down_time.py`. It is
intentionally NOT duplicated here — this module only covers the new surface
this Work Unit adds (the endpoint + the login field), per the instruction not
to touch frozen test files.
"""

import pytest

from src.app.core.firestore import USERS_COLLECTION
from src.app.globals.enum import Role

from tests.factories.user import UserFactory

SET_ONLINE_URL = "/users/me/online"
MOBILE_LOGIN_URL = "/auth/mobile-login"

# A role that is neither owner nor admin: self-service online toggling must
# succeed for it, since /users/* is otherwise owner/admin-only via
# `_admin_or_owner` and the real regression risk is the new route inheriting
# that guard.
NON_ADMIN_ROLE = Role.PRODUCTION_AGENT.value


class TestSetOwnOnline:
    """PATCH /users/me/online"""

    def test_set_own_online_false_returns_200_and_updates_document(
        self, client, seed_user, auth_headers, fake_db
    ):
        caller = seed_user(online=True)

        response = client.patch(
            SET_ONLINE_URL, json={"online": False}, headers=auth_headers(caller)
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["online"] is False
        stored = (
            fake_db.collection(USERS_COLLECTION)
            .document(caller["id"])
            .get()
            .to_dict()
        )
        assert stored["online"] is False

    def test_set_own_online_true_returns_200_and_updates_document(
        self, client, seed_user, auth_headers, fake_db
    ):
        caller = seed_user(online=False)

        response = client.patch(
            SET_ONLINE_URL, json={"online": True}, headers=auth_headers(caller)
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["online"] is True
        stored = (
            fake_db.collection(USERS_COLLECTION)
            .document(caller["id"])
            .get()
            .to_dict()
        )
        assert stored["online"] is True

    def test_set_own_online_is_idempotent_on_repeated_calls(
        self, client, seed_user, auth_headers, fake_db
    ):
        caller = seed_user(online=True)

        first = client.patch(
            SET_ONLINE_URL, json={"online": False}, headers=auth_headers(caller)
        )
        second = client.patch(
            SET_ONLINE_URL, json={"online": False}, headers=auth_headers(caller)
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["data"]["online"] is False
        stored = (
            fake_db.collection(USERS_COLLECTION)
            .document(caller["id"])
            .get()
            .to_dict()
        )
        assert stored["online"] is False

    def test_set_own_online_unauthenticated_returns_401(self, client, fake_db):
        response = client.patch(SET_ONLINE_URL, json={"online": False})

        assert response.status_code == 401

    def test_set_own_online_non_admin_role_succeeds(
        self, client, seed_user, auth_headers, fake_db
    ):
        caller = seed_user(role=NON_ADMIN_ROLE, online=True)

        response = client.patch(
            SET_ONLINE_URL, json={"online": False}, headers=auth_headers(caller)
        )

        assert response.status_code == 200
        assert response.json()["data"]["online"] is False

    def test_set_own_online_missing_field_returns_422(
        self, client, seed_user, auth_headers, fake_db
    ):
        caller = seed_user()

        response = client.patch(SET_ONLINE_URL, json={}, headers=auth_headers(caller))

        assert response.status_code == 422

    @pytest.mark.parametrize("bad_value", ["yes", 1, "true", None])
    def test_set_own_online_non_boolean_value_returns_422(
        self, client, seed_user, auth_headers, fake_db, bad_value
    ):
        caller = seed_user()

        response = client.patch(
            SET_ONLINE_URL,
            json={"online": bad_value},
            headers=auth_headers(caller),
        )

        assert response.status_code == 422

    def test_set_own_online_does_not_match_user_id_route_for_id_me(
        self, client, seed_user, auth_headers, fake_db
    ):
        """`/users/me/online` must not be swallowed by `/{user_id}`: a
        document literally id'd "me" in the caller's own namespace must be
        left untouched by the call, and the caller's own document (not the
        "me" document) must be the one updated."""
        caller = seed_user(online=True)
        decoy = seed_user(
            id="me", namespace_id=caller["namespace_id"], online=True
        )

        response = client.patch(
            SET_ONLINE_URL, json={"online": False}, headers=auth_headers(caller)
        )

        assert response.status_code == 200
        assert response.json()["data"]["id"] == caller["id"]

        caller_doc = (
            fake_db.collection(USERS_COLLECTION)
            .document(caller["id"])
            .get()
            .to_dict()
        )
        decoy_doc = (
            fake_db.collection(USERS_COLLECTION).document(decoy["id"]).get().to_dict()
        )
        assert caller_doc["online"] is False
        assert decoy_doc["online"] is True

    def test_set_own_online_does_not_affect_other_user_in_same_namespace(
        self, client, seed_user, auth_headers, fake_db
    ):
        caller = seed_user(online=True)
        other = seed_user(namespace_id=caller["namespace_id"], online=True)

        response = client.patch(
            SET_ONLINE_URL, json={"online": False}, headers=auth_headers(caller)
        )

        assert response.status_code == 200
        other_doc = (
            fake_db.collection(USERS_COLLECTION).document(other["id"]).get().to_dict()
        )
        assert other_doc["online"] is True

    def test_set_own_online_preserves_other_fields_on_own_document(
        self, client, seed_user, auth_headers, fake_db
    ):
        caller = seed_user(
            online=True,
            security_code="4821",
            role=Role.MAINTENANCE_AGENT.value,
            push_token="expo-token-abc",
        )

        response = client.patch(
            SET_ONLINE_URL, json={"online": False}, headers=auth_headers(caller)
        )

        assert response.status_code == 200
        stored = (
            fake_db.collection(USERS_COLLECTION)
            .document(caller["id"])
            .get()
            .to_dict()
        )
        assert stored["security_code"] == "4821"
        assert stored["role"] == Role.MAINTENANCE_AGENT.value
        assert stored["push_token"] == "expo-token-abc"
        assert stored["first_name"] == caller["first_name"]
        assert stored["last_name"] == caller["last_name"]


class TestAuthUserOutOnline:
    """`online` on `AuthUserOut`, surfaced through `POST /auth/mobile-login`."""

    def test_login_returns_online_false_when_set_on_document(
        self, client, seed_user, fake_db
    ):
        user = seed_user(device_id="device-online-1", online=False)

        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "device-online-1"})

        assert response.status_code == 200
        assert response.json()["data"]["user"].get("online") is False

    def test_login_returns_online_true_when_set_on_document(
        self, client, seed_user, fake_db
    ):
        user = seed_user(device_id="device-online-2", online=True)

        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "device-online-2"})

        assert response.status_code == 200
        assert response.json()["data"]["user"].get("online") is True

    def test_login_defaults_online_true_when_field_absent_from_document(
        self, client, seed_user, fake_db
    ):
        # UserFactory does not set an `online` key by default, mirroring a
        # user document created before the field existed.
        user = UserFactory(device_id="device-online-3")
        assert "online" not in user
        fake_db.collection(USERS_COLLECTION).document(user["id"]).set(user)

        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "device-online-3"})

        assert response.status_code == 200
        assert response.json()["data"]["user"].get("online") is True
