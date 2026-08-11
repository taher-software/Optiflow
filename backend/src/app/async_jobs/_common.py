"""Shared helpers for downtime async job handlers (see `.claude/skills/async`).

Extracted out of `add_down_time` so `notify_down_time_update` does not
duplicate tenant-scoped location resolution — there must be exactly one
implementation, imported by every handler that needs it. This module owns
that location resolution plus the `down_time`/`issues` collection constants.

Namespace-timezone resolution does NOT live here: it moved to
`src.app.core.timezone.namespace_timezone`, the single shared implementation
used by both the sync API layer and this async job layer (`core/` is the
neutral home either side may import without crossing the sync/async
boundary). Import it directly from there rather than re-exporting it here.
"""

from __future__ import annotations

import logging

from src.app.core.firestore import (
    PRODUCTION_LINE_COLLECTION,
    UAP_COLLECTION,
    WORKSTATION_COLLECTION,
)
from src.app.globals.enum import Language, ProductionScope

logger = logging.getLogger(__name__)

DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"

_FALLBACK_LOCATION = {Language.EN: "the plant", Language.FR: "l'usine"}

# Sentinel distinguishing "no pre-fetched doc was passed" from "the caller
# already looked it up and it's None" (e.g. scope isn't `work station`, or
# the document doesn't exist) — see `resolve_location`'s `doc` parameter.
_UNRESOLVED = object()


def resolve_scope_document(
    firestore, namespace_id: str, scope_source: dict
) -> dict | None:
    """Best-effort, tenant-scoped fetch of the Firestore document backing a
    downtime ticket's production scope (the workstation / production line /
    UAP document), or `None` when the scope has no such document (`plant`),
    the referenced document doesn't exist, or it belongs to another tenant.
    Never raises.

    `scope_source` must carry the same keys `add_down_time`'s payload does:
    `production_scope` plus whichever of `workstation_id` /
    `production_line_id` / `uap_id` applies. Callers reading an already
    written issue document (rather than the raw creation payload) adapt its
    fields (`down_time_scope` -> `production_scope`, etc.) into this shape.

    Extracted out of `resolve_location` so a caller that also needs the raw
    document (e.g. `add_down_time` evaluating the escalation policy against
    the workstation's `type`) can fetch it exactly once and pass it to both,
    rather than reading it twice.
    """
    try:
        scope = scope_source.get("production_scope")
        doc = None
        if scope == ProductionScope.WORK_STATION.value and scope_source.get("workstation_id"):
            doc = firestore.get_document(
                WORKSTATION_COLLECTION, scope_source["workstation_id"]
            )
        elif scope == ProductionScope.PRODUCTION_LINE.value and scope_source.get(
            "production_line_id"
        ):
            doc = firestore.get_document(
                PRODUCTION_LINE_COLLECTION, scope_source["production_line_id"]
            )
        elif scope == ProductionScope.UAP.value and scope_source.get("uap_id"):
            doc = firestore.get_document(UAP_COLLECTION, scope_source["uap_id"])

        # The worker route is unauthenticated at the app layer, so a job
        # message could pair an attacker's `namespace_id` with a victim
        # tenant's document id. Never surface another tenant's document.
        if doc and doc.get("namespace_id") != namespace_id:
            doc = None

        return doc
    except Exception as e:  # never let a scope-document lookup fail the caller
        logger.warning(
            f"resolve_scope_document: failed to resolve scope document "
            f"(namespace='{namespace_id}'): {e}"
        )
        return None


def resolve_location(
    firestore,
    namespace_id: str,
    namespace: dict | None,
    scope_source: dict,
    language: Language,
    doc: dict | None = _UNRESOLVED,
) -> str:
    """Best-effort human-readable location label for a downtime ticket, from
    its production scope. Reads the relevant Firestore document's `name`
    field. Never raises — falls back to the namespace `company_name`, then to
    a generic "the plant" / "l'usine" label, so a missing/renamed document
    never blocks the caller.

    `scope_source` — see `resolve_scope_document`.

    `doc`: optional pre-fetched scope document (from `resolve_scope_document`)
    to reuse instead of fetching it again — pass this when the caller already
    needed the raw document for something else. Leave unset (the default) to
    have this function fetch it itself, as before.
    """
    doc = resolve_scope_document(firestore, namespace_id, scope_source) if doc is _UNRESOLVED else doc

    name = (doc or {}).get("name") if doc else None
    if name:
        return name

    company_name = (namespace or {}).get("company_name")
    if company_name:
        return company_name
    return _FALLBACK_LOCATION[language]
