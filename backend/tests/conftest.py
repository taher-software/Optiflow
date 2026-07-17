"""Shared pytest fixtures for the API test suite.

Firestore is never hit for real: `get_db()` is monkeypatched, module-by-module,
to return a shared `FakeFirestore` instance (see `tests/fake_firestore.py`).
Each test gets a fresh instance (function-scoped `fake_db` fixture) so tests
are independent and can run in any order.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import src.app.core.deps as deps_module
import src.app.routers.uap.services as uap_services_module
from src.app.core.firestore import USERS_COLLECTION
from src.app.core.security import make_access_token
from src.app.main import app

from tests.fake_firestore import FakeFirestore
from tests.factories.user import UserFactory


@pytest.fixture
def fake_db(monkeypatch):
    """A fresh in-memory Firestore double, wired into every module that holds
    its own imported reference to `get_db` (each `from ... import get_db`
    binds its own name, so each call site must be patched individually)."""
    db = FakeFirestore()
    monkeypatch.setattr(deps_module, "get_db", lambda: db)
    monkeypatch.setattr(uap_services_module, "get_db", lambda: db)
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
def auth_headers():
    def _headers(user: dict) -> dict:
        token = make_access_token({"user_id": user["id"]})
        return {"Authorization": f"Bearer {token}"}

    return _headers
