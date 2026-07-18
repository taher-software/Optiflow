import uuid
from typing import Any, Optional

from fastapi import HTTPException, status

from src.app.core.firestore import (
    PRODUCTION_LINE_COLLECTION,
    WORKSTATION_COLLECTION,
    get_db,
)

from src.app.routers.workstation.modelsIn import CreateWorkstationIn, UpdateWorkstationIn
from src.app.routers.workstation.modelsOut import WorkstationOut


def _to_out(station: dict[str, Any]) -> WorkstationOut:
    return WorkstationOut(
        id=station["id"],
        name=station.get("name", ""),
        description=station.get("description", ""),
        production_line_id=station.get("production_line_id"),
        type=station.get("type", ""),
        namespace_id=station.get("namespace_id", ""),
    )


def _validate_production_line_id(
    db: Any, namespace_id: str, production_line_id: str
) -> None:
    """Ensure `production_line_id` refers to an existing production line in
    the caller's namespace. Raises HTTPException(422) otherwise. Never lets a
    blank id reach the Firestore SDK (`.document("")` would otherwise blow up
    unhandled). Called only when a non-None value is supplied — `None` means
    independent workstation and is always valid."""
    if not production_line_id or not production_line_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="production_line_id: no such production line in this namespace.",
        )

    snapshot = db.collection(PRODUCTION_LINE_COLLECTION).document(production_line_id).get()
    line = snapshot.to_dict() or {} if snapshot.exists else None
    if not line or line.get("namespace_id") != namespace_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="production_line_id: no such production line in this namespace.",
        )


def create_workstation(payload: CreateWorkstationIn, namespace_id: str) -> WorkstationOut:
    db = get_db()

    if payload.production_line_id is not None:
        _validate_production_line_id(db, namespace_id, payload.production_line_id)

    station_id = str(uuid.uuid4())
    doc: dict[str, Any] = {
        "id": station_id,
        "name": payload.name,
        "description": payload.description,
        "production_line_id": payload.production_line_id,
        "type": payload.type.value,
        "namespace_id": namespace_id,
    }
    db.collection(WORKSTATION_COLLECTION).document(station_id).set(doc)
    return _to_out(doc)


def list_workstations(namespace_id: str) -> list[WorkstationOut]:
    db = get_db()
    rows = (
        db.collection(WORKSTATION_COLLECTION)
        .where("namespace_id", "==", namespace_id)
        .get()
    )
    return [_to_out(r.to_dict() or {}) for r in rows]


def _load_scoped(db: Any, station_id: str, namespace_id: str) -> dict[str, Any]:
    snapshot = db.collection(WORKSTATION_COLLECTION).document(station_id).get()
    station = snapshot.to_dict() or {} if snapshot.exists else {}
    if not station or station.get("namespace_id") != namespace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workstation not found."
        )
    return station


def get_workstation(station_id: str, namespace_id: str) -> WorkstationOut:
    return _to_out(_load_scoped(get_db(), station_id, namespace_id))


def update_workstation(
    station_id: str, payload: UpdateWorkstationIn, namespace_id: str
) -> WorkstationOut:
    db = get_db()
    station = _load_scoped(db, station_id, namespace_id)

    fields_set = payload.model_fields_set
    updates: dict[str, Any] = {}

    if "name" in fields_set and payload.name is not None:
        updates["name"] = payload.name
    if "description" in fields_set and payload.description is not None:
        updates["description"] = payload.description
    if "type" in fields_set and payload.type is not None:
        updates["type"] = payload.type.value
    if "production_line_id" in fields_set:
        new_line_id: Optional[str] = payload.production_line_id
        if new_line_id is not None:
            _validate_production_line_id(db, namespace_id, new_line_id)
        updates["production_line_id"] = new_line_id

    if updates:
        db.collection(WORKSTATION_COLLECTION).document(station_id).update(updates)
    return _to_out({**station, **updates})


def delete_workstation(station_id: str, namespace_id: str) -> WorkstationOut:
    db = get_db()
    station = _load_scoped(db, station_id, namespace_id)
    db.collection(WORKSTATION_COLLECTION).document(station_id).delete()
    return _to_out(station)
