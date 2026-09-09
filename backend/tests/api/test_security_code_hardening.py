"""API tests for Work Unit `feature/strong-security-code`.

Covers the two changes described in the brief:

Change 1 -- new code format (`src/app/core/security_code.py::
generate_security_code`, format/uniqueness unit-tested directly in
`tests/core/test_security_code.py`). This file adds the parts that need HTTP:
  - `CheckUserCodeIn.security_code` (`src/app/routers/auth/modelsIn.py`)
    becomes `min_length=4, max_length=4`.
  - The three call sites (`routers/user/services.py::create_user`,
    `routers/registration/services.py::confirm_account`,
    `routers/auth/services.py::check_user_code` rotation) each produce a
    code in the new format.
  - Legacy 4-digit codes keep pairing (no migration).
  - A lowercase submission is normalised before lookup (one test, per the
    brief's own "low relevance" classification of this case).

Change 2 -- device lockout on failed pairing (new `temporary_connection`
Firestore collection, no constant yet in `src/app/core/firestore.py` since
the collection doesn't exist there yet -- the literal name from the brief is
used directly and only via `find_document`/`find_documents` field lookups,
never `.document(<assumed-id-scheme>)`, so these tests don't assume how the
implementation keys its documents).

Written test-first: neither the new `CheckUserCodeIn` length bounds nor any
lockout behavior exist yet, so every test below that targets them is
expected to fail on the missing behavior (see the per-class docstrings and
the hand-back for the precise reason). `POST /auth/check-user-code` is
unauthenticated by design (see `tests/api/test_auth_mobile.py`), so there is
no 401/403 scenario here either.

No real Firestore/network touched (`fake_db`, `seed_user`). The lockout
window (1 hour since `last_attempt_at`) is exercised by seeding
`temporary_connection` documents with a `last_attempt_at` computed relative
to the real wall clock (`datetime.now(timezone.utc) - timedelta(...)`)
rather than freezing time: the implementation doesn't exist yet so there is
no module to pin `datetime` on, and letting the implementation compare its
own real `now()` against a genuinely-past/genuinely-recent seeded timestamp
avoids coupling the test to which module ends up owning the lockout check.
No `sleep()` is used anywhere.
"""

import re
from datetime import datetime, timedelta, timezone

from src.app.core.firestore import USERS_COLLECTION
from src.app.core.security import make_confirmation_token, read_access_token
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import Role

import src.app.core.email as email_module
import src.app.routers.auth.services as auth_services_module

CHECK_USER_CODE_URL = "/auth/check-user-code"
USERS_URL = "/users"
REGISTRATION_CONFIRM_URL = "/registration/confirm"

TEMP_CONNECTION_COLLECTION = "temporary_connection"

# The 32-symbol unambiguous base32 alphabet from the contract, defined
# locally (not imported from `src/`).
CODE_ALPHABET_RE = re.compile(r"^[0-9A-HJ-KM-NP-TV-Z]{4}$")

# A role permitted to create users (owner/admin) -- see `test_user.py`.
NO_EMAIL_REQUIRED_ROLE = Role.PRODUCTION_AGENT.value


def _create_user_payload(**overrides):
    payload = {
        "first_name": "Alex",
        "last_name": "Martin",
        "role": NO_EMAIL_REQUIRED_ROLE,
    }
    payload.update(overrides)
    return payload


def _seed_temporary_connection(fake_db, device_id, **overrides):
    doc = {
        "device_id": device_id,
        "trial_number": 0,
        "blocked": False,
        "last_attempt_at": None,
    }
    doc.update(overrides)
    fake_db.collection(TEMP_CONNECTION_COLLECTION).document(device_id).set(doc)
    return doc


def _read_temporary_connection(fake_db, device_id):
    client = FirestoreClient(client=fake_db)
    return client.find_document(TEMP_CONNECTION_COLLECTION, {"device_id": device_id})


class _RecordingClient:
    """Wraps a real `FirestoreClient`; records every `find_document` call
    (collection name only, for the lockout short-circuit assertion) while
    delegating to the wrapped client so the request behaves normally."""

    def __init__(self, wrapped: FirestoreClient):
        self._wrapped = wrapped
        self.find_document_collections: list[str] = []

    def find_document(self, collection_name, params):
        self.find_document_collections.append(collection_name)
        return self._wrapped.find_document(collection_name, params)

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


class TestCheckUserCodeInLengthValidation:
    """Scenario 7 -- `CheckUserCodeIn.security_code` must be exactly 4
    characters. Today the field is `min_length=1` only, so a length != 4
    that isn't empty is currently accepted by validation (and then fails the
    lookup with a 404, never a 422) -- these tests are expected to fail on
    getting 404 back instead of 422."""

    def test_security_code_shorter_than_four_returns_422(self, client, fake_db):
        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "AB1", "device_id": "device-abc"},
        )

        assert response.status_code == 422

    def test_security_code_longer_than_four_returns_422(self, client, fake_db):
        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "AB123", "device_id": "device-abc"},
        )

        assert response.status_code == 422


class TestCheckUserCodeCaseAndLegacyHandling:
    """Scenario 8 (one test only, per the brief's low-relevance call) and
    scenario 9 (legacy 4-digit codes keep working, no migration)."""

    def test_lowercase_submitted_code_is_normalised_and_pairs(
        self, client, seed_user
    ):
        user = seed_user(security_code="AB3F")

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "ab3f", "device_id": "device-lower-1"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["user"]["id"] == user["id"]

    def test_legacy_four_digit_code_still_pairs(self, client, seed_user):
        """Non-regression pin: legacy digits are a subset of the new
        alphabet, so this already works and is expected to keep working."""
        user = seed_user(security_code="1234")

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "1234", "device_id": "device-legacy-1"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["user"]["id"] == user["id"]


class TestSecurityCodeFormatAtCallSites:
    """Scenario 6 -- all three call sites produce the new format.

    All three tests below already pass today: the current 4-decimal-digit
    format is a strict subset of the new 32-symbol alphabet, so a single
    sampled code from any call site trivially matches `CODE_ALPHABET_RE`
    even though the implementation hasn't actually widened the draw yet
    (mirrors `tests/core/test_security_code.py::
    TestGenerateSecurityCodeFormat`, which covers the same non-proof with a
    many-draw assertion instead). Kept here per the validated scenario list
    to pin the call sites once the widened alphabet lands; called out as
    already-green in the hand-back, not contrived to fail."""

    def test_user_creation_security_code_matches_new_format(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)

        response = client.post(
            USERS_URL, json=_create_user_payload(), headers=auth_headers(owner)
        )

        assert response.status_code == 201
        code = response.json()["data"]["security_code"]
        assert CODE_ALPHABET_RE.match(code), (
            f"expected a 4-char code from the unambiguous alphabet, got {code!r}"
        )

    def test_registration_confirm_security_code_matches_new_format(
        self, client, fake_db, seed_namespace, seed_user, monkeypatch
    ):
        welcome_calls = []
        monkeypatch.setattr(
            email_module,
            "send_welcome_email",
            lambda to, username, password: welcome_calls.append(to),
        )
        namespace = seed_namespace(confirmed=False)
        owner = seed_user(
            role=Role.OWNER.value,
            namespace_id=namespace["id"],
            password=None,
            email="owner@example.com",
        )
        token = make_confirmation_token(
            {"user_id": owner["id"], "namespace_id": namespace["id"]}
        )

        response = client.post(REGISTRATION_CONFIRM_URL, json={"token": token})

        assert response.status_code == 200
        stored = (
            fake_db.collection(USERS_COLLECTION).document(owner["id"]).get().to_dict()
        )
        code = stored["security_code"]
        assert CODE_ALPHABET_RE.match(code), (
            f"expected a 4-char code from the unambiguous alphabet, got {code!r}"
        )

    def test_check_user_code_rotation_security_code_matches_new_format(
        self, client, seed_user, fake_db
    ):
        user = seed_user(security_code="1234")

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "1234", "device_id": "device-rotate-1"},
        )

        assert response.status_code == 200
        stored = (
            fake_db.collection(USERS_COLLECTION).document(user["id"]).get().to_dict()
        )
        new_code = stored["security_code"]
        assert new_code != "1234"
        assert CODE_ALPHABET_RE.match(new_code), (
            f"expected a 4-char code from the unambiguous alphabet, got {new_code!r}"
        )


class TestCheckUserCodeNonRegression:
    """Scenario 18 -- the pairing flow still rotates the code and still
    returns a usable token. Non-regression pin: already passes today (the
    brief only adds a *format* to the rotated code and a *lockout* around
    failure, neither of which touches this)."""

    def test_successful_pairing_returns_a_usable_access_token(
        self, client, seed_user
    ):
        user = seed_user(security_code="1234")

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "1234", "device_id": "device-token-1"},
        )

        assert response.status_code == 200
        token = response.json()["data"]["access_token"]
        claims = read_access_token(token)
        assert claims["user_id"] == user["id"]


class TestCheckUserCodeLockout:
    """Scenarios 10-17 -- device lockout after 3 consecutive failed pairing
    attempts, a 1-hour lazily-evaluated expiry, and cleanup on success.

    None of this exists yet: every failed attempt today returns 404 with no
    `temporary_connection` side effect at all, and there is no 429 path.
    Every test below is expected to fail either on the response status
    (getting 404 where 429 is expected, or vice-versa) or on the seeded/
    read-back `temporary_connection` document never being written by
    production code -- except
    `test_successful_pairing_without_prior_document_does_not_error`
    (scenario 16), which already passes today: with no lockout code at all,
    a successful pairing trivially "does not error" and there is trivially
    no document to find afterwards. Called out as already-green in the
    hand-back, not contrived to fail.
    """

    def test_first_failed_attempt_returns_404_and_starts_the_counter(
        self, client, fake_db
    ):
        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "ZZZZ", "device_id": "device-lockout-1"},
        )

        assert response.status_code == 404
        doc = _read_temporary_connection(fake_db, "device-lockout-1")
        assert doc is not None
        assert doc["trial_number"] == 1
        assert doc["blocked"] is False

    def test_second_failed_attempt_reaches_trial_two_still_unblocked(
        self, client, fake_db
    ):
        device_id = "device-lockout-2"
        client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "ZZZZ", "device_id": device_id},
        )

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "ZZZZ", "device_id": device_id},
        )

        assert response.status_code == 404
        doc = _read_temporary_connection(fake_db, device_id)
        assert doc["trial_number"] == 2
        assert doc["blocked"] is False

    def test_third_failed_attempt_sets_blocked_true(self, client, fake_db):
        device_id = "device-lockout-3"
        for _ in range(2):
            client.post(
                CHECK_USER_CODE_URL,
                json={"security_code": "ZZZZ", "device_id": device_id},
            )

        client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "ZZZZ", "device_id": device_id},
        )

        doc = _read_temporary_connection(fake_db, device_id)
        assert doc["trial_number"] == 3
        assert doc["blocked"] is True

    def test_attempt_while_blocked_returns_429_without_user_lookup(
        self, client, fake_db, seed_user, monkeypatch
    ):
        device_id = "device-lockout-4"
        seed_user(security_code="AB3F")
        _seed_temporary_connection(
            fake_db,
            device_id,
            trial_number=3,
            blocked=True,
            last_attempt_at=datetime.now(timezone.utc).isoformat(),
        )
        real_client = FirestoreClient(client=fake_db)
        spy = _RecordingClient(real_client)
        monkeypatch.setattr(
            auth_services_module, "get_firestore_client", lambda: spy
        )

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "AB3F", "device_id": device_id},
        )

        assert response.status_code == 429
        assert USERS_COLLECTION not in spy.find_document_collections

    def test_attempt_after_expiry_is_allowed_and_counter_restarts(
        self, client, fake_db
    ):
        device_id = "device-lockout-5"
        _seed_temporary_connection(
            fake_db,
            device_id,
            trial_number=3,
            blocked=True,
            last_attempt_at=(
                datetime.now(timezone.utc) - timedelta(hours=1, minutes=1)
            ).isoformat(),
        )

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "ZZZZ", "device_id": device_id},
        )

        assert response.status_code == 404
        doc = _read_temporary_connection(fake_db, device_id)
        assert doc["blocked"] is False
        assert doc["trial_number"] == 1

    def test_attempt_within_the_hour_stays_blocked(self, client, fake_db):
        device_id = "device-lockout-6"
        _seed_temporary_connection(
            fake_db,
            device_id,
            trial_number=3,
            blocked=True,
            last_attempt_at=(
                datetime.now(timezone.utc) - timedelta(minutes=59)
            ).isoformat(),
        )

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "ZZZZ", "device_id": device_id},
        )

        assert response.status_code == 429

    def test_successful_pairing_deletes_temporary_connection_document(
        self, client, fake_db, seed_user
    ):
        device_id = "device-lockout-7"
        user = seed_user(security_code="AB3F")
        _seed_temporary_connection(
            fake_db, device_id, trial_number=1, blocked=False
        )

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "AB3F", "device_id": device_id},
        )

        assert response.status_code == 200
        assert response.json()["data"]["user"]["id"] == user["id"]
        assert _read_temporary_connection(fake_db, device_id) is None

    def test_successful_pairing_without_prior_document_does_not_error(
        self, client, fake_db, seed_user
    ):
        device_id = "device-lockout-8"
        seed_user(security_code="AB3F")

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "AB3F", "device_id": device_id},
        )

        assert response.status_code == 200
        assert _read_temporary_connection(fake_db, device_id) is None

    def test_two_devices_have_independent_counters(self, client, fake_db):
        device_a = "device-lockout-9a"
        device_b = "device-lockout-9b"
        for _ in range(2):
            client.post(
                CHECK_USER_CODE_URL,
                json={"security_code": "ZZZZ", "device_id": device_a},
            )

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "ZZZZ", "device_id": device_b},
        )

        assert response.status_code == 404
        doc_a = _read_temporary_connection(fake_db, device_a)
        doc_b = _read_temporary_connection(fake_db, device_b)
        assert doc_a["trial_number"] == 2
        assert doc_a["blocked"] is False
        assert doc_b["trial_number"] == 1
        assert doc_b["blocked"] is False
