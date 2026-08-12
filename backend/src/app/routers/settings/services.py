from typing import Any, Optional

from fastapi import HTTPException, status

from src.app.core.firestore import (
    NAMESPACE_SETTINGS_COLLECTION,
    SETTINGS_SUBCOLLECTION,
)
from src.app.gcp import get_firestore_client

from src.app.routers.settings.modelsIn import (
    CreateNamespaceSettingsIn,
    ShiftTime,
    UpdateNamespaceSettingsIn,
)
from src.app.routers.settings.modelsOut import NamespaceSettingsOut

_SHIFT_FIELDS = ("shift_1", "shift_2", "shift_3")


def _shift_from_stored(value: Any) -> Optional[ShiftTime]:
    """Rebuild a `ShiftTime` from its stored dict, tolerating a missing/`None`
    value (a shift that was never configured)."""
    if not isinstance(value, dict):
        return None
    return ShiftTime(start_time=value.get("start_time", ""), end_time=value.get("end_time", ""))


def _to_out(doc: dict[str, Any]) -> NamespaceSettingsOut:
    return NamespaceSettingsOut(
        namespace_id=doc.get("namespace_id", ""),
        shift_number=doc.get("shift_number", 1),
        shift_1=_shift_from_stored(doc.get("shift_1")),
        shift_2=_shift_from_stored(doc.get("shift_2")),
        shift_3=_shift_from_stored(doc.get("shift_3")),
        time_to_escalate=doc.get("time_to_escalate", 1800),
    )


def create_namespace_settings(
    payload: CreateNamespaceSettingsIn, namespace_id: str
) -> NamespaceSettingsOut:
    """Create (or overwrite) the plant settings of `namespace_id`. The stored
    document reflects the payload exactly, keyed by the namespace id under
    `NamespaceSettings/{namespace_id}/settings/{namespace_id}`."""
    client = get_firestore_client()

    doc: dict[str, Any] = {
        "namespace_id": namespace_id,
        "shift_number": payload.shift_number,
        "time_to_escalate": payload.time_to_escalate,
    }
    for field in _SHIFT_FIELDS:
        shift: Optional[ShiftTime] = getattr(payload, field)
        doc[field] = shift.model_dump() if shift is not None else None

    client.create_subdocument(
        NAMESPACE_SETTINGS_COLLECTION,
        namespace_id,
        SETTINGS_SUBCOLLECTION,
        doc,
        document_id=namespace_id,
    )
    return _to_out(doc)


def update_namespace_settings(
    payload: UpdateNamespaceSettingsIn, namespace_id: str
) -> NamespaceSettingsOut:
    """Merge the provided fields into the namespace's existing settings. Only
    fields present in the request body are written (partial update). Raises
    404 when the namespace has no settings yet (create them first)."""
    client = get_firestore_client()

    existing = client.get_subdocument(
        NAMESPACE_SETTINGS_COLLECTION, namespace_id, SETTINGS_SUBCOLLECTION, namespace_id
    )
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No settings for this namespace yet.",
        )

    fields_set = payload.model_fields_set
    updates: dict[str, Any] = {}

    if "shift_number" in fields_set and payload.shift_number is not None:
        updates["shift_number"] = payload.shift_number
    if "time_to_escalate" in fields_set and payload.time_to_escalate is not None:
        updates["time_to_escalate"] = payload.time_to_escalate
    for field in _SHIFT_FIELDS:
        if field in fields_set:
            shift: Optional[ShiftTime] = getattr(payload, field)
            updates[field] = shift.model_dump() if shift is not None else None

    if updates:
        client.update_subdocument(
            NAMESPACE_SETTINGS_COLLECTION,
            namespace_id,
            SETTINGS_SUBCOLLECTION,
            namespace_id,
            updates,
        )
    return _to_out({**existing, **updates})


def get_namespace_settings(
    namespace_id: str, requester_namespace_id: str
) -> NamespaceSettingsOut:
    """Retrieve the settings of `namespace_id`. Tenant-scoped: a caller may
    only read the settings of their own namespace (403 otherwise). Raises 404
    when no settings exist for that namespace yet."""
    if namespace_id != requester_namespace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access the settings of your own namespace.",
        )

    client = get_firestore_client()
    doc = client.get_subdocument(
        NAMESPACE_SETTINGS_COLLECTION, namespace_id, SETTINGS_SUBCOLLECTION, namespace_id
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No settings for this namespace yet.",
        )
    return _to_out(doc)
