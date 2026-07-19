import uuid
from typing import Any

from fastapi import HTTPException, status

from src.app.core.firestore import PRODUCTION_LINE_COLLECTION, UAP_COLLECTION
from src.app.gcp import get_firestore_client
from src.app.gcp.firestore import FirestoreClient

from src.app.routers.production_line.modelsIn import (
    CreateProductionLineIn,
    UpdateProductionLineIn,
)
from src.app.routers.production_line.modelsOut import ProductionLineOut


def _to_out(line: dict[str, Any]) -> ProductionLineOut:
    return ProductionLineOut(
        id=line["id"],
        name=line.get("name", ""),
        description=line.get("description", ""),
        uap_id=line.get("uap_id", ""),
        namespace_id=line.get("namespace_id", ""),
    )


def _validate_uap_id(client: FirestoreClient, namespace_id: str, uap_id: str) -> None:
    """Ensure `uap_id` refers to an existing UAP in the caller's namespace.
    Raises HTTPException(422) otherwise. Never lets a blank id reach the
    Firestore SDK (`.document("")` would otherwise blow up unhandled)."""
    if not uap_id or not uap_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="uap_id: no such production area in this namespace.",
        )

    uap = client.get_document(UAP_COLLECTION, uap_id)
    if not uap or uap.get("namespace_id") != namespace_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="uap_id: no such production area in this namespace.",
        )


def create_production_line(
    payload: CreateProductionLineIn, namespace_id: str
) -> ProductionLineOut:
    client = get_firestore_client()
    _validate_uap_id(client, namespace_id, payload.uap_id)

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
    return [_to_out(r) for r in rows]


def _load_scoped(
    client: FirestoreClient, line_id: str, namespace_id: str
) -> dict[str, Any]:
    line = client.get_document(PRODUCTION_LINE_COLLECTION, line_id)
    if not line or line.get("namespace_id") != namespace_id:
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

    if payload.uap_id is not None:
        _validate_uap_id(client, namespace_id, payload.uap_id)

    updates: dict[str, Any] = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.description is not None:
        updates["description"] = payload.description
    if payload.uap_id is not None:
        updates["uap_id"] = payload.uap_id

    if updates:
        client.update_document(PRODUCTION_LINE_COLLECTION, line_id, updates)
    return _to_out({**line, **updates})


def delete_production_line(line_id: str, namespace_id: str) -> ProductionLineOut:
    client = get_firestore_client()
    line = _load_scoped(client, line_id, namespace_id)
    client.delete_document(PRODUCTION_LINE_COLLECTION, line_id)
    return _to_out(line)
