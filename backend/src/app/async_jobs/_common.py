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


def resolve_location(
    firestore, namespace_id: str, namespace: dict | None, scope_source: dict, language: Language
) -> str:
    """Best-effort human-readable location label for a downtime ticket, from
    its production scope. Reads the relevant Firestore document's `name`
    field. Never raises — falls back to the namespace `company_name`, then to
    a generic "the plant" / "l'usine" label, so a missing/renamed document
    never blocks the caller.

    `scope_source` must carry the same keys `add_down_time`'s payload does:
    `production_scope` plus whichever of `workstation_id` /
    `production_line_id` / `uap_id` applies. Callers reading an already
    written issue document (rather than the raw creation payload) adapt its
    fields (`down_time_scope` -> `production_scope`, etc.) into this shape.
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
        # tenant's document id. Never surface another tenant's document name.
        if doc and doc.get("namespace_id") != namespace_id:
            doc = None

        name = (doc or {}).get("name") if doc else None
        if name:
            return name
    except Exception as e:  # never let a location lookup fail the caller
        logger.warning(
            f"resolve_location: failed to resolve location "
            f"(namespace='{namespace_id}'): {e}"
        )

    company_name = (namespace or {}).get("company_name")
    if company_name:
        return company_name
    return _FALLBACK_LOCATION[language]
