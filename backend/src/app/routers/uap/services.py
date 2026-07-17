import uuid
from typing import Any

from fastapi import HTTPException, status

from src.app.core.firestore import UAP_COLLECTION, USERS_COLLECTION, get_db
from src.app.globals.enum import Role

from src.app.routers.uap.modelsIn import CreateUapIn, UpdateUapIn
from src.app.routers.uap.modelsOut import UapOut

# Maps each UAP id-list field to the role its members must hold. Sourced from
# the single Role enum (globals/enum/roles.py) rather than hardcoded strings.
_LIST_ROLE_MAP: dict[str, Role] = {
    "maintenance_agent_ids": Role.MAINTENANCE_AGENT,
    "production_agent_ids": Role.PRODUCTION_AGENT,
    "quality_agent_ids": Role.QUALITY_AGENT,
    "logistic_agent_ids": Role.LOGISTIC_AGENT,
    "logistic_supervisor_ids": Role.LOGISTIC_SUPERVISOR,
    "maintenance_supervisor_ids": Role.MAINTENANCE_SUPERVISOR,
    "quality_supervisor_ids": Role.QUALITY_SUPERVISOR,
    "production_supervisor_ids": Role.PRODUCTION_SUPERVISOR,
}


def _to_out(uap: dict[str, Any]) -> UapOut:
    return UapOut(
        id=uap["id"],
        name=uap.get("name", ""),
        description=uap.get("description", ""),
        namespace_id=uap.get("namespace_id", ""),
        maintenance_agent_ids=uap.get("maintenance_agent_ids", []),
        production_agent_ids=uap.get("production_agent_ids", []),
        quality_agent_ids=uap.get("quality_agent_ids", []),
        logistic_agent_ids=uap.get("logistic_agent_ids", []),
        logistic_supervisor_ids=uap.get("logistic_supervisor_ids", []),
        maintenance_supervisor_ids=uap.get("maintenance_supervisor_ids", []),
        quality_supervisor_ids=uap.get("quality_supervisor_ids", []),
        production_supervisor_ids=uap.get("production_supervisor_ids", []),
    )


def _dedupe(ids: list[str]) -> list[str]:
    seen: list[str] = []
    for i in ids:
        if i not in seen:
            seen.append(i)
    return seen


def _validate_id_lists(
    db: Any, namespace_id: str, lists: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Validate that every id in each list refers to an existing user in the
    same namespace with the matching role. Returns the de-duplicated lists.
    Raises HTTPException(422) naming the offending list on any violation.

    Reads are batched: one `db.get_all(...)` round-trip for the union of all
    (de-duplicated) ids across the 8 lists, instead of one `.get()` per id."""
    deduped: dict[str, list[str]] = {field: _dedupe(ids) for field, ids in lists.items()}

    # Reject empty/blank ids up front, as part of the same 422 validation
    # path (an empty document id would otherwise reach the Firestore SDK and
    # blow up with an unhandled error).
    for field, ids in deduped.items():
        for user_id in ids:
            if not user_id or not user_id.strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{field}: id must not be empty.",
                )

    all_ids = sorted({user_id for ids in deduped.values() for user_id in ids})
    users_by_id: dict[str, dict[str, Any]] = {}
    if all_ids:
        refs = [db.collection(USERS_COLLECTION).document(uid) for uid in all_ids]
        for snapshot in db.get_all(refs):
            if snapshot.exists:
                users_by_id[snapshot.id] = snapshot.to_dict() or {}

    for field, ids in deduped.items():
        expected_role = _LIST_ROLE_MAP[field]
        for user_id in ids:
            user = users_by_id.get(user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"{field}: user '{user_id}' does not exist."
                    ),
                )
            if user.get("namespace_id") != namespace_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"{field}: user '{user_id}' does not belong to this namespace."
                    ),
                )
            if user.get("role") != expected_role.value:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"{field}: user '{user_id}' does not have the "
                        f"'{expected_role.value}' role."
                    ),
                )
    return deduped


def create_uap(payload: CreateUapIn, namespace_id: str) -> UapOut:
    db = get_db()

    id_lists = {
        field: getattr(payload, field) for field in _LIST_ROLE_MAP
    }
    validated_lists = _validate_id_lists(db, namespace_id, id_lists)

    uap_id = str(uuid.uuid4())
    doc: dict[str, Any] = {
        "id": uap_id,
        "name": payload.name,
        "description": payload.description,
        "namespace_id": namespace_id,
        **validated_lists,
    }
    db.collection(UAP_COLLECTION).document(uap_id).set(doc)
    return _to_out(doc)


def list_uaps(namespace_id: str) -> list[UapOut]:
    db = get_db()
    rows = (
        db.collection(UAP_COLLECTION)
        .where("namespace_id", "==", namespace_id)
        .get()
    )
    return [_to_out(r.to_dict() or {}) for r in rows]


def _load_scoped(db: Any, uap_id: str, namespace_id: str) -> dict[str, Any]:
    snapshot = db.collection(UAP_COLLECTION).document(uap_id).get()
    uap = snapshot.to_dict() or {} if snapshot.exists else {}
    if not uap or uap.get("namespace_id") != namespace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="UAP not found."
        )
    return uap


def get_uap(uap_id: str, namespace_id: str) -> UapOut:
    return _to_out(_load_scoped(get_db(), uap_id, namespace_id))


def update_uap(uap_id: str, payload: UpdateUapIn, namespace_id: str) -> UapOut:
    db = get_db()
    uap = _load_scoped(db, uap_id, namespace_id)

    provided_lists = {
        field: getattr(payload, field)
        for field in _LIST_ROLE_MAP
        if getattr(payload, field) is not None
    }
    validated_lists = _validate_id_lists(db, namespace_id, provided_lists)

    updates: dict[str, Any] = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.description is not None:
        updates["description"] = payload.description
    updates.update(validated_lists)

    if updates:
        db.collection(UAP_COLLECTION).document(uap_id).update(updates)
    return _to_out({**uap, **updates})


def delete_uap(uap_id: str, namespace_id: str) -> UapOut:
    db = get_db()
    uap = _load_scoped(db, uap_id, namespace_id)
    db.collection(UAP_COLLECTION).document(uap_id).delete()
    return _to_out(uap)
