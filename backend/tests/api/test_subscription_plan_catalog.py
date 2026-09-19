"""API tests for Work Unit `api.subscription_plan_catalog`.

Covers `src/app/routers/subscription/__init__.py::list_subscription_plans`
and `src/app/routers/subscription/services.py::list_catalog_plans`
(`GET /subscriptions/plans`), per `.claude/specs/subscription-paywall.md`
§1, plus a regression check that `POST /subscriptions` keeps its platform
API-key protection after the router-level dependency moved onto that route.
"""

from src.app.core.firestore import PLAN_COLLECTION

PLANS_URL = "/subscriptions/plans"
SUBSCRIPTIONS_URL = "/subscriptions"


def _seed_plan(fake_db, **overrides):
    plan = {
        "id": "plan_1",
        "name": "Pro",
        "price": 49.9,
        "duration": 30,
        "quota": None,
        "maintenance_price": None,
    }
    plan.update(overrides)
    fake_db.collection(PLAN_COLLECTION).document(plan["id"]).set(plan)
    return plan


class TestListSubscriptionPlans:
    """GET /subscriptions/plans"""

    def test_list_subscription_plans_unauthenticated_returns_401(
        self, client, fake_db
    ):
        response = client.get(PLANS_URL)

        assert response.status_code == 401

    def test_list_subscription_plans_returns_only_catalog_plans_in_order(
        self, client, fake_db, seed_user, auth_headers
    ):
        standard = _seed_plan(
            fake_db,
            id="plan_standard",
            name="Operio Standard",
            price=100.0,
            duration=365,
            quota=None,
            maintenance_price=20.0,
        )
        dedicated = _seed_plan(
            fake_db,
            id="plan_dedicated",
            name="  operio dedicated  ",
            price=500.0,
            duration=365,
            quota=None,
            maintenance_price=150.0,
        )
        intelligence = _seed_plan(
            fake_db,
            id="plan_intelligence",
            name="OPERIO INTELLIGENCE",
            price=80.0,
            duration=365,
            quota=1000,
            maintenance_price=None,
        )
        # Not part of the catalog: must not appear in the response.
        _seed_plan(fake_db, id="plan_other", name="Pro")

        caller = seed_user()

        response = client.get(PLANS_URL, headers=auth_headers(caller))

        assert response.status_code == 200
        data = response.json()["data"]
        assert [plan["id"] for plan in data] == [
            standard["id"],
            dedicated["id"],
            intelligence["id"],
        ]
        assert data[0] == {
            "id": standard["id"],
            "name": "Operio Standard",
            "price": 100.0,
            "duration": 365,
            "quota": None,
            "maintenance_price": 20.0,
        }
        assert data[1]["name"] == "  operio dedicated  "
        assert data[2]["quota"] == 1000

    def test_list_subscription_plans_missing_catalog_plan_is_absent(
        self, client, fake_db, seed_user, auth_headers
    ):
        standard = _seed_plan(
            fake_db, id="plan_standard", name="Operio Standard"
        )
        caller = seed_user()

        response = client.get(PLANS_URL, headers=auth_headers(caller))

        data = response.json()["data"]
        assert [plan["id"] for plan in data] == [standard["id"]]

    def test_list_subscription_plans_empty_catalog_returns_empty_list(
        self, client, fake_db, seed_user, auth_headers
    ):
        caller = seed_user()

        response = client.get(PLANS_URL, headers=auth_headers(caller))

        assert response.status_code == 200
        assert response.json()["data"] == []


class TestCreateSubscriptionStillRequiresApiKey:
    """POST /subscriptions -- regression: still platform-API-key protected
    after the router-level dependency moved onto this route."""

    def test_create_subscription_without_api_key_returns_401(self, client, fake_db):
        response = client.post(
            SUBSCRIPTIONS_URL,
            json={"namespace_id": "ns_1", "plan_name": "Pro"},
        )

        assert response.status_code == 401
