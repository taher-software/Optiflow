"""Unit tests for `FirestoreClient.find_document`
(`src/app/gcp/firestore.py:188-190`) — cross-cutting review fix #1.

`find_document` currently logs `params` verbatim at INFO
(`f"Searching for document in collection '{collection_name}' with params:
{params}"`), which writes any sensitive lookup value (a mobile pairing
`security_code`, a `password`, a `device_id`) to Cloud Run logs in clear
text. This became more severe once a passwordless user's `security_code`
became its SOLE credential (`test_user.py`,
`TestPasswordlessUserMobilePairing`): anyone with log-viewer access could
replay it into `POST /auth/check-user-code` for a full access token.

The fix (decided by the developer, not re-litigated here): `find_document`
redacts the VALUE of a fixed set of sensitive field names — at least
`security_code`, `password`, `device_id` — while still logging the field
NAME, so the log stays useful for debugging which lookup ran. Non-sensitive
params (`email`, `namespace_id`, ...) must still log their value.

Exercises `FirestoreClient(client=FakeFirestore())` directly (no HTTP, no
`fake_db`/router fixtures needed) — this is a pure logging behavior of one
method. The end-to-end scenario (a real `/auth/check-user-code` request
never leaking the submitted code) is appended to `tests/api/test_user.py`,
next to the rest of the passwordless-account coverage.

Written test-first: `find_document` does no redaction today, so every
sensitive-field assertion below is expected to fail on the code VALUE being
present in `caplog.text`, never on a broken fixture. The non-sensitive-field
test already passes today (nothing to redact there) and is called out as
such in the hand-back.
"""

import logging

from tests.fake_firestore import FakeFirestore
from src.app.gcp.firestore import FirestoreClient
from src.app.core.firestore import USERS_COLLECTION


def _seeded_client():
    """A FirestoreClient wrapping a fake store with one seeded user document,
    so `find_document` has something to match against."""
    db = FakeFirestore()
    db.collection(USERS_COLLECTION).document("user-1").set(
        {
            "id": "user-1",
            "email": "alex@example.com",
            "namespace_id": "ns-1",
            "security_code": "4821",
            "password": "hashed-s3cret",
            "device_id": "device-abc-123",
        }
    )
    return FirestoreClient(client=db)


class TestFindDocumentRedactsSensitiveParamValues:
    """`find_document` must never log the VALUE of a sensitive param, while
    still logging its field name."""

    def test_security_code_value_is_redacted_but_field_name_is_logged(self, caplog):
        client = _seeded_client()

        with caplog.at_level(logging.INFO):
            client.find_document(USERS_COLLECTION, {"security_code": "4821"})

        assert "4821" not in caplog.text
        assert "security_code" in caplog.text

    def test_password_value_is_redacted_but_field_name_is_logged(self, caplog):
        client = _seeded_client()

        with caplog.at_level(logging.INFO):
            client.find_document(USERS_COLLECTION, {"password": "hashed-s3cret"})

        assert "hashed-s3cret" not in caplog.text
        assert "password" in caplog.text

    def test_device_id_value_is_redacted_but_field_name_is_logged(self, caplog):
        client = _seeded_client()

        with caplog.at_level(logging.INFO):
            client.find_document(USERS_COLLECTION, {"device_id": "device-abc-123"})

        assert "device-abc-123" not in caplog.text
        assert "device_id" in caplog.text

    def test_non_sensitive_param_value_is_still_logged(self, caplog):
        """The redaction must not blind the log entirely: an ordinary lookup
        field (e.g. `email`) still logs its value, which is what makes the
        log line useful for debugging."""
        client = _seeded_client()

        with caplog.at_level(logging.INFO):
            client.find_document(USERS_COLLECTION, {"email": "alex@example.com"})

        assert "alex@example.com" in caplog.text
        assert "email" in caplog.text

    def test_namespace_id_param_value_is_still_logged(self, caplog):
        client = _seeded_client()

        with caplog.at_level(logging.INFO):
            client.find_document(USERS_COLLECTION, {"namespace_id": "ns-1"})

        assert "ns-1" in caplog.text
        assert "namespace_id" in caplog.text
