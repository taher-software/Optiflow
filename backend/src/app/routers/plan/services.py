import uuid
from typing import Any

from fastapi import HTTPException, status

from src.app.core.firestore import NAMESPACE_COLLECTION, PLAN_COLLECTION
from src.app.core.naming import normalized_name
from src.app.gcp import get_firestore_client
from src.app.gcp.firestore import FirestoreClient

from src.app.routers.plan.modelsIn import CreatePlanIn, UpdatePlanIn
from src.app.routers.plan.modelsOut import PlanOut


def _to_out(plan: dict[str, Any]) -> PlanOut:
    return PlanOut(
        id=plan["id"],
        name=plan.get("name", ""),
        price=plan.get("price", 0.0),
        duration=plan.get("duration", 0),
        quota=plan.get("quota"),
    )


def _assert_plan_name_unique(
    client: FirestoreClient, name: str, *, exclude_id: str | None = None
) -> None:
    """Plans are a global (not tenant-scoped) collection, so uniqueness is
    checked across every plan, not per namespace — `core.naming.assert_name_unique`
    doesn't apply here since it always scopes to a `namespace_id`."""
    candidate = normalized_name(name)
    for doc in client.find_documents(PLAN_COLLECTION):
        if exclude_id is not None and doc.get("id") == exclude_id:
            continue
        if normalized_name(doc.get("name", "")) == candidate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A plan with this name already exists.",
            )


def create_plan(payload: CreatePlanIn) -> PlanOut:
    client = get_firestore_client()
    _assert_plan_name_unique(client, payload.name)

    plan_id = str(uuid.uuid4())
    doc: dict[str, Any] = {
        "id": plan_id,
        "name": payload.name.strip(),
        "price": payload.price,
        "duration": payload.duration,
        "quota": payload.quota,
    }
    client.create_document(PLAN_COLLECTION, doc, document_id=plan_id)
    return _to_out(doc)


def list_plans() -> list[PlanOut]:
    client = get_firestore_client()
    rows = client.find_documents(PLAN_COLLECTION)
    return sorted((_to_out(r) for r in rows), key=lambda p: p.name)


def _load(client: FirestoreClient, plan_id: str) -> dict[str, Any]:
    plan = client.get_document(PLAN_COLLECTION, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    return plan


def get_plan(plan_id: str) -> PlanOut:
    return _to_out(_load(get_firestore_client(), plan_id))


def update_plan(plan_id: str, payload: UpdatePlanIn) -> PlanOut:
    client = get_firestore_client()
    plan = _load(client, plan_id)

    fields_set = payload.model_fields_set
    updates: dict[str, Any] = {}

    if "name" in fields_set and payload.name is not None:
        _assert_plan_name_unique(client, payload.name, exclude_id=plan_id)
        updates["name"] = payload.name.strip()
    if "price" in fields_set and payload.price is not None:
        updates["price"] = payload.price
    if "duration" in fields_set and payload.duration is not None:
        updates["duration"] = payload.duration
    if "quota" in fields_set:
        # `quota` may be legitimately set to `None` (turning the plan back
        # into a base plan), so this branch is keyed off `model_fields_set`
        # alone, not off `payload.quota is not None` like the other fields.
        updates["quota"] = payload.quota

    if updates:
        client.update_document(PLAN_COLLECTION, plan_id, updates)
    return _to_out({**plan, **updates})


def _plan_in_use(client: FirestoreClient, plan_id: str) -> bool:
    return bool(
        client.find_documents(NAMESPACE_COLLECTION, {"subscription_plan_id": plan_id})
    ) or bool(
        client.find_documents(
            NAMESPACE_COLLECTION, {"extra_subscription_plan_id": plan_id}
        )
    )


def delete_plan(plan_id: str) -> PlanOut:
    client = get_firestore_client()
    plan = _load(client, plan_id)

    if _plan_in_use(client, plan_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This plan is in use by at least one namespace and cannot be deleted.",
        )

    client.delete_document(PLAN_COLLECTION, plan_id)
    return _to_out(plan)
