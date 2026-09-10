"""Shared archiving helpers for namespace-scoped resources (UAP, production
line, workstation).

Archiving replaces hard delete for these three resources: the document is
never removed from Firestore (its downtime tickets must keep counting in the
plant's KPIs), it simply gets an `archived_at` ISO-8601 timestamp and is
excluded from every list/read from then on. There is deliberately no stored
`archived` boolean — a second field would drift from the date, so "is this
active?" is always derived from `archived_at` here, never stored and never
re-implemented at each call site.

Every resource already in Firestore has no `archived_at` key at all, and a
Firestore `where("archived_at", "==", None)` does not match a document where
the field is absent — so this predicate is only ever applied in Python,
never as a server-side query filter.
"""

from datetime import datetime
from typing import Any

from src.app.core.firestore import NAMESPACE_COLLECTION
from src.app.core.timezone import namespace_timezone
from src.app.gcp.firestore import FirestoreClient


def is_active(resource: dict[str, Any]) -> bool:
    """True when `resource` is not archived: `archived_at` absent, empty, or
    `None`."""
    return not resource.get("archived_at")


def now_iso_for_namespace(client: FirestoreClient, namespace_id: str) -> str:
    """Current time in the namespace's timezone, as an ISO-8601 string — the
    same timestamp convention `down_time` uses for its own timestamps (see
    `_now_iso_for_namespace` in `routers/down_time/services.py`)."""
    namespace = client.get_document(NAMESPACE_COLLECTION, namespace_id)
    tz = namespace_timezone(namespace_id, namespace)
    return datetime.now(tz).isoformat()
