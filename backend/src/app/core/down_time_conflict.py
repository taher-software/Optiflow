"""Shared "is this resource already down" conflict check — §4 of
`.claude/specs/downtime-gantt.md` ("one open downtime per resource").

Lives in `src.app.core` (not `routers/down_time/` or `async_jobs/`)
precisely because it is shared by both sides of the guard: the synchronous
`POST /down-times` endpoint (`src.app.routers.down_time.services`, so the
caller gets a `409`) and the defensive re-check in the
`src.app.async_jobs.add_down_time` handler (the endpoint only publishes; it
never runs the handler in-process, so the same business rule must be
enforced again on the async side). Same reasoning as
`core.timezone.namespace_timezone` — one shared implementation either side
may import, never two copies that can drift (see `async_jobs/_common.py`'s
module docstring for why that drift has already cost this codebase twice).

Conflict rule (§4, developer ruling 2026-09-11): a declaration on a resource
is blocked when the resource itself, or any of its ancestors (work station ->
its production line -> its UAP -> plant), already carries an issue in status
`pending` or `ongoing`. A `resolved` (not yet closed) or `closed` ticket never
blocks — the fix is done, or the ticket is fully retired. The reverse
direction — a child resource already being down — never blocks a *parent*
declaration: a broader stop is new information, not a duplicate.

Bounded I/O: exactly one Firestore query for the namespace's open-status
issues (`find_subdocuments` with a `status in (...)` filter, then filtered in
Python — the same posture as
`routers/down_time/services._filter_archived_resource_issues` and the
carry-over queries in `routers/kpi/services.py`: one round trip, never one
read per issue), plus at most two single-document reads to walk a
workstation/production-line up to its ancestors when the caller didn't
already know them (mirrors `async_jobs/_common.resolve_scope_document`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.app.core.firestore import (
    PRODUCTION_LINE_COLLECTION,
    WORKSTATION_COLLECTION,
)
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import DownTimeStatus, ProductionScope

# Same literals `add_down_time` stores the issue under (see
# `src.app.async_jobs.add_down_time.DOWN_TIME_COLLECTION` /
# `ISSUES_SUBCOLLECTION` and `routers/down_time/services.py`'s copy of the
# same constants) — duplicated here on purpose rather than imported, to keep
# this module free of a dependency on either the router or the async job
# package (it must stay importable from both without a cycle).
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"

# Statuses that count as "open" for the conflict guard — `resolved`/`closed`
# never block (see module docstring).
_OPEN_STATUSES = (DownTimeStatus.PENDING.value, DownTimeStatus.ONGOING.value)

# The Firestore field on an issue document carrying the resource id for each
# non-plant scope level.
_SCOPE_ID_FIELD = {
    ProductionScope.UAP.value: "uap_id",
    ProductionScope.PRODUCTION_LINE.value: "production_line_id",
    ProductionScope.WORK_STATION.value: "workstation_id",
}


@dataclass(frozen=True)
class DownTimeConflict:
    """Enough for a caller to build a clear user-facing message: which issue
    is blocking, the level it was declared at (a `ProductionScope` value —
    `"plant"` / `"uap"` / `"production line"` / `"work station"`), and its
    current status (always `"pending"` or `"ongoing"` — see `_OPEN_STATUSES`)."""

    issue_id: str
    down_time_scope: str
    status: str


def _resolve_ancestor_ids(
    firestore: FirestoreClient,
    namespace_id: str,
    production_scope: str,
    uap_id: Optional[str],
    production_line_id: Optional[str],
    workstation_id: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Always derive `(uap_id, production_line_id, workstation_id)` for
    levels ABOVE the declared scope by walking the resource documents
    themselves — workstation -> its `production_line_id` -> that line's
    `uap_id`. This is unconditional: an ancestor id the caller supplies is
    NEVER trusted as-is and is overwritten by whatever the datastore says
    (including with `None`, for an independent workstation or an
    unresolvable document). Only the id that names the declared
    `production_scope` itself (its own target, not an ancestor) is ever
    taken from the caller.

    Why unconditional rather than "fill in only what's missing": this
    function has exactly two callers — the synchronous `POST /down-times`
    endpoint's service (which has already validated the chain against
    Firestore and could, in principle, be trusted) and the
    `add_down_time` async handler, reachable through the
    unauthenticated-by-design `/pubsub_job` route, which recopies its
    payload with NO revalidation (review finding W5). A "trust the
    supplied ancestor id if present" mode — whether the previous
    fill-missing-only behaviour or an opt-in flag — is one line a future
    caller can get wrong by simply supplying an id (or by not opting into
    the strict mode), silently re-opening exactly this hole. Making
    resolution unconditional removes that failure mode entirely: there is
    no trusting branch to misuse. The cost is bounded (at most two
    `get_document` reads, independent of the number of open issues) for
    BOTH callers — see `find_blocking_conflict`'s docstring.

    Tenant-checked exactly like `_common.resolve_scope_document`: a document
    that doesn't belong to `namespace_id` is treated as absent rather than
    trusted. Never raises — an ancestor that fails to resolve just narrows
    the blocking-id set below, the same conservative-but-safe posture
    `resolve_scope_document` takes; it must never block ticket creation on a
    lookup blip on its own.
    """
    if production_scope == ProductionScope.WORK_STATION.value:
        production_line_id = None
        if workstation_id:
            station = firestore.get_document(WORKSTATION_COLLECTION, workstation_id)
            if station and station.get("namespace_id") == namespace_id:
                production_line_id = station.get("production_line_id")

    if production_scope in (
        ProductionScope.WORK_STATION.value,
        ProductionScope.PRODUCTION_LINE.value,
    ):
        uap_id = None
        if production_line_id:
            line = firestore.get_document(
                PRODUCTION_LINE_COLLECTION, production_line_id
            )
            if line and line.get("namespace_id") == namespace_id:
                uap_id = line.get("uap_id")

    return uap_id, production_line_id, workstation_id


def find_blocking_conflict(
    firestore: FirestoreClient,
    namespace_id: str,
    production_scope: str,
    uap_id: Optional[str] = None,
    production_line_id: Optional[str] = None,
    workstation_id: Optional[str] = None,
) -> Optional[DownTimeConflict]:
    """Whether a new downtime declaration on the given resource would
    conflict with an already-open (`pending`/`ongoing`) issue on the resource
    itself or any of its ancestors (§4). Returns the first `DownTimeConflict`
    found, or `None` when the declaration is clear to proceed.

    `production_scope` is a `ProductionScope` value (its raw string is fine —
    callers on both sides already carry it as a plain string, e.g. a
    `add_down_time` payload's `"production_scope"` or `down_time_scope` on an
    already-written issue).

    Pass the id of the resource the declaration actually targets
    (`uap_id` for a `uap` declaration, `production_line_id` for a
    `production line` one, `workstation_id` for a `work station` one — a
    caller never needs to pre-resolve the ancestor chain itself). **Ancestor
    ids above the declared scope are ALWAYS re-derived from the resource
    documents themselves (see `_resolve_ancestor_ids`), never taken from the
    caller — even if supplied.** This is unconditional and applies to both
    intended callers identically, on purpose (review finding W5: a caller
    cannot be relied on to have validated its own ancestor ids, so the
    function never gives a way to skip that by supplying them):
    - `src.app.async_jobs.add_down_time`, reachable through the
      unauthenticated-by-design `/pubsub_job` route, only ever passes the
      single id of the declared scope; everything above it is resolved here.
    - the `POST /down-times` endpoint's service has already validated the
      target resource and its parent chain against Firestore before this
      runs — it MAY pass the full chain for readability/backward
      compatibility, but any ancestor id above the declared scope is
      ignored and re-resolved here regardless, at the same bounded cost
      (at most two extra `get_document` reads — see module docstring).
    """
    uap_id, production_line_id, workstation_id = _resolve_ancestor_ids(
        firestore,
        namespace_id,
        production_scope,
        uap_id,
        production_line_id,
        workstation_id,
    )

    # The resource id to match against, per level — `None` for a level the
    # target has no ancestor at, which stops it from ever matching (see the
    # `target_id is not None` check below). Deliberately keyed only on the
    # target's own scope + ancestors — a descendant's id (e.g. a target
    # `production line`'s `workstation_id`, which doesn't exist) is never
    # part of this mapping, which is exactly what keeps the reverse
    # direction (child down, parent declared) from ever matching.
    blocking_ids = {
        ProductionScope.UAP.value: uap_id,
        ProductionScope.PRODUCTION_LINE.value: production_line_id,
        ProductionScope.WORK_STATION.value: workstation_id,
    }

    # One bounded query: every open issue in the namespace, filtered in
    # Python below — never one read per issue (see module docstring).
    open_issues = firestore.find_subdocuments(
        DOWN_TIME_COLLECTION,
        namespace_id,
        ISSUES_SUBCOLLECTION,
        params={"status": [("in", _OPEN_STATUSES)]},
    )

    for issue in open_issues:
        scope = issue.get("down_time_scope")
        if scope == ProductionScope.PLANT.value:
            # A plant-wide open ticket blocks every declaration, regardless
            # of the target's own scope.
            return DownTimeConflict(
                issue_id=issue["id"],
                down_time_scope=scope,
                status=issue.get("status"),
            )

        id_field = _SCOPE_ID_FIELD.get(scope)
        if id_field is None:
            # Unknown/malformed `down_time_scope` on the stored issue — never
            # let a bad document break the guard; just skip it.
            continue

        target_id = blocking_ids.get(scope)
        if target_id is not None and issue.get(id_field) == target_id:
            return DownTimeConflict(
                issue_id=issue["id"],
                down_time_scope=scope,
                status=issue.get("status"),
            )

    return None
