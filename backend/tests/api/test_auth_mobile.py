"""API tests for the device-based mobile auth endpoints.

Covers `src/app/routers/auth/__init__.py` + `services.py`: `/auth/mobile-login`
and `/auth/check-user-code`. Both endpoints are unauthenticated on purpose
(a device pairs/logs in before it has a bearer token), so there is no 401/403
scenario for them here — that absence is itself asserted below.

No real Firestore/network is touched — `get_firestore_client()` is monkeypatched to an
in-memory fake for `src.app.routers.auth.services` (see
`tests/conftest.py::fake_db`). `generate_security_code` (used to rotate the
code on pairing) receives the `FirestoreClient` as an explicit argument from
the caller rather than calling `get_firestore_client()` itself, so it is
exercised transparently against the same fake store.
"""

from src.app.core.firestore import USERS_COLLECTION
from src.app.core.security import read_access_token

from tests.factories.user import UserFactory

MOBILE_LOGIN_URL = "/auth/mobile-login"
CHECK_USER_CODE_URL = "/auth/check-user-code"


class TestMobileLogin:
    """POST /auth/mobile-login"""

    def test_mobile_login_success_returns_200(self, client, seed_user):
        user = seed_user(device_id="device-123", push_token="old-token")

        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "device-123"})

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["user"]["id"] == user["id"]
        assert data["user"]["email"] == user["email"]
        assert data["access_token"]

    def test_mobile_login_decodes_access_token_claims(self, client, seed_user):
        user = seed_user(device_id="device-123", role="owner")

        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "device-123"})

        token = response.json()["data"]["access_token"]
        claims = read_access_token(token)
        assert claims["user_id"] == user["id"]
        assert claims["namespace_id"] == user["namespace_id"]
        assert claims["role"] == "owner"

    def test_mobile_login_updates_push_token_when_different(
        self, client, seed_user, fake_db
    ):
        user = seed_user(device_id="device-123", push_token="old-token")

        response = client.post(
            MOBILE_LOGIN_URL,
            json={"device_id": "device-123", "push_token": "new-token"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["user"]["id"] == user["id"]
        stored = (
            fake_db.collection(USERS_COLLECTION).document(user["id"]).get().to_dict()
        )
        assert stored["push_token"] == "new-token"

    def test_mobile_login_sets_push_token_when_previously_empty(
        self, client, seed_user, fake_db
    ):
        user = seed_user(device_id="device-123", push_token=None)

        response = client.post(
            MOBILE_LOGIN_URL,
            json={"device_id": "device-123", "push_token": "new-token"},
        )

        assert response.status_code == 200
        stored = (
            fake_db.collection(USERS_COLLECTION).document(user["id"]).get().to_dict()
        )
        assert stored["push_token"] == "new-token"

    def test_mobile_login_does_not_change_identical_push_token(
        self, client, seed_user, fake_db
    ):
        user = seed_user(device_id="device-123", push_token="same-token")

        response = client.post(
            MOBILE_LOGIN_URL,
            json={"device_id": "device-123", "push_token": "same-token"},
        )

        assert response.status_code == 200
        stored = (
            fake_db.collection(USERS_COLLECTION).document(user["id"]).get().to_dict()
        )
        assert stored["push_token"] == "same-token"

    def test_mobile_login_no_device_match_returns_404(self, client, fake_db):
        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "unknown-device"})

        assert response.status_code == 404

    def test_mobile_login_user_without_email_returns_null_email(
        self, client, seed_user
    ):
        seed_user(device_id="device-no-email", email=None)

        response = client.post(
            MOBILE_LOGIN_URL, json={"device_id": "device-no-email"}
        )

        assert response.status_code == 200
        assert response.json()["data"]["user"]["email"] is None

    def test_mobile_login_missing_device_id_returns_422(self, client, fake_db):
        response = client.post(MOBILE_LOGIN_URL, json={})

        assert response.status_code == 422

    def test_mobile_login_empty_device_id_returns_422(self, client, fake_db):
        response = client.post(MOBILE_LOGIN_URL, json={"device_id": ""})

        assert response.status_code == 422

    def test_mobile_login_does_not_require_authentication(self, client, seed_user):
        seed_user(device_id="device-123")

        # No Authorization header supplied at all; must not be rejected as
        # unauthenticated (i.e. must not be a 401).
        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "device-123"})

        assert response.status_code != 401


class TestCheckUserCode:
    """POST /auth/check-user-code"""

    def test_check_user_code_success_returns_200(self, client, seed_user):
        user = seed_user(security_code="1234")

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "1234", "device_id": "device-abc"},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["user"]["id"] == user["id"]
        assert data["access_token"]

    def test_check_user_code_pairs_device_and_push_token(
        self, client, seed_user, fake_db
    ):
        user = seed_user(security_code="1234")

        response = client.post(
            CHECK_USER_CODE_URL,
            json={
                "security_code": "1234",
                "device_id": "device-abc",
                "push_token": "push-xyz",
            },
        )

        assert response.status_code == 200
        stored = (
            fake_db.collection(USERS_COLLECTION).document(user["id"]).get().to_dict()
        )
        assert stored["device_id"] == "device-abc"
        assert stored["push_token"] == "push-xyz"

    def test_check_user_code_rotates_security_code(self, client, seed_user, fake_db):
        user = seed_user(security_code="1234")

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "1234", "device_id": "device-abc"},
        )

        assert response.status_code == 200
        stored = (
            fake_db.collection(USERS_COLLECTION).document(user["id"]).get().to_dict()
        )
        assert stored["security_code"] != "1234"

        # The old code can no longer be used to pair a (new) device.
        second_response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "1234", "device_id": "another-device"},
        )
        assert second_response.status_code == 404

    def test_check_user_code_no_match_returns_404(self, client, fake_db):
        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "9999", "device_id": "device-abc"},
        )

        assert response.status_code == 404

    def test_check_user_code_user_without_email_returns_null_email(
        self, client, seed_user
    ):
        seed_user(security_code="1234", email=None)

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "1234", "device_id": "device-abc"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["user"]["email"] is None

    def test_check_user_code_empty_security_code_returns_422(self, client, fake_db):
        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "", "device_id": "device-abc"},
        )

        assert response.status_code == 422

    def test_check_user_code_empty_device_id_returns_422(self, client, fake_db):
        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "1234", "device_id": ""},
        )

        assert response.status_code == 422

    def test_check_user_code_missing_fields_returns_422(self, client, fake_db):
        response = client.post(CHECK_USER_CODE_URL, json={})

        assert response.status_code == 422

    def test_check_user_code_does_not_require_authentication(
        self, client, seed_user
    ):
        seed_user(security_code="1234")

        # No Authorization header supplied at all; must not be rejected as
        # unauthenticated (i.e. must not be a 401).
        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "1234", "device_id": "device-abc"},
        )

        assert response.status_code != 401
