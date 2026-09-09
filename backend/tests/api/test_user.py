"""API tests for Work Unit `test.optional_uap_and_password`, CHANGE 2:
`CreateUserIn.password` (`src/app/routers/user/modelsIn.py`) becomes
conditional -- required only when `email` is set, optional otherwise.

No prior suite exercises `POST /users` at all (confirmed by search before
writing this file), so there is no existing file to append to; this is a new
file rather than a rewrite of frozen tests. Scope is deliberately limited to
the password/email interaction this Work Unit changes, plus the two
security-sensitive corollaries the brief calls out by name -- it is NOT a
full CRUD suite for `/users` (no list/get/update/delete coverage, no
cross-namespace coverage for `GET/PUT/DELETE /users/{id}`). A couple of cheap
auth-guard checks (401/403) are included because they cost nothing once the
endpoint is being exercised anyway, not because this Work Unit re-specifies
them.

Covers:
- `POST /users` (`src/app/routers/user/__init__.py::create_user` /
  `services.py::create_user`) for the password/email conditional.
- `POST /auth/check-user-code` (`src/app/routers/auth/__init__.py` /
  `services.py::check_user_code`) -- a passwordless user must still be able
  to pair a device. This already works today (the handler never reads
  `password`); the test pins it as a non-regression guard now that
  passwordless accounts become reachable through `POST /users` too.
- `POST /auth/login` (`services.py::login`) -- the security property named
  explicitly in the brief: a user document stored with no password hash must
  never grant a login token. Also already-passing today (existing `if not
  hashed: raise 403` branch); pinned here as a non-regression guard, not as
  new behavior.

Written test-first: `CreateUserIn.password` is still `str = Field(...,
min_length=6)` (unconditionally required) as of this revision, so every
"no email + no password" case below is expected to fail on that mandatory
field's `422`, never on a broken fixture. Tests for behavior that is
unaffected by this change (an email-required role still requiring email; a
supplied password's `min_length=6`; a supplied password being accepted even
with no email) already pass today and are called out as such in the
hand-back, not contrived to fail.

No real Firestore/network touched (`fake_db`, `seed_user`); no timestamps in
this contract, so time is not frozen here.
"""

import logging

from src.app.globals.enum import Role

USERS_URL = "/users"
LOGIN_URL = "/auth/login"
CHECK_USER_CODE_URL = "/auth/check-user-code"

# A role that does NOT require an email (EMAIL_REQUIRED_ROLES = admin,
# manager, and the three supervisor roles) -- the one
# `CreateUserIn.password` becomes optional for, absent an email.
NO_EMAIL_REQUIRED_ROLE = Role.PRODUCTION_AGENT.value
EMAIL_REQUIRED_ROLE = Role.ADMIN.value

# A role NOT permitted to manage users (create_user is owner/admin only),
# for the 403 test.
FORBIDDEN_ROLE = Role.MAINTENANCE_AGENT.value


def _payload(**overrides):
    payload = {
        "first_name": "Alex",
        "last_name": "Martin",
        "role": NO_EMAIL_REQUIRED_ROLE,
    }
    payload.update(overrides)
    return payload


class TestCreateUserPasswordOptionalWithoutEmail:
    """POST /users -- `password` is required when `email` is set, optional
    otherwise."""

    def test_create_user_without_email_and_without_password_returns_201(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)

        response = client.post(
            USERS_URL, json=_payload(), headers=auth_headers(owner)
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["email"] is None
        assert "password" not in data

    def test_create_user_without_email_with_valid_password_still_returns_201(
        self, client, seed_user, auth_headers
    ):
        """The developer explicitly chose NOT to forbid supplying a password
        when no email is given -- already works today, must keep working."""
        owner = seed_user(role=Role.OWNER.value)

        response = client.post(
            USERS_URL,
            json=_payload(password="s3cret1"),
            headers=auth_headers(owner),
        )

        assert response.status_code == 201
        assert response.json()["data"]["email"] is None

    def test_create_user_without_email_short_password_returns_422(
        self, client, seed_user, auth_headers
    ):
        """`min_length=6` still applies whenever a password IS supplied,
        even for a role that does not require one."""
        owner = seed_user(role=Role.OWNER.value)

        response = client.post(
            USERS_URL,
            json=_payload(password="abc"),
            headers=auth_headers(owner),
        )

        assert response.status_code == 422

    def test_create_user_with_email_and_password_returns_201(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)

        response = client.post(
            USERS_URL,
            json=_payload(
                role=EMAIL_REQUIRED_ROLE,
                email="new.admin@example.com",
                password="s3cret1",
            ),
            headers=auth_headers(owner),
        )

        assert response.status_code == 201
        assert response.json()["data"]["email"] == "new.admin@example.com"

    def test_create_user_with_email_and_without_password_returns_422(
        self, client, seed_user, auth_headers
    ):
        """Password becomes required the moment `email` is set, regardless
        of whether the role itself requires an email."""
        owner = seed_user(role=Role.OWNER.value)

        response = client.post(
            USERS_URL,
            json=_payload(email="agent@example.com"),
            headers=auth_headers(owner),
        )

        assert response.status_code == 422

    def test_create_user_email_required_role_without_email_returns_422(
        self, client, seed_user, auth_headers
    ):
        """The safety property: `EMAIL_REQUIRED_ROLES` already force an
        email, so those roles keep requiring a password transitively -- this
        pre-existing rule is untouched by this change."""
        owner = seed_user(role=Role.OWNER.value)

        response = client.post(
            USERS_URL,
            json=_payload(role=EMAIL_REQUIRED_ROLE, password="s3cret1"),
            headers=auth_headers(owner),
        )

        assert response.status_code == 422

    def test_create_user_unauthenticated_returns_401(self, client, fake_db):
        response = client.post(USERS_URL, json=_payload(password="s3cret1"))

        assert response.status_code == 401

    def test_create_user_forbidden_role_returns_403(
        self, client, seed_user, auth_headers
    ):
        agent = seed_user(role=FORBIDDEN_ROLE)

        response = client.post(
            USERS_URL,
            json=_payload(password="s3cret1"),
            headers=auth_headers(agent),
        )

        assert response.status_code == 403


class TestPasswordlessUserMobilePairing:
    """A user created without email/password must still get a security code
    and be able to pair a device via `POST /auth/check-user-code`."""

    def test_passwordless_user_is_created_with_a_security_code(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)

        response = client.post(
            USERS_URL, json=_payload(), headers=auth_headers(owner)
        )

        assert response.status_code == 201
        assert response.json()["data"]["security_code"]

    def test_passwordless_user_can_pair_device_via_check_user_code(
        self, client, seed_user
    ):
        """Already works today -- `check_user_code` never reads `password`
        -- pinned as a non-regression guard now that passwordless accounts
        become reachable through `POST /users` too."""
        worker = seed_user(
            role=NO_EMAIL_REQUIRED_ROLE,
            email=None,
            password=None,
            security_code="1234",
        )

        response = client.post(
            CHECK_USER_CODE_URL,
            json={"security_code": "1234", "device_id": "device-passwordless-1"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["user"]["id"] == worker["id"]


class TestPasswordlessAccountCannotBypassLogin:
    """Security pin named explicitly in the brief: a user document stored
    with no password hash must never grant a login token through `POST
    /auth/login`. Exercises the already-existing `if not hashed: raise 403`
    branch in `auth/services.py::login` -- already passes today, and stays
    green once the email/password conditional lands, as the non-regression
    guard the brief asks for."""

    def test_login_with_stored_passwordless_user_returns_403_not_200(
        self, client, seed_user
    ):
        seed_user(
            email="passwordless@example.com",
            password=None,
            role=NO_EMAIL_REQUIRED_ROLE,
        )

        response = client.post(
            LOGIN_URL,
            json={"username": "passwordless@example.com", "password": "anything1"},
        )

        assert response.status_code == 403

    def test_login_for_emailless_user_returns_401_not_found_by_username(
        self, client, seed_user
    ):
        """An emailless user cannot be looked up by `username` at all (the
        lookup is an exact `email` match), so no guessed username ever
        reaches their document -- the passwordless/emailless combo is simply
        unreachable from `/auth/login`, by construction."""
        seed_user(email=None, password=None, role=NO_EMAIL_REQUIRED_ROLE)

        response = client.post(
            LOGIN_URL,
            json={"username": "no-such-user@example.com", "password": "anything1"},
        )

        assert response.status_code == 401


# --------------------------------------------------------------------------
# Cross-cutting review fix #1 (test.review_fixes) — a passwordless user's
# `security_code` is now its SOLE credential, so `POST /auth/check-user-code`
# must never write the submitted code anywhere in the application logs.
# Unit-level coverage of the redaction itself lives in
# `tests/core/test_firestore_find_document_redaction.py`; this is the
# end-to-end scenario that actually matters.
#
# Written test-first: `FirestoreClient.find_document` does not redact
# anything today, so this is expected to fail on the submitted code being
# present in `caplog.text`, never on a broken fixture.
# --------------------------------------------------------------------------


class TestCheckUserCodeNeverLeaksCodeToLogs:
    def test_check_user_code_request_does_not_emit_submitted_code_in_logs(
        self, client, seed_user, caplog
    ):
        worker = seed_user(
            role=NO_EMAIL_REQUIRED_ROLE,
            email=None,
            password=None,
            security_code="7391",
        )

        with caplog.at_level(logging.INFO):
            response = client.post(
                CHECK_USER_CODE_URL,
                json={"security_code": "7391", "device_id": "device-log-leak-1"},
            )

        assert response.status_code == 200
        assert response.json()["data"]["user"]["id"] == worker["id"]
        assert "7391" not in caplog.text


# --------------------------------------------------------------------------
# Work Unit test.review_fixes, FIX 3 — `PUT /users/{id}` must not be able to
# create a state `POST /users` forbids: email set + no password. Today
# `update_user` (services.py:81-113) only re-checks the role->email rule, so
# a passwordless responder patched with just `{"email": "..."}` ends up with
# an email and no password -- a state creation refuses. That account then
# hits `login`'s 403 "Please confirm your account before signing in", which
# points at an owner/registration-only, unreachable flow for them.
#
# The fix: `update_user` rejects (422) whenever the RESULTING state -- the
# merge of the stored document and the payload -- has an email and no
# password, not just when the payload alone looks that way (a user who
# already has a stored password must still be updatable with only a new
# email).
#
# Written test-first: `update_user` does no such check today, so the
# "add email, no password" scenarios below are expected to fail on
# `response.status_code == 422` (the endpoint currently returns 200),
# never on a broken fixture.
# --------------------------------------------------------------------------


class TestUpdateUserCannotCreateEmailWithoutPasswordState:
    """PUT /users/{id} -- rejects a resulting state of email set + no
    password, computed from stored doc + payload merged, not payload alone."""

    def test_passwordless_user_email_only_update_returns_422(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        target = seed_user(
            namespace_id=owner["namespace_id"],
            role=NO_EMAIL_REQUIRED_ROLE,
            email=None,
            password=None,
        )

        response = client.put(
            f"{USERS_URL}/{target['id']}",
            json={"email": "new.email@example.com"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 422

    def test_passwordless_user_email_and_password_update_returns_200(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        target = seed_user(
            namespace_id=owner["namespace_id"],
            role=NO_EMAIL_REQUIRED_ROLE,
            email=None,
            password=None,
        )

        response = client.put(
            f"{USERS_URL}/{target['id']}",
            json={"email": "new.email@example.com", "password": "secret7"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        assert response.json()["data"]["email"] == "new.email@example.com"

    def test_user_with_stored_password_email_only_update_returns_200(
        self, client, seed_user, auth_headers
    ):
        """The case a payload-only check would wrongly reject: the target
        already HAS a stored password, so the merged/resulting state still
        satisfies the rule even though the payload alone carries only an
        email."""
        owner = seed_user(role=Role.OWNER.value)
        target = seed_user(
            namespace_id=owner["namespace_id"],
            role=NO_EMAIL_REQUIRED_ROLE,
            email=None,
            password="hashed-existing-password",
        )

        response = client.put(
            f"{USERS_URL}/{target['id']}",
            json={"email": "new.email@example.com"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        assert response.json()["data"]["email"] == "new.email@example.com"

    def test_passwordless_user_update_touching_neither_field_returns_200_unchanged(
        self, client, seed_user, auth_headers
    ):
        owner = seed_user(role=Role.OWNER.value)
        target = seed_user(
            namespace_id=owner["namespace_id"],
            role=NO_EMAIL_REQUIRED_ROLE,
            email=None,
            password=None,
            first_name="Original",
        )

        response = client.put(
            f"{USERS_URL}/{target['id']}",
            json={"first_name": "Updated"},
            headers=auth_headers(owner),
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["first_name"] == "Updated"
        assert data["email"] is None
