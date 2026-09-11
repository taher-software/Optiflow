import uuid
from typing import Any, Optional

from fastapi import HTTPException, status

from src.app.core.archiving import (
    cancel_ticket_escalations_on_archive,
    is_active,
    now_iso_for_namespace,
)
from src.app.core.escalation import cancel_escalation
from src.app.core.firestore import (
    PRODUCTION_LINE_COLLECTION,
    UAP_COLLECTION,
    WORKSTATION_COLLECTION,
)
from src.app.core.naming import assert_name_unique
from src.app.gcp import get_firestore_client
from src.app.gcp.firestore import FirestoreClient

from src.app.routers.production_line.modelsIn import (
    CreateProductionLineIn,
    UpdateProductionLineIn,
)
from src.app.routers.production_line.modelsOut import (
    ProductionLineArchiveOut,
    ProductionLineOut,
)


def _to_out(line: dict[str, Any]) -> ProductionLineOut:
    return ProductionLineOut(
        id=line["id"],
        name=line.get("name", ""),
        description=line.get("description", ""),
        uap_id=line.get("uap_id"),
        namespace_id=line.get("namespace_id", ""),
        archived=not is_active(line),
    )


def _validate_uap_id(client: FirestoreClient, namespace_id: str, uap_id: str) -> None:
    """Ensure `uap_id` refers to an existing, active UAP in the caller's
    namespace. Raises HTTPException(422) otherwise — an archived UAP is
    treated exactly like a nonexistent one, since attaching a new/updated
    line to an archived parent is rejected. Never lets a blank id reach the
    Firestore SDK (`.document("")` would otherwise blow up unhandled).
    Called only when a non-None value is supplied — `None` means
    independent production line and is always valid."""
    if not uap_id or not uap_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="uap_id: no such production area in this namespace.",
        )

    uap = client.get_document(UAP_COLLECTION, uap_id)
    if not uap or uap.get("namespace_id") != namespace_id or not is_active(uap):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="uap_id: no such production area in this namespace.",
        )


def create_production_line(
    payload: CreateProductionLineIn, namespace_id: str
) -> ProductionLineOut:
    client = get_firestore_client()
    if payload.uap_id is not None:
        _validate_uap_id(client, namespace_id, payload.uap_id)
    assert_name_unique(
        client,
        PRODUCTION_LINE_COLLECTION,
        namespace_id,
        payload.name,
        resource_label="production line",
    )

    line_id = str(uuid.uuid4())
    doc: dict[str, Any] = {
        "id": line_id,
        "name": payload.name,
        "description": payload.description,
        "uap_id": payload.uap_id,
        "namespace_id": namespace_id,
    }
    client.create_document(PRODUCTION_LINE_COLLECTION, doc, document_id=line_id)
    return _to_out(doc)


def list_production_lines(namespace_id: str) -> list[ProductionLineOut]:
    client = get_firestore_client()
    rows = client.find_documents(
        PRODUCTION_LINE_COLLECTION, {"namespace_id": namespace_id}
    )
    # Archived filter happens here, in Python — never as a Firestore `where`
    # (every pre-existing document has no `archived_at` key at all; see
    # `core.archiving`).
    return [_to_out(r) for r in rows if is_active(r)]


def _load_scoped(
    client: FirestoreClient,
    line_id: str,
    namespace_id: str,
    *,
    allow_archived: bool = False,
) -> dict[str, Any]:
    """Load a production line scoped to `namespace_id`, 404ing on a missing
    id, a cross-namespace id, or (unless `allow_archived`) an archived one —
    an archived line behaves as not found from every angle except the
    archive endpoint itself, which needs to re-load it to stay idempotent."""
    line = client.get_document(PRODUCTION_LINE_COLLECTION, line_id)
    if not line or line.get("namespace_id") != namespace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Production line not found."
        )
    if not allow_archived and not is_active(line):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Production line not found."
        )
    return line


def get_production_line(line_id: str, namespace_id: str) -> ProductionLineOut:
    return _to_out(_load_scoped(get_firestore_client(), line_id, namespace_id))


def update_production_line(
    line_id: str, payload: UpdateProductionLineIn, namespace_id: str
) -> ProductionLineOut:
    client = get_firestore_client()
    line = _load_scoped(client, line_id, namespace_id)

    fields_set = payload.model_fields_set
    updates: dict[str, Any] = {}

    if "name" in fields_set and payload.name is not None:
        assert_name_unique(
            client,
            PRODUCTION_LINE_COLLECTION,
            namespace_id,
            payload.name,
            exclude_id=line_id,
            resource_label="production line",
        )
        updates["name"] = payload.name
    if "description" in fields_set and payload.description is not None:
        updates["description"] = payload.description
    if "uap_id" in fields_set:
        new_uap_id: Optional[str] = payload.uap_id
        if new_uap_id is not None:
            _validate_uap_id(client, namespace_id, new_uap_id)
        updates["uap_id"] = new_uap_id

    if updates:
        client.update_document(PRODUCTION_LINE_COLLECTION, line_id, updates)
    return _to_out({**line, **updates})


def delete_production_line(line_id: str, namespace_id: str) -> ProductionLineArchiveOut:
    """Archives the production line (irreversibly; there is no unarchive)
    and cascades to its own workstations (those whose `production_line_id`
    is this line); a workstation on another line, or an independent one, is
    never touched. The cascade shares one `archived_at` timestamp, computed
    once. Idempotent: archiving an already-archived line returns 200
    without touching its original `archived_at` — the cascade is still
    (re-)walked using that same original timestamp.

    Layer 1 of "stop escalating a ticket on an archived resource": any OPEN
    downtime ticket scoped to this line, or to one of its cascaded
    workstations, has its pending escalation Cloud Task cancelled and its
    `escalation_task_id` cleared — see
    `core.archiving.cancel_ticket_escalations_on_archive`."""
    client = get_firestore_client()
    line = _load_scoped(client, line_id, namespace_id, allow_archived=True)

    timestamp = line.get("archived_at") or now_iso_for_namespace(client, namespace_id)
    if not line.get("archived_at"):
        client.update_document(
            PRODUCTION_LINE_COLLECTION, line_id, {"archived_at": timestamp}
        )
        line = {**line, "archived_at": timestamp}

    stations = client.find_documents(
        WORKSTATION_COLLECTION, {"namespace_id": namespace_id}
    )
    archived_station_ids: list[str] = []
    for station in stations:
        if station.get("production_line_id") != line_id:
            continue
        archived_station_ids.append(station["id"])
        if is_active(station):
            client.update_document(
                WORKSTATION_COLLECTION, station["id"], {"archived_at": timestamp}
            )

    cancel_ticket_escalations_on_archive(
        client,
        namespace_id,
        cancel_escalation,
        production_line_ids=[line_id],
        workstation_ids=archived_station_ids,
    )

    return ProductionLineArchiveOut(
        **_to_out(line).model_dump(),
        archived_workstation_ids=archived_station_ids,
    )
