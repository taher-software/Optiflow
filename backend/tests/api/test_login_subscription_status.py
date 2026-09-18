"""API tests for Work Unit `api.login_subscription_status`.

Covers `src/app/routers/auth/services.py::_build_login_out` (and its private
helper `_subscription_status`), shared by `/auth/login`, `/auth/mobile-login`
and `/auth/check-user-code`. Exercised here through `/auth/mobile-login`
(no password hashing involved, keeping the fixtures focused on the
subscription-status computation itself).

Only the base subscription (`subscription_plan_id`, `subscription_end_date`)
drives `warning`/`blocked`/`plan_id`/`plan_name` -- every `extra_*` field is
ignored (see `.claude/specs/subscription-plans.md`).

Time is frozen by monkeypatching `datetime` on the module under test (no
`freezegun` in this codebase) so "today" is deterministic regardless of the
machine's clock.
"""

from datetime import datetime, timezone

import src.app.routers.auth.services as auth_services_module
from src.app.core.firestore import PLAN_COLLECTION

MOBILE_LOGIN_URL = "/auth/mobile-login"

# Frozen "today" for every test in this module: 2026-09-18, matching the
# namespace's default UTC timezone (see `NamespaceDocFactory.timezone = None`).
_TODAY = "2026-09-18"


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 9, 18, 10, 0, tzinfo=tz or timezone.utc)


def _freeze_today(monkeypatch):
    monkeypatch.setattr(auth_services_module, "datetime", _FixedDatetime)


def _seed_plan(fake_db, **overrides):
    plan = {
        "id": "plan_1",
        "name": "Pro",
        "price": 49.9,
        "duration": 30,
        "quota": None,
    }
    plan.update(overrides)
    fake_db.collection(PLAN_COLLECTION).document(plan["id"]).set(plan)
    return plan


class TestLoginSubscriptionStatus:
    """POST /auth/mobile-login -- root-level warning/blocked/plan_id/plan_name."""

    def test_login_active_subscription_returns_no_warning_or_block(
        self, client, seed_user, seed_namespace, fake_db, monkeypatch
    ):
        _freeze_today(monkeypatch)
        plan = _seed_plan(fake_db)
        namespace = seed_namespace(
            subscription_plan_id=plan["id"], subscription_end_date=_TODAY
        )
        seed_user(device_id="device-1", namespace_id=namespace["id"])

        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "device-1"})

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["warning"] is None
        assert data["blocked"] is None
        assert data["plan_id"] == plan["id"]
        assert data["plan_name"] == plan["name"]

    def test_login_one_day_expired_returns_warning_not_blocked(
        self, client, seed_user, seed_namespace, fake_db, monkeypatch
    ):
        _freeze_today(monkeypatch)
        plan = _seed_plan(fake_db)
        namespace = seed_namespace(
            subscription_plan_id=plan["id"], subscription_end_date="2026-09-17"
        )
        seed_user(device_id="device-1", namespace_id=namespace["id"])

        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "device-1"})

        data = response.json()["data"]
        assert data["warning"] is True
        assert data["blocked"] is False

    def test_login_twenty_nine_days_expired_returns_warning_not_blocked(
        self, client, seed_user, seed_namespace, fake_db, monkeypatch
    ):
        _freeze_today(monkeypatch)
        plan = _seed_plan(fake_db)
        namespace = seed_namespace(
            subscription_plan_id=plan["id"], subscription_end_date="2026-08-20"
        )
        seed_user(device_id="device-1", namespace_id=namespace["id"])

        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "device-1"})

        data = response.json()["data"]
        assert data["warning"] is True
        assert data["blocked"] is False

    def test_login_thirty_days_expired_returns_blocked_not_warning(
        self, client, seed_user, seed_namespace, fake_db, monkeypatch
    ):
        _freeze_today(monkeypatch)
        plan = _seed_plan(fake_db)
        namespace = seed_namespace(
            subscription_plan_id=plan["id"], subscription_end_date="2026-08-19"
        )
        seed_user(device_id="device-1", namespace_id=namespace["id"])

        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "device-1"})

        data = response.json()["data"]
        assert data["warning"] is False
        assert data["blocked"] is True
        # plan_id/plan_name are still returned even though the base
        # subscription is expired.
        assert data["plan_id"] == plan["id"]
        assert data["plan_name"] == plan["name"]

    def test_login_no_subscription_returns_all_null(
        self, client, seed_user, seed_namespace, monkeypatch
    ):
        _freeze_today(monkeypatch)
        namespace = seed_namespace()
        seed_user(device_id="device-1", namespace_id=namespace["id"])

        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "device-1"})

        data = response.json()["data"]
        assert data["warning"] is None
        assert data["blocked"] is None
        assert data["plan_id"] is None
        assert data["plan_name"] is None

    def test_login_extra_only_subscription_is_ignored(
        self, client, seed_user, seed_namespace, fake_db, monkeypatch
    ):
        _freeze_today(monkeypatch)
        plan = _seed_plan(fake_db, id="plan_extra", quota=500)
        namespace = seed_namespace(
            extra_subscription_plan_id=plan["id"],
            extra_subscription_end_date="2026-08-01",
            oiu_generated=500,
        )
        seed_user(device_id="device-1", namespace_id=namespace["id"])

        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "device-1"})

        data = response.json()["data"]
        assert data["warning"] is None
        assert data["blocked"] is None
        assert data["plan_id"] is None
        assert data["plan_name"] is None

    def test_login_plan_name_maps_from_plan_collection(
        self, client, seed_user, seed_namespace, fake_db, monkeypatch
    ):
        _freeze_today(monkeypatch)
        plan = _seed_plan(fake_db, id="plan_pro", name="Pro Plan")
        namespace = seed_namespace(
            subscription_plan_id=plan["id"], subscription_end_date=_TODAY
        )
        seed_user(device_id="device-1", namespace_id=namespace["id"])

        response = client.post(MOBILE_LOGIN_URL, json={"device_id": "device-1"})

        data = response.json()["data"]
        assert data["plan_id"] == "plan_pro"
        assert data["plan_name"] == "Pro Plan"
