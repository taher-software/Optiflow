"""Shared pytest fixtures for the API test suite.

Firestore is never hit for real: `get_firestore_client()` is monkeypatched,
module-by-module, to return a `FirestoreClient` wrapping a shared
`FakeFirestore` instance (see `tests/fake_firestore.py`). Each test gets a
fresh instance (function-scoped `fake_db` fixture) so tests are independent
and can run in any order.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import src.app.core.deps as deps_module
import src.app.routers.auth.services as auth_services_module
import src.app.routers.registration.services as registration_services_module
import src.app.routers.uap.services as uap_services_module
import src.app.routers.user.services as user_services_module
import src.app.routers.production_line.services as production_line_services_module
import src.app.routers.workstation.services as workstation_services_module
from src.app.core.firestore import (
    PRODUCTION_LINE_COLLECTION,
    UAP_COLLECTION,
    USERS_COLLECTION,
)
from src.app.core.security import make_access_token
from src.app.gcp.firestore import FirestoreClient
from src.app.main import app

from tests.fake_firestore import FakeFirestore
from tests.factories.production_line import ProductionLineDocFactory
from tests.factories.uap import UapDocFactory
from tests.factories.user import UserFactory


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
    monkeypatch.setattr(auth_services_module, "get_firestore_client", lambda: client)
    monkeypatch.setattr(
        registration_services_module, "get_firestore_client", lambda: client
    )
    monkeypatch.setattr(user_services_module, "get_firestore_client", lambda: client)
    return db


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
def auth_headers():
    def _headers(user: dict) -> dict:
        token = make_access_token({"user_id": user["id"]})
        return {"Authorization": f"Bearer {token}"}

    return _headers
