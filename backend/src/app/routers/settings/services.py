import logging
from typing import Any, Optional

from fastapi import HTTPException, status
from pydantic import ValidationError

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

logger = logging.getLogger(__name__)

_SHIFT_FIELDS = ("shift_1", "shift_2", "shift_3")


def _shift_from_stored(value: Any) -> Optional[ShiftTime]:
    """Rebuild a `ShiftTime` from its stored dict, tolerating a missing/`None`
    value (a shift that was never configured) and legacy stored documents
    that still carry a residual `break_minutes` field (revision 2 — ignored,
    `ShiftTime` no longer has that field) or no break fields at all (any
    document written before revision 3, or a shift with no break). Review
    fix W6: a stored shift missing/blank `start_time`/`end_time` (an
    amputated legacy document) fails `ShiftTime`'s own validation
    (`pattern`/zero-length checks) — caught here and treated as "not
    configured" (logged, never a 500), mirroring how the KPI module was
    hardened against the same kind of corrupted document (fix #9,
    `kpi/services.py::_parse_hhmm`). A stored break pair that itself fails
    `ShiftTime`'s break validation (e.g. a corrupted document with a break
    outside the shift window) is degraded the same way: the whole shift is
    treated as unconfigured rather than 500ing, since `ShiftTime` has no way
    to represent "valid window, invalid break"."""
    if not isinstance(value, dict):
        return None
    try:
        return ShiftTime(
            start_time=value.get("start_time", ""),
            end_time=value.get("end_time", ""),
            break_start_time=value.get("break_start_time"),
            break_end_time=value.get("break_end_time"),
        )
    except ValidationError:
        logger.warning("settings: unparsable stored shift %r, treating as unconfigured.", value)
        return None


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
    404 when the namespace has no settings yet (create them first).

    Revision 3 decision (§5bis.4bis — "shift window required from
    `shift_number = 1`"): `UpdateNamespaceSettingsIn` stays all-optional in
    shape (a PATCH may touch only `time_to_escalate`), so the "every shift
    up to `shift_number` has a window" invariant can't be checked on the
    payload alone — it depends on what's already stored. Instead, this
    function re-checks the invariant on the **merged** document (existing +
    payload) before writing anything: for the resulting `shift_number`,
    `shift_1..shift_number` must all be non-`None` in the merge. Concretely:
    - Patching `shift_number` down (e.g. 3 -> 1) never fails on this check
      by itself — `shift_1` was already required (at `shift_number == 3`,
      both before and after revision 3) unless the document predates
      revision 3 and was created at `shift_number == 1` without a window; in
      that legacy case the PATCH is rejected until the payload also supplies
      `shift_1`, which is the intended tightening (a plant touching its
      settings post-revision-3 must have a real mono-shift window).
    - Patching `shift_number` up (e.g. 1 -> 2) fails unless the payload (or
      an already-stored value) supplies the newly-required shift's window.
    422 with the missing shift numbers on violation — nothing is written."""
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

    merged = {**existing, **updates}
    shift_number = merged.get("shift_number", 1)
    missing = [
        i for i in range(1, shift_number + 1) if merged.get(f"shift_{i}") is None
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "shift window(s) required for shift "
                + ", ".join(str(n) for n in missing)
            ),
        )

    if updates:
        client.update_subdocument(
            NAMESPACE_SETTINGS_COLLECTION,
            namespace_id,
            SETTINGS_SUBCOLLECTION,
            namespace_id,
            updates,
        )
    return _to_out(merged)


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
