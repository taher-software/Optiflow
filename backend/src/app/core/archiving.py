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

import logging
from datetime import datetime
from typing import Any, Callable, Iterable, Optional

from src.app.core.firestore import NAMESPACE_COLLECTION
from src.app.core.timezone import namespace_timezone
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import DownTimeStatus

logger = logging.getLogger(__name__)

# Same literals `down_time.services` / `async_jobs.add_down_time` store the
# issue under — duplicated here rather than imported, matching the existing
# convention (see `routers/down_time/services.py`'s own copy).
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"

# Firestore's `in` operator accepts at most 10 values per query.
_IN_QUERY_CHUNK_SIZE = 10


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


def _chunked(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def cancel_ticket_escalations_on_archive(
    client: FirestoreClient,
    namespace_id: str,
    canceller: Callable[[Optional[str]], Any],
    *,
    uap_ids: Iterable[str] = (),
    production_line_ids: Iterable[str] = (),
    workstation_ids: Iterable[str] = (),
) -> None:
    """Layer 1 of "stop escalating a ticket whose resource got archived":
    proactively cancel the pending escalation Cloud Task of every OPEN
    downtime ticket scoped to any of the given resource ids, and clear that
    ticket's `escalation_task_id`.

    Shared by `routers.{uap,production_line,workstation}.services` — the
    three archiving endpoints differ only in which resource ids their
    cascade covers (a workstation archive has none; a line archive adds its
    own workstations; a UAP archive adds its lines and their workstations),
    which each caller has already computed for its own response payload.
    This function does not re-derive that cascade, it only acts on it.

    `canceller` is the caller's own module-level `cancel_escalation` name
    (`from src.app.core.escalation import cancel_escalation`), not this
    module's import of it — callers must pass their own bound name so test
    spies that monkeypatch it on the service module actually take effect
    (mirrors the convention `down_time.services` already established; see
    that module's docstring). It is best-effort and never raises on its own,
    but is called inside a try/except here anyway (belt-and-braces on top of
    belt-and-braces, same posture as `down_time.services`'s own
    `_cancel_escalation_best_effort`) so nothing in this function can ever
    turn a successful archive into a 500.

    Bounded I/O: at most one Firestore query per non-empty id group (uap /
    production line / workstation), chunked to Firestore's 10-value `in`
    limit — never one query per ticket or per resource. A ticket whose
    `status` is already `closed` is left completely untouched: no cancel
    call, no write."""
    field_id_groups = (
        ("uap_id", list(uap_ids)),
        ("production_line_id", list(production_line_ids)),
        ("workstation_id", list(workstation_ids)),
    )

    tickets_by_id: dict[str, dict[str, Any]] = {}
    for field, ids in field_id_groups:
        if not ids:
            continue
        for chunk in _chunked(ids, _IN_QUERY_CHUNK_SIZE):
            rows = client.find_subdocuments(
                DOWN_TIME_COLLECTION,
                namespace_id,
                ISSUES_SUBCOLLECTION,
                {field: [("in", chunk)]},
            )
            for row in rows:
                tickets_by_id[row["id"]] = row

    for ticket in tickets_by_id.values():
        if ticket.get("status") == DownTimeStatus.CLOSED.value:
            continue
        try:
            canceller(ticket.get("escalation_task_id"))
        except Exception:
            logger.warning(
                "cancel_ticket_escalations_on_archive: escalation "
                f"cancellation raised unexpectedly for down_time_id="
                f"{ticket.get('id')}.",
                exc_info=True,
            )
        client.update_subdocument(
            DOWN_TIME_COLLECTION,
            namespace_id,
            ISSUES_SUBCOLLECTION,
            ticket["id"],
            {"escalation_task_id": None},
        )
