import datetime
from typing import Any, Optional

from fastapi import HTTPException, status

from src.app.core.firestore import NAMESPACE_COLLECTION, PLAN_COLLECTION
from src.app.core.naming import normalized_name
from src.app.core.timezone import namespace_timezone
from src.app.gcp import get_firestore_client
from src.app.gcp.firestore import FirestoreClient

from src.app.routers.subscription.modelsIn import CreateSubscriptionIn
from src.app.routers.subscription.modelsOut import SubscriptionOut

_SUBSCRIPTION_FIELDS = (
    "subscription_plan_id",
    "subscription_start_date",
    "subscription_end_date",
    "extra_subscription_plan_id",
    "extra_subscription_start_date",
    "extra_subscription_end_date",
    "oiu_generated",
)


def _find_plan_by_name(client: FirestoreClient, plan_name: str) -> dict[str, Any]:
    candidate = normalized_name(plan_name)
    for doc in client.find_documents(PLAN_COLLECTION):
        if normalized_name(doc.get("name", "")) == candidate:
            return doc
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="plan_name: no such plan.",
    )


def _parse_date(value: Optional[str]) -> Optional[datetime.date]:
    if not value:
        return None
    return datetime.date.fromisoformat(value)


def create_subscription(payload: CreateSubscriptionIn) -> SubscriptionOut:
    client = get_firestore_client()

    namespace = client.get_document(NAMESPACE_COLLECTION, payload.namespace_id)
    if not namespace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Namespace not found."
        )

    plan = _find_plan_by_name(client, payload.plan_name)

    is_extra = plan.get("quota") is not None
    prefix = "extra_subscription_" if is_extra else "subscription_"

    today = datetime.datetime.now(namespace_timezone(payload.namespace_id, namespace)).date()

    current_end = _parse_date(namespace.get(f"{prefix}end_date"))

    if payload.today_start_day or current_end is None:
        start_date = today
    else:
        start_date = current_end + datetime.timedelta(days=1)
    end_date = start_date + datetime.timedelta(days=plan["duration"])

    updates: dict[str, Any] = {
        f"{prefix}plan_id": plan["id"],
        f"{prefix}start_date": start_date.isoformat(),
        f"{prefix}end_date": end_date.isoformat(),
    }

    if is_extra:
        # Evaluated against the PREVIOUS extra_subscription_end_date, i.e.
        # `current_end` computed above, before this update overwrites it: a
        # still-active extra subscription accumulates its quota, an expired
        # (or absent) one starts over from the plan's quota.
        previous_oiu = namespace.get("oiu_generated")
        if current_end is not None and current_end > today:
            updates["oiu_generated"] = (previous_oiu or 0) + plan["quota"]
        else:
            updates["oiu_generated"] = plan["quota"]

    client.update_document(NAMESPACE_COLLECTION, payload.namespace_id, updates)

    final_state = {**{f: namespace.get(f) for f in _SUBSCRIPTION_FIELDS}, **updates}

    return SubscriptionOut(
        namespace_id=payload.namespace_id,
        plan_id=plan["id"],
        plan_name=plan.get("name", ""),
        is_extra=is_extra,
        **final_state,
    )
