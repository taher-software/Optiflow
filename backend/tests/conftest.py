"""Shared pytest fixtures for the API test suite.

Firestore is never hit for real: `get_firestore_client()` is monkeypatched,
module-by-module, to return a `FirestoreClient` wrapping a shared
`FakeFirestore` instance (see `tests/fake_firestore.py`). Each test gets a
fresh instance (function-scoped `fake_db` fixture) so tests are independent
and can run in any order.
"""

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import src.app.core.deps as deps_module
import src.app.core.email as email_module
import src.app.core.push as push_module
import src.app.routers.auth.services as auth_services_module
import src.app.routers.down_time.services as down_time_services_module
import src.app.routers.kpi.services as kpi_services_module
import src.app.routers.registration.services as registration_services_module
import src.app.routers.subscription.services as subscription_services_module
import src.app.routers.uap.services as uap_services_module
import src.app.routers.user.services as user_services_module
import src.app.routers.production_line.services as production_line_services_module
import src.app.routers.settings.services as settings_services_module
import src.app.routers.workstation.services as workstation_services_module
from src.app.core.firestore import (
    NAMESPACE_COLLECTION,
    PRODUCTION_LINE_COLLECTION,
    UAP_COLLECTION,
    USERS_COLLECTION,
    WORKSTATION_COLLECTION,
)
from src.app.core.security import make_access_token
from src.app.gcp.firestore import FirestoreClient
from src.app.main import app

# `add_down_time` is re-exported by the `src.app.async_jobs` package
# (`__init__.py: from .add_down_time import add_down_time`), so patching the
# name off the package would rebind the package's own imported reference, not
# the one `add_down_time()` actually calls at runtime. Import the submodule
# directly so the patch lands on the name the function body resolves.
add_down_time_module = importlib.import_module("src.app.async_jobs.add_down_time")

from tests.fake_firestore import FakeFirestore
from tests.factories.namespace import NamespaceDocFactory
from tests.factories.production_line import ProductionLineDocFactory
from tests.factories.uap import UapDocFactory
from tests.factories.user import UserFactory
from tests.factories.workstation import WorkstationDocFactory


@pytest.fixture
def fake_db(monkeypatch):
    """A fresh in-memory Firestore double, wired into every module that holds
    its own imported reference to `get_firestore_client` (each
    `from ... import get_firestore_client` binds its own name, so each call
    site must be patched individually). The raw `FakeFirestore` is wrapped in
    a real `FirestoreClient` so services exercise the actual client methods
    (`find_document`, `get_documents`, ...) against the fake, and exposed
    directly (not the wrapper) so `seed_*` fixtures can keep writing through
    the raw `collection(...).document(...).set(...)` surface."""
    db = FakeFirestore()
    client = FirestoreClient(client=db)
    monkeypatch.setattr(deps_module, "get_firestore_client", lambda: client)
    monkeypatch.setattr(uap_services_module, "get_firestore_client", lambda: client)
    monkeypatch.setattr(
        production_line_services_module, "get_firestore_client", lambda: client
    )
    monkeypatch.setattr(
        workstation_services_module, "get_firestore_client", lambda: client
    )
    monkeypatch.setattr(
        settings_services_module, "get_firestore_client", lambda: client
    )
    monkeypatch.setattr(auth_services_module, "get_firestore_client", lambda: client)
    monkeypatch.setattr(
        registration_services_module, "get_firestore_client", lambda: client
    )
    monkeypatch.setattr(
        subscription_services_module, "get_firestore_client", lambda: client
    )
    monkeypatch.setattr(user_services_module, "get_firestore_client", lambda: client)
    monkeypatch.setattr(
        down_time_services_module, "get_firestore_client", lambda: client
    )
    monkeypatch.setattr(
        kpi_services_module, "get_firestore_client", lambda: client
    )
    # The worker route runs `add_down_time` (via the registry) with the same
    # fake — its own `get_firestore_client` reference must be patched too (via
    # the submodule, not the package re-export; see the import comment above).
    monkeypatch.setattr(
        add_down_time_module, "get_firestore_client", lambda: client
    )
    return db


@pytest.fixture
def publish_spy(monkeypatch):
    """Replace the Pub/Sub publisher used by the down_time create endpoint with
    a spy, so `POST /down-times` records the published job instead of hitting
    real Pub/Sub. Returns the list of recorded publish calls."""
    calls: list[dict] = []

    class _FakePublisher:
        def publish_job(self, job_type, namespace_id, payload, job_id=None):
            calls.append(
                {
                    "job_type": job_type,
                    "namespace_id": namespace_id,
                    "payload": payload,
                    "job_id": job_id,
                }
            )
            return "fake-message-id"

    monkeypatch.setattr(
        down_time_services_module, "get_pubsub_publisher", lambda: _FakePublisher()
    )
    return calls


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def seed_user(fake_db):
    """Factory fixture: seed_user(role=..., namespace_id=...) -> user dict."""

    def _seed(**overrides) -> dict:
        user = UserFactory(**overrides)
        fake_db.collection(USERS_COLLECTION).document(user["id"]).set(user)
        return user

    return _seed


@pytest.fixture
def seed_uap(fake_db):
    """Factory fixture: seed_uap(namespace_id=...) -> UAP doc dict, seeded
    directly into the fake Firestore `uap` collection (bypasses the /uaps
    endpoint since these tests exercise production_line/workstation, not UAP
    itself)."""

    def _seed(**overrides) -> dict:
        uap = UapDocFactory(**overrides)
        fake_db.collection(UAP_COLLECTION).document(uap["id"]).set(uap)
        return uap

    return _seed


@pytest.fixture
def seed_production_line(fake_db):
    """Factory fixture: seed_production_line(namespace_id=..., uap_id=...) ->
    production line doc dict, seeded directly into the fake Firestore
    `production_line` collection."""

    def _seed(**overrides) -> dict:
        line = ProductionLineDocFactory(**overrides)
        fake_db.collection(PRODUCTION_LINE_COLLECTION).document(line["id"]).set(line)
        return line

    return _seed


@pytest.fixture
def seed_workstation(fake_db):
    """Factory fixture: seed_workstation(namespace_id=..., production_line_id=...)
    -> workstation doc dict, seeded directly into the fake Firestore
    `workstation` collection."""

    def _seed(**overrides) -> dict:
        station = WorkstationDocFactory(**overrides)
        fake_db.collection(WORKSTATION_COLLECTION).document(station["id"]).set(
            station
        )
        return station

    return _seed


@pytest.fixture
def seed_namespace(fake_db):
    """Factory fixture: seed_namespace(id=..., timezone=...) -> namespace doc
    dict, seeded directly into the fake Firestore `namespace` collection
    (used by `add_down_time` handler tests to control the tenant's IANA
    timezone)."""

    def _seed(**overrides) -> dict:
        namespace = NamespaceDocFactory(**overrides)
        fake_db.collection(NAMESPACE_COLLECTION).document(namespace["id"]).set(
            namespace
        )
        return namespace

    return _seed


@pytest.fixture
def auth_headers():
    def _headers(user: dict) -> dict:
        token = make_access_token({"user_id": user["id"]})
        return {"Authorization": f"Bearer {token}"}

    return _headers


# Egress attempts recorded during the current test. Raising from the guard is
# NOT enough on its own: both `core.push.send_push_notification` and the
# per-recipient email loops catch `Exception` broadly by design (a failed
# notification must never break a request or a job), so they swallow the
# guard's `AssertionError` into a warning log and the test still passes green
# — the exact silent-discipline failure this guard exists to end. The
# `_no_real_network` fixture therefore also asserts this list is empty at
# teardown, which production code cannot swallow.
_BLOCKED_EGRESS: list[str] = []


class _BlockedRequests:
    """Stand-in for the `requests` module name inside `src.app.core.push`:
    any attempted HTTP verb records the attempt and raises, naming the call."""

    def __getattr__(self, verb: str):
        def _blocked(url, *args, **kwargs):
            message = (
                f"requests.{verb}({url!r}) from "
                "src.app.core.push.send_push_notification — reaching the Expo "
                "push API is never allowed in tests. Add/use the `push_spy` "
                "fixture (monkeypatch `send_push_notifications`/"
                "`send_push_notification` on the module under test)."
            )
            _BLOCKED_EGRESS.append(message)
            raise AssertionError(f"Test attempted a real network call: {message}")

        return _blocked


def _blocked_email_send(to: str, subject: str, html: str) -> None:
    message = (
        f"src.app.core.email._send(to={to!r}, subject={subject!r}) (Resend) — "
        "reaching Resend is never allowed in tests. Add/use the `email_spy` "
        "fixture (monkeypatch the relevant `send_*_email` function on the "
        "module under test)."
    )
    _BLOCKED_EGRESS.append(message)
    raise AssertionError(f"Test attempted a real network call: {message}")


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Backstop against genuine outbound network calls, patched at the two
    real egress choke points rather than the caller-facing helpers:
    `src.app.core.push`'s `requests` and `src.app.core.email._send`. Every
    push/email sender funnels through one of these two, regardless of which
    module imported the caller-facing helper (`send_push_notifications`,
    `send_down_time_escalation_email`, ...) into its own namespace, because
    those helpers resolve `requests`/`_send` from their *own* defining
    module's globals — not the caller's.

    This is a backstop beneath the existing per-test `push_spy`/`email_spy`
    fixtures, not a replacement: those patch the caller-facing helper
    directly (e.g. `add_down_time_module.send_push_notifications`) so they
    intercept first and this fixture's patched `requests`/`_send` is simply
    never reached in that case. A test that seeds a push token/email and
    forgets to request a spy now fails loudly here instead of silently
    hitting (or best-effort-swallowing a failed hit to) the real network.
    """
    _BLOCKED_EGRESS.clear()
    monkeypatch.setattr(push_module, "requests", _BlockedRequests())
    monkeypatch.setattr(email_module, "_send", _blocked_email_send)

    yield

    if _BLOCKED_EGRESS:
        attempts = "\n  - ".join(_BLOCKED_EGRESS)
        _BLOCKED_EGRESS.clear()
        raise AssertionError(
            "This test reached a real network egress point. It was blocked, "
            "but the production sender swallowed the error by design, so the "
            "test would otherwise have passed silently:\n  - " + attempts
        )
