import uuid
from typing import Any, Optional

from fastapi import HTTPException, status

from src.app.core.archiving import is_active, now_iso_for_namespace
from src.app.core.firestore import (
    PRODUCTION_LINE_COLLECTION,
    WORKSTATION_COLLECTION,
)
from src.app.core.naming import assert_name_unique
from src.app.gcp import get_firestore_client
from src.app.gcp.firestore import FirestoreClient

from src.app.routers.workstation.modelsIn import CreateWorkstationIn, UpdateWorkstationIn
from src.app.routers.workstation.modelsOut import WorkstationArchiveOut, WorkstationOut


def _to_out(station: dict[str, Any]) -> WorkstationOut:
    return WorkstationOut(
        id=station["id"],
        name=station.get("name", ""),
        description=station.get("description", ""),
        production_line_id=station.get("production_line_id"),
        type=station.get("type", ""),
        namespace_id=station.get("namespace_id", ""),
        archived=not is_active(station),
    )


def _validate_production_line_id(
    client: FirestoreClient, namespace_id: str, production_line_id: str
) -> None:
    """Ensure `production_line_id` refers to an existing, active production
    line in the caller's namespace. Raises HTTPException(422) otherwise — an
    archived line is treated exactly like a nonexistent one, since
    attaching a new/updated workstation to an archived parent is rejected.
    Never lets a blank id reach the Firestore SDK (`.document("")` would
    otherwise blow up unhandled). Called only when a non-None value is
    supplied — `None` means independent workstation and is always valid."""
    if not production_line_id or not production_line_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="production_line_id: no such production line in this namespace.",
        )

    line = client.get_document(PRODUCTION_LINE_COLLECTION, production_line_id)
    if not line or line.get("namespace_id") != namespace_id or not is_active(line):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="production_line_id: no such production line in this namespace.",
        )


def create_workstation(payload: CreateWorkstationIn, namespace_id: str) -> WorkstationOut:
    client = get_firestore_client()

    if payload.production_line_id is not None:
        _validate_production_line_id(client, namespace_id, payload.production_line_id)
    assert_name_unique(
        client,
        WORKSTATION_COLLECTION,
        namespace_id,
        payload.name,
        resource_label="workstation",
    )

    station_id = str(uuid.uuid4())
    doc: dict[str, Any] = {
        "id": station_id,
        "name": payload.name,
        "description": payload.description,
        "production_line_id": payload.production_line_id,
        "type": payload.type.value,
        "namespace_id": namespace_id,
    }
    client.create_document(WORKSTATION_COLLECTION, doc, document_id=station_id)
    return _to_out(doc)


def list_workstations(namespace_id: str) -> list[WorkstationOut]:
    client = get_firestore_client()
    rows = client.find_documents(
        WORKSTATION_COLLECTION, {"namespace_id": namespace_id}
    )
    # Archived filter happens here, in Python — never as a Firestore `where`
    # (every pre-existing document has no `archived_at` key at all; see
    # `core.archiving`).
    return [_to_out(r) for r in rows if is_active(r)]


def _load_scoped(
    client: FirestoreClient,
    station_id: str,
    namespace_id: str,
    *,
    allow_archived: bool = False,
) -> dict[str, Any]:
    """Load a workstation scoped to `namespace_id`, 404ing on a missing id,
    a cross-namespace id, or (unless `allow_archived`) an archived one — an
    archived workstation behaves as not found from every angle except the
    archive endpoint itself, which needs to re-load it to stay idempotent."""
    station = client.get_document(WORKSTATION_COLLECTION, station_id)
    if not station or station.get("namespace_id") != namespace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workstation not found."
        )
    if not allow_archived and not is_active(station):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workstation not found."
        )
    return station


def get_workstation(station_id: str, namespace_id: str) -> WorkstationOut:
    return _to_out(_load_scoped(get_firestore_client(), station_id, namespace_id))


def update_workstation(
    station_id: str, payload: UpdateWorkstationIn, namespace_id: str
) -> WorkstationOut:
    client = get_firestore_client()
    station = _load_scoped(client, station_id, namespace_id)

    fields_set = payload.model_fields_set
    updates: dict[str, Any] = {}

    if "name" in fields_set and payload.name is not None:
        assert_name_unique(
            client,
            WORKSTATION_COLLECTION,
            namespace_id,
            payload.name,
            exclude_id=station_id,
            resource_label="workstation",
        )
        updates["name"] = payload.name
    if "description" in fields_set and payload.description is not None:
        updates["description"] = payload.description
    if "type" in fields_set and payload.type is not None:
        updates["type"] = payload.type.value
    if "production_line_id" in fields_set:
        new_line_id: Optional[str] = payload.production_line_id
        if new_line_id is not None:
            _validate_production_line_id(client, namespace_id, new_line_id)
        updates["production_line_id"] = new_line_id

    if updates:
        client.update_document(WORKSTATION_COLLECTION, station_id, updates)
    return _to_out({**station, **updates})


def delete_workstation(station_id: str, namespace_id: str) -> WorkstationArchiveOut:
    """Archives the workstation (irreversibly; there is no unarchive). A
    workstation has no children, so this never cascades. Idempotent:
    archiving an already-archived workstation returns 200 without touching
    its original `archived_at`."""
    client = get_firestore_client()
    station = _load_scoped(client, station_id, namespace_id, allow_archived=True)

    if not station.get("archived_at"):
        timestamp = now_iso_for_namespace(client, namespace_id)
        client.update_document(
            WORKSTATION_COLLECTION, station_id, {"archived_at": timestamp}
        )
        station = {**station, "archived_at": timestamp}

    return WorkstationArchiveOut(**_to_out(station).model_dump())
