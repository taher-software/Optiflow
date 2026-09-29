"""Business logic for the `kpi` router (`GET /kpi/dashboard|drilldown|daily`).

Everything is computed in-memory from a small number of ticket fetches per
request (the spec's own assumption: per-plant monthly downtime volumes are
small). The module is organized bottom-up:

1. Type/process mapping between the frontend's slug ids and the backend's
   `DownTimeType`/`Process` enums (§5bis.7 of the spec).
2. Ticket-level KPI primitives (downtime seconds, MTTR) per
   `.claude/specs/kpi-dashboard.md` §5bis — the single source of truth for
   every KPI definition in this file.
3. Planned-time (shift-schedule) helpers feeding MTBF.
4. The UAP -> production line -> workstation hierarchy, used both to resolve
   a ticket's location (roll-up: a workstation ticket rolls up to its line's
   UAP) and to build the dashboard/drill-down `children` lists.
5. Breakdown builders (by shift/location/process/type/agent) — pure
   functions the test-agent can unit-test directly.
6. The three public entry points: `get_dashboard`, `get_drilldown`,
   `get_daily`.

All datetimes are timezone-aware, in the namespace's IANA timezone
(`src.app.core.timezone.namespace_timezone`), matching how `created_at` /
`resolved_at` are stored by the `add_down_time` async job.

Carry-over tickets (review fix #1): a plain `created_at` range query misses
tickets that were opened before the queried period but are still relevant to
it — a still-open ticket carries its downtime into the window, and a ticket
closed inside the window was "live" right up to its resolution even though it
was created earlier. `_fetch_tickets` returns `(current, carry_overs)`:
`current` is the unchanged range query (the only source for `count`/`mttr`/
count+mttr daily buckets); `current + carry_overs` feeds every downtime-based
aggregation (overall/breakdown downtime, pareto, repair, downtime_by_* bars).
`_ticket_downtime_seconds`'s existing `max(created_at, period_start)` clamp
does the rest of the work once a carry-over ticket is in the slice.
"""

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Optional

from fastapi import HTTPException, status

from src.app.core.archiving import is_active
from src.app.core.firestore import (
    NAMESPACE_COLLECTION,
    NAMESPACE_SETTINGS_COLLECTION,
    PRODUCTION_LINE_COLLECTION,
    SETTINGS_SUBCOLLECTION,
    UAP_COLLECTION,
    USERS_COLLECTION,
    WORKSTATION_COLLECTION,
)
from src.app.core.shift_time import break_minutes_in_window
from src.app.core.shift_time import clock_window_elapsed_since_midnight
from src.app.core.shift_time import parse_hhmm as _strict_parse_hhmm
from src.app.core.timezone import namespace_timezone
from src.app.gcp import get_firestore_client
from src.app.gcp.firestore import FirestoreClient
from src.app.globals.enum import (
    DOWNTIME_TYPE_PROCESS,
    DownTimeStatus,
    DownTimeType,
    Process,
    ProductionScope,
    WorkstationType,
)

from src.app.routers.kpi.modelsIn import (
    MAX_PATH_STEPS,
    DailyQueryIn,
    DashboardQueryIn,
    DrilldownQueryIn,
)
from src.app.routers.kpi.modelsOut import (
    Bar,
    BaseKpis,
    BreakdownRow,
    DailyPoint,
    DailyPointsOut,
    DashboardData,
    DrilldownData,
    Kpis,
    NamespaceMeta,
    ParetoRow,
    ShiftWindow,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# 0. Parallel-read helper.
#
# Every public entry point below issues several Firestore reads that are
# mutually independent (e.g. `_fetch_tickets`'s 3 queries, `_location_hierarchy`'s
# 3 collection scans, `_namespace_context`'s 2 document gets) but were
# previously awaited one at a time, each paying its own network round-trip.
# `FirestoreClient` is a blocking client and every endpoint in this router is
# a sync `def` (FastAPI already runs those in its own threadpool), so the fix
# is a plain `ThreadPoolExecutor`, not `asyncio`.
#
# A single MODULE-LEVEL pool (not one `ThreadPoolExecutor()` per call) is
# used deliberately: creating and tearing down an executor per request means
# spawning/joining a handful of OS threads on every single dashboard/
# drilldown/daily call, which is wasteful and, under concurrent traffic,
# unbounded (as many live executors as in-flight requests). A shared pool
# reuses its worker threads across requests and gives a single place to
# bound total concurrency. `max_workers=12` is sized for "a few requests at
# once, each needing at most 3 concurrent reads" (this module's largest
# fan-out is 3, in `_fetch_tickets`/`_location_hierarchy`) — enough to avoid
# queuing under light-to-moderate concurrent load while still capping how
# many Firestore reads this process can have in flight at any moment. If
# request concurrency grows well past ~4 simultaneous KPI calls, later reads
# queue for a free worker (they don't fail — `ThreadPoolExecutor.submit`
# always has a queue), a graceful degradation to sequential-when-saturated,
# not overload.
_READ_POOL = ThreadPoolExecutor(max_workers=12, thread_name_prefix="kpi-read")


def _run_parallel(callables: list[Callable[[], Any]]) -> list[Any]:
    """Runs each zero-arg callable in `callables` on `_READ_POOL` and returns
    their results in the SAME ORDER as `callables` was given — never in
    whichever order the futures happen to complete — so callers can
    destructure the returned list positionally exactly as they would a
    sequence of direct calls.

    Exception propagation: `Future.result()` re-raises whatever exception the
    callable raised, in the calling thread, the first time it's called on
    that future. So if e.g. a read helper is changed later to raise an
    `HTTPException` on a malformed document, the first callable (in
    `callables` order) whose future raised is what this function re-raises —
    same as sequential code hitting that failure first. The remaining
    futures still run to completion on the pool (they are not cancelled),
    but their results/exceptions are simply discarded once this call has
    already raised.
    """
    futures = [_READ_POOL.submit(fn) for fn in callables]
    return [future.result() for future in futures]


# Same literals `add_down_time` stores the issue under — kept in sync with
# `src.app.routers.down_time.services.DOWN_TIME_COLLECTION` / `ISSUES_SUBCOLLECTION`
# (and, transitively, `src.app.async_jobs.add_down_time`).
DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"

# --------------------------------------------------------------------------
# 1. Frontend slug <-> backend enum mapping (§5bis.7).
# --------------------------------------------------------------------------

_TYPE_ID_TO_ENUM: dict[str, DownTimeType] = {
    "break_down": DownTimeType.BREAKDOWN,
    "quality_issue": DownTimeType.QUALITY_ISSUE,
    "absenteeism": DownTimeType.ABSENTEEISM,
    "wip_shortage": DownTimeType.WIP_SHORTAGE,
    "material_shortage": DownTimeType.MATERIAL_SHORTAGE,
    "setup_changeover": DownTimeType.SETUP_CHANGEOVER,
    # Fix #14: "others" now has a slug too, so `by_type`/`downtime_by_type`
    # totals reconcile with the overall/pareto totals instead of silently
    # dropping OTHERS tickets from every type-keyed breakdown.
    "others": DownTimeType.OTHERS,
}
_TYPE_ENUM_TO_ID: dict[DownTimeType, str] = {v: k for k, v in _TYPE_ID_TO_ENUM.items()}

_PROCESS_IDS = {p.value for p in Process}


def _type_id_for_ticket(issue: dict[str, Any]) -> Optional[str]:
    """Frontend slug id for `issue`'s `down_time_type`, or `None` when it's
    an unrecognized/legacy value."""
    try:
        dt_type = DownTimeType(issue.get("down_time_type"))
    except ValueError:
        return None
    return _TYPE_ENUM_TO_ID.get(dt_type)


def _process_for_ticket(issue: dict[str, Any]) -> Optional[str]:
    """The process id `issue` is owned by (§5bis.7, revision 2): read
    directly from the ticket's own stored `process` field (`add_down_time`
    always sets it, regardless of `down_time_type`) whenever it's a
    recognized process id. Falls back to `DOWNTIME_TYPE_PROCESS[down_time_type]`
    for legacy documents with no valid stored `process`. `None` when neither
    source resolves (unrecognized/legacy type and no usable stored process)."""
    process = issue.get("process")
    if process in _PROCESS_IDS:
        return process
    try:
        dt_type = DownTimeType(issue.get("down_time_type"))
    except ValueError:
        return None
    mapped = DOWNTIME_TYPE_PROCESS.get(dt_type)
    return mapped.value if mapped else None


# --------------------------------------------------------------------------
# 2. Ticket-level KPI primitives (§5bis.1/2).
# --------------------------------------------------------------------------


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _ticket_own_resource_archived_at(
    issue: dict[str, Any], hierarchy: dict[str, Any]
) -> Optional[datetime]:
    """Resource-archiving rule 2 — the `archived_at` (parsed) of the single
    MOST SPECIFIC archivable resource (workstation > production line > UAP,
    same precedence `_stored_id_rank` uses) `issue` is directly stored
    against, when that resource is in fact archived. `None` when the ticket
    carries no such id, the id doesn't resolve in `hierarchy`, or the
    resolved resource isn't archived — in every one of those cases the
    ticket's own `archived_at` bound simply doesn't apply. Never writes to
    the ticket and never reads/derives from its `status` — only the
    resource's own `archived_at` produces this bound (rule 2)."""
    workstation_id = issue.get("workstation_id")
    if workstation_id:
        station = hierarchy["stations"].get(workstation_id)
        return _parse_iso(station.get("archived_at")) if station is not None else None
    line_id = issue.get("production_line_id")
    if line_id:
        line = hierarchy["lines"].get(line_id)
        return _parse_iso(line.get("archived_at")) if line is not None else None
    uap_id = issue.get("uap_id")
    if uap_id:
        uap = hierarchy["uaps"].get(uap_id)
        return _parse_iso(uap.get("archived_at")) if uap is not None else None
    return None


def _ticket_downtime_seconds(
    issue: dict[str, Any],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    hierarchy: Optional[dict[str, Any]] = None,
) -> float:
    """A single ticket's downtime, clamped to the queried period (§5bis.1):
    closed -> `created_at -> resolved_at`; not closed -> `created_at -> now`;
    effective window = `[max(created_at, period_start), min(natural_end,
    min(period_end, now))]`, floored at 0. This clamp is what makes a
    carry-over ticket (created before `period_start`) contribute only its
    in-window slice once it's included in a downtime aggregation (fix #1).

    Resource-archiving rule 2: for a still-open (non-`CLOSED`) ticket whose
    own resource (`_ticket_own_resource_archived_at`) has since been
    archived, `natural_end` is additionally bounded at that `archived_at`
    instead of running all the way to `now` — the ticket stops accruing
    downtime the moment its workstation/line/UAP left service, even though
    its stored `status` never changes. A CLOSED ticket is never affected: its
    natural end is always `resolved_at`, archiving or not (rule 2/3 — this is
    also what keeps a bounded-but-still-open ticket out of `_mttr_seconds`,
    which only ever looks at CLOSED tickets). `hierarchy` is optional and
    defaults to `None` (no archiving awareness at all, today's exact
    behavior) so every direct unit-test call site of this function keeps
    working unchanged."""
    created_at = _parse_iso(issue.get("created_at"))
    if created_at is None:
        return 0.0
    if issue.get("status") == DownTimeStatus.CLOSED.value:
        natural_end = _parse_iso(issue.get("resolved_at")) or created_at
    else:
        natural_end = now
        if hierarchy is not None:
            archived_at = _ticket_own_resource_archived_at(issue, hierarchy)
            if archived_at is not None:
                natural_end = min(natural_end, archived_at)

    period_upper = min(period_end, now)
    effective_end = min(natural_end, period_upper)
    effective_start = max(created_at, period_start)
    return max(0.0, (effective_end - effective_start).total_seconds())


def _mttr_seconds(tickets: list[dict[str, Any]]) -> float | None:
    """§5bis.2 — mean `created_at -> resolved_at` over CLOSED tickets only
    (`None` when there are none)."""
    durations: list[float] = []
    for issue in tickets:
        if issue.get("status") != DownTimeStatus.CLOSED.value:
            continue
        created_at = _parse_iso(issue.get("created_at"))
        resolved_at = _parse_iso(issue.get("resolved_at"))
        if created_at is None or resolved_at is None:
            continue
        durations.append(max(0.0, (resolved_at - created_at).total_seconds()))
    return sum(durations) / len(durations) if durations else None


def _compute_base_kpis(
    tickets: list[dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    planned_seconds: float,
    count_tickets: Optional[list[dict[str, Any]]] = None,
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None,
    hierarchy: Optional[dict[str, Any]] = None,
) -> BaseKpis:
    """The 4 headline KPIs for a slice (§5bis.3/4/empty-slice rule;
    availability removed in revision 2). Used both for a `Kpis` object's own
    root fields and for one workstation-type division's fields (§3.2 of the
    kpi-workstation-type-slices contract) — same formula, different ticket
    weight function.

    `tickets` drives `downtime_seconds` — it may include carry-over tickets
    from outside the queried `created_at` range (fix #1). Each ticket's
    clamped downtime is multiplied by `weight_of(issue)` (§5bis.1bis,
    revision 2 — per-workstation weighting of aggregated downtime; defaults
    to a flat weight of 1 when `weight_of` is omitted, e.g. plain unit tests
    of this function). `count`/`mttr` are computed from `count_tickets` when
    given (the current-range-only tickets, never weighted) — when omitted,
    `tickets` itself is used for both (matches the original single-list
    behavior).

    `mtbf_seconds` is `None` when `planned_seconds` is not strictly positive
    (fix #3) — an unconfigured/zero denominator, or a breakdown row that
    deliberately has no planned-time denominator (fix #5, callers simply
    pass `0.0`). MTBF no longer depends on downtime at all (planned/count).

    `hierarchy`, when given, is threaded straight through to
    `_ticket_downtime_seconds` so a still-open ticket on an archived resource
    is bounded at its `archived_at` (resource-archiving rule 2) instead of
    running to `now`. `None` (the default) keeps every direct unit-test call
    site of this function on today's exact behavior.
    """
    count_source = tickets if count_tickets is None else count_tickets
    weight_fn = weight_of if weight_of is not None else _flat_weight
    downtime = sum(
        _ticket_downtime_seconds(issue, period_start, period_end, now, hierarchy)
        * weight_fn(issue)
        for issue in tickets
    )
    count = len(count_source)
    mttr = _mttr_seconds(count_source)
    if planned_seconds <= 0:
        mtbf: Optional[float] = None
    else:
        mtbf = None if count == 0 else planned_seconds / count
    return BaseKpis(
        downtime_seconds=int(round(downtime)),
        count=count,
        mttr_seconds=int(round(mttr)) if mttr is not None else None,
        mtbf_seconds=int(round(mtbf)) if mtbf is not None else None,
    )


def _widen_kpis(
    base: BaseKpis,
    bottleneck: Optional[BaseKpis] = None,
    critical: Optional[BaseKpis] = None,
) -> Kpis:
    """The single `BaseKpis` -> `Kpis` widening point (kpi-workstation-type-
    slices §9 hygiene) — every call site that needs a `Kpis` from a computed
    `BaseKpis` goes through here, so the two are never allowed to drift
    (e.g. one call site casting/copying fields by hand while another uses a
    different shortcut)."""
    return Kpis(**base.model_dump(), bottleneck=bottleneck, critical=critical)


def _compute_kpis(
    tickets: list[dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    planned_seconds: float,
    count_tickets: Optional[list[dict[str, Any]]] = None,
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None,
    type_weight_fn: Optional[Callable[[dict[str, Any]], dict[str, int]]] = None,
    perimeter_type_counts: Optional[dict[str, int]] = None,
    hierarchy: Optional[dict[str, Any]] = None,
) -> Kpis:
    """`_compute_base_kpis` plus, optionally, the `bottleneck`/`critical`
    divisions (kpi-workstation-type-slices §3).

    `hierarchy`, when given, is forwarded to `_compute_base_kpis`/
    `_compute_type_slice` for resource-archiving rule 2's open-ticket bound
    — see `_compute_base_kpis`'s own docstring. `None` (default) is today's
    behavior, unchanged.

    `type_weight_fn` and `perimeter_type_counts` are an all-or-nothing pair:
    passing only one is a caller bug (there is no way to compute a slice
    without both — the per-ticket type weight AND the perimeter's own
    workstation-type composition), so it raises rather than silently
    producing a base-only `Kpis` some callers might mistake for "no slices
    applicable" (§9 hygiene — "impossible to call with a base model AND
    slice arguments" in an inconsistent way). Passing NEITHER is the normal
    "not applicable" case (`by_type`, a `station`-kind row, pareto/repair,
    ...) and simply returns `bottleneck=None, critical=None`.
    """
    if (type_weight_fn is None) != (perimeter_type_counts is None):
        raise ValueError(
            "_compute_kpis: type_weight_fn and perimeter_type_counts must be "
            "given together, or not at all."
        )
    base = _compute_base_kpis(
        tickets,
        period_start,
        period_end,
        now,
        planned_seconds,
        count_tickets,
        weight_of,
        hierarchy,
    )
    if type_weight_fn is None or perimeter_type_counts is None:
        return _widen_kpis(base)

    count_source = tickets if count_tickets is None else count_tickets
    bottleneck = _compute_type_slice(
        tickets,
        count_source,
        period_start,
        period_end,
        now,
        planned_seconds,
        type_weight_fn,
        perimeter_type_counts,
        WorkstationType.BOTTLENECK.value,
        hierarchy,
    )
    critical = _compute_type_slice(
        tickets,
        count_source,
        period_start,
        period_end,
        now,
        planned_seconds,
        type_weight_fn,
        perimeter_type_counts,
        WorkstationType.CRITICAL.value,
        hierarchy,
    )
    return _widen_kpis(base, bottleneck=bottleneck, critical=critical)


def _compute_type_slice(
    tickets: list[dict[str, Any]],
    count_tickets: list[dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    planned_seconds: float,
    type_weight_fn: Callable[[dict[str, Any]], dict[str, int]],
    perimeter_type_counts: dict[str, int],
    type_key: str,
    hierarchy: Optional[dict[str, Any]] = None,
) -> Optional[BaseKpis]:
    """One `bottleneck`/`critical` division (§3.1/§3.2). `None` when the
    perimeter (`perimeter_type_counts`, precomputed once per request, never
    rebuilt per ticket — §9 performance) holds no workstation of `type_key`
    at all; present-with-zeros when it does but nothing in `tickets`/
    `count_tickets` weighs into this type this period.

    `count`/`mttr_seconds` are this type's OWN mean over the tickets that
    touch at least one `type_key` workstation in `count_tickets` (current
    -range only, unweighted, mirroring the root's own `count`/`mttr`) — a
    ticket touching both a bottleneck and a critical workstation counts once
    in EACH slice (§5), so slice counts do not sum to the root's `count`.
    `mtbf_seconds` reuses the SAME `planned_seconds` denominator as the
    object's own root (never a new one) divided by this slice's own count.

    `hierarchy`, forwarded to `_ticket_downtime_seconds`, keeps this slice's
    own downtime sum consistent with the root's (resource-archiving rule 2 —
    an open ticket on an archived resource is bounded here exactly like it
    is at the root, never left to run to `now` in one and not the other).
    """
    if perimeter_type_counts.get(type_key, 0) <= 0:
        return None

    def _weight(issue: dict[str, Any]) -> int:
        return type_weight_fn(issue).get(type_key, 0)

    downtime = sum(
        _ticket_downtime_seconds(issue, period_start, period_end, now, hierarchy)
        * _weight(issue)
        for issue in tickets
    )
    slice_count_tickets = [issue for issue in count_tickets if _weight(issue) > 0]
    count = len(slice_count_tickets)
    mttr = _mttr_seconds(slice_count_tickets)
    if planned_seconds <= 0:
        mtbf: Optional[float] = None
    else:
        mtbf = None if count == 0 else planned_seconds / count
    return BaseKpis(
        downtime_seconds=int(round(downtime)),
        count=count,
        mttr_seconds=int(round(mttr)) if mttr is not None else None,
        mtbf_seconds=int(round(mtbf)) if mtbf is not None else None,
    )


# --------------------------------------------------------------------------
# 3. Planned time (§5bis.3).
# --------------------------------------------------------------------------


def _parse_hhmm(value: str) -> Optional[int]:
    """Tolerant `"HH:MM"` -> minutes-since-midnight parse (fix #9): an
    unparsable stored shift window logs a warning and returns `None` instead
    of raising, so a corrupted settings document degrades that one shift
    (skipped) rather than 500ing the whole KPI request."""
    try:
        return _strict_parse_hhmm(value)
    except (ValueError, AttributeError):
        logger.warning("kpi: unparsable shift clock time %r, skipping shift.", value)
        return None


def _valid_break(shift: dict[str, Any]) -> Optional[tuple[int, int, int]]:
    """`(break_start_min, break_end_min, break_len_min)` — minutes-since
    -midnight bounds of `shift`'s break, plus its validated length — the
    single validate-and-parse routine shared by `_break_window` (offset
    -from-shift-start space, used by `_elapsed_shift_seconds`'s default
    mode) and `_elapsed_shift_seconds`'s current-day-only mode (real
    clock-time space, via `clock_window_elapsed_since_midnight`).

    `None` when the shift has no break (either field absent/`None` —
    includes legacy documents with a residual `break_minutes`, which is
    ignored) or when the pair fails `break_minutes_in_window`'s validation
    (unparsable clock time, or a corrupted/out-of-window pair on a stored
    document that predates request-time validation): same tolerant-degrade
    philosophy as fix #9 — logged once here, the break is ignored rather
    than failing the whole request."""
    break_start = shift.get("break_start_time")
    break_end = shift.get("break_end_time")
    if not break_start or not break_end:
        return None
    start = _parse_hhmm(shift.get("start_time", ""))
    break_start_min = _parse_hhmm(break_start)
    break_end_min = _parse_hhmm(break_end)
    if start is None or break_start_min is None or break_end_min is None:
        return None
    try:
        break_len_minutes = break_minutes_in_window(
            shift.get("start_time", ""), shift.get("end_time", ""), break_start, break_end
        )
    except ValueError:
        logger.warning(
            "kpi: unparsable/invalid shift break %r/%r, ignoring break.",
            break_start,
            break_end,
        )
        return None
    return break_start_min, break_end_min, break_len_minutes


def _break_window(shift: dict[str, Any]) -> Optional[tuple[float, float]]:
    """`(break_start_offset_seconds, break_length_seconds)`, `break_start_offset`
    measured as a circular "distance since the shift's own start" (same
    convention as `_elapsed_shift_seconds`'s default-mode `window_elapsed` —
    this is what lets both midnight-wrap without a cascade of special cases:
    a break is just another point expressed in the same offset space as
    "now"). `None` per `_valid_break`'s degrade rules."""
    start = _parse_hhmm(shift.get("start_time", ""))
    parsed = _valid_break(shift)
    if start is None or parsed is None:
        return None
    break_start_min, _break_end_min, break_len_minutes = parsed
    offset_minutes = (break_start_min - start) % (24 * 60)
    return offset_minutes * 60.0, break_len_minutes * 60.0


def _break_seconds(shift: dict[str, Any]) -> float:
    """The shift's break duration in seconds (revision 3, §5bis.4bis) — see
    `_break_window` for the validation/degrade rules. `0.0` when the shift
    has no (valid) break."""
    window = _break_window(shift)
    return window[1] if window is not None else 0.0


def _shift_window_seconds(shift: dict[str, Any]) -> Optional[float]:
    """One shift's planned seconds: its clock window length (midnight-wrap
    aware) minus its break's duration, if any (revision 3, §5bis.4bis —
    replaces the revision-2 `break_minutes`, itself removed in favor of
    `break_start_time`/`break_end_time`). `None` when the window itself
    doesn't parse; an unparsable/invalid break degrades to "no break"
    (`_break_seconds`) rather than failing the whole shift."""
    start = _parse_hhmm(shift.get("start_time", ""))
    end = _parse_hhmm(shift.get("end_time", ""))
    if start is None or end is None:
        return None
    length_minutes = (end - start) if end > start else (24 * 60 - start) + end
    return float(length_minutes * 60) - _break_seconds(shift)


def _configured_shifts(settings: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """`[("1", shift_1_dict), ...]` for the first `shift_number` shifts that
    actually carry a (parsable) window. Empty when the namespace has no
    settings, its shifts have no configured windows, or every configured
    window is unparsable (fix #9 — such a shift is skipped, not fatal)."""
    shift_number = settings.get("shift_number", 1)
    shifts: list[tuple[str, dict[str, Any]]] = []
    for i in range(1, shift_number + 1):
        shift = settings.get(f"shift_{i}")
        if not (isinstance(shift, dict) and shift.get("start_time") and shift.get("end_time")):
            continue
        if _shift_window_seconds(shift) is None:
            continue
        shifts.append((str(i), shift))
    return shifts


def _planned_seconds_per_day(
    settings: dict[str, Any], shift_filter: Optional[str] = None
) -> float:
    """Planned production seconds per day. `shift_filter` narrows to a single
    shift's own window (0 when that shift isn't configured). With no filter:
    sum of every configured shift's window, or 24h/day when the namespace has
    no settings/no configured shift windows at all."""
    shifts = _configured_shifts(settings)
    if shift_filter is not None:
        shifts = [(sid, shift) for sid, shift in shifts if sid == shift_filter]
        return sum(_shift_window_seconds(shift) or 0.0 for _, shift in shifts)
    if not shifts:
        return 24.0 * 3600.0
    return sum(_shift_window_seconds(shift) or 0.0 for _, shift in shifts)


def _seconds_of_day(dt: datetime) -> float:
    return dt.hour * 3600.0 + dt.minute * 60.0 + dt.second + dt.microsecond / 1_000_000.0


def _elapsed_shift_seconds(
    shift: dict[str, Any], now_local: datetime, current_day_only: bool = False
) -> float:
    """Seconds **actually worked** in `shift`, net of its break (revision 3,
    §5bis.4bis; client decision: no more proration, this IS the real worked
    time, not an estimate of it). Two modes, selected by `current_day_only`:

    - `current_day_only=False` (default) — the **current or most recent
      instance**'s progress by `now_local`'s time-of-day: that instance's raw
      clock-window elapsed time, net of break. Unchanged from before this
      mode existed; every existing caller keeps this behavior.
    - `current_day_only=True` — how much of the shift's window (and its
      break) TODAY's civil day has occupied by `now_local`
      (`clock_window_elapsed_since_midnight`), net of whatever part of the
      break has elapsed under that same civil-day measurement.

    Both modes agree exactly for a shift whose window doesn't cross midnight
    (the whole window lives on one civil day already, so "this instance's
    progress" and "today's civil-day occupation" are the same slice). They
    only diverge for a midnight-wrapping shift (`end_time <= start_time`,
    e.g. 22:00->06:00): `current_day_only=False` saturates to the full
    window once the current/most recent instance has completed (see below);
    `current_day_only=True` instead sums BOTH pieces of today's civil day
    that the window touches — the tail of last night's instance, `[0,
    end_time)`, plus however much of tonight's instance has run so far,
    `[start_time, now_local]` — since a midnight-wrapping window can occupy
    two disjoint slices of one civil day. Concretely, for 22:00->06:00:
    05:00 -> 5h, 10:00 -> 6h, 21:59 -> 6h, 22:00 -> 6h, 23:00 -> 7h
    (`clock_window_elapsed_since_midnight`).

    Break netting, both modes, follows the same principle as the window
    itself — measure the break exactly like the window, so the two stay
    consistent:
    - `current_day_only=False`: the raw window-elapsed time and the break's
      own start are compared as circular "distance since the shift's
      start" offsets (`window_elapsed` / `_break_window`'s offset) — before
      the break starts -> unchanged; during the break -> pinned to the
      elapsed time AT the break's start; after the break ends -> its full
      duration is deducted. Comparing two offsets in the same space is what
      makes the midnight-wrap case correct without extra special-casing.
    - `current_day_only=True`: window and break are both literal clock
      positions on today's civil day, so applying
      `clock_window_elapsed_since_midnight` directly to the break's own
      real clock bounds and subtracting is already coherent — entirely
      elapsed -> deducted in full; `now_local` mid-break -> only the
      elapsed part is deducted; not yet reached -> nothing deducted; and
      for a midnight-wrapping break, both of its own civil-day pieces are
      summed the same way the shift's window is.
    Example — the client's break case, 22:00->06:00 shift, break
    23:30->00:30, `now_local` = 23:45: window 7h45 (civil-day occupation),
    break 45min elapsed (yesterday's 00:00->00:30 tail + tonight's
    23:30->23:45 so far) -> net 7h.

    For a non-wrapping shift, `current_day_only=False` saturates to the full
    window (net of break) once `now_local` is past `end_time`, and stays
    there until the next instance starts the following day. For a
    midnight-wrapping shift, the *current or most recent* instance is: the
    one running now if `now_local` is inside `[start_time, 24h)` or `[0,
    end_time]`; otherwise — `now_local` is past that instance's end and
    before its next start — the most recent instance already ran to
    completion, so this also saturates to the full window (net of break),
    exactly like the non-wrapping case. It resets to 0 only at the exact
    instant the next instance starts.

    Clamped to `[0, _shift_window_seconds(shift)]`. Midnight-wrap aware. A
    shift with no (valid) break falls back to the raw elapsed time unchanged;
    an unparsable window returns 0."""
    start = _parse_hhmm(shift.get("start_time", ""))
    end = _parse_hhmm(shift.get("end_time", ""))
    if start is None or end is None:
        return 0.0
    start_sec, end_sec = start * 60.0, end * 60.0
    now_sec = _seconds_of_day(now_local)

    if current_day_only:
        window_elapsed = clock_window_elapsed_since_midnight(now_sec, start_sec, end_sec)
        parsed_break = _valid_break(shift)
        if parsed_break is None:
            return window_elapsed

        # Window and break are both literal clock positions on today's
        # civil day, so applying the SAME primitive directly to the break's
        # own real clock bounds and subtracting is already coherent — this
        # is what keeps the two measurements (window/break) consistent with
        # each other under the "civil day occupation" semantics.
        break_start_min, break_end_min, _break_len_min = parsed_break
        break_elapsed = clock_window_elapsed_since_midnight(
            now_sec, break_start_min * 60.0, break_end_min * 60.0
        )
        return max(0.0, window_elapsed - break_elapsed)

    if end_sec > start_sec:
        window_elapsed = min(max(now_sec - start_sec, 0.0), end_sec - start_sec)
    else:
        # Midnight-wrap window: [start, 24h) followed by [0, end).
        day_sec = 24 * 3600.0
        if now_sec >= start_sec:
            window_elapsed = now_sec - start_sec
        elif now_sec <= end_sec:
            window_elapsed = (day_sec - start_sec) + now_sec
        else:
            # `now` is past this shift's end and before its next start: the
            # most recent instance (the one that started the previous day)
            # already ran to completion. Saturate to the full window length
            # instead of falling back to 0 — same value the branch above
            # converges to as `now_sec` -> `end_sec`, so this is its natural
            # continuation, not a separate case.
            window_elapsed = (day_sec - start_sec) + end_sec

    break_window = _break_window(shift)
    if break_window is None:
        return window_elapsed
    break_offset, break_len = break_window
    if window_elapsed <= break_offset:
        return window_elapsed
    if window_elapsed >= break_offset + break_len:
        return window_elapsed - break_len
    return break_offset


def _planned_seconds(
    settings: dict[str, Any],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    shift_filter: Optional[str] = None,
) -> float:
    """Planned production seconds over `[period_start, min(period_end,
    now)]` (fix #2): whole elapsed days each count their full per-day
    planned time; if the queried period isn't over yet (`now < period_end`),
    the still-in-progress final day counts each configured shift's actually
    -worked time so far TODAY (namespace-local), net of its break, per
    `_elapsed_shift_seconds(..., current_day_only=True)` (revision 3,
    §5bis.4bis — no more proration: the elapsed-time computation IS the real
    worked time, not an estimate of it; revision 4 — `current_day_only=True`
    specifically, not the default mode: for a midnight-wrapping shift the
    default mode measures progress through that shift's own *instance*,
    which for e.g. a 22:00->06:00 shift queried at 10:00 today would count
    the full 8h instance (started yesterday 22:00) as "today's" planned time
    — overcounting by the ~2h that actually belongs to yesterday. The
    current-day mode instead reports how much of TODAY's civil day the
    shift's window has occupied (§5bis.4bis; see
    `clock_window_elapsed_since_midnight`): for that same 22:00->06:00 shift,
    that's the tail of yesterday's instance (`[0, 06:00)`) PLUS however much
    of tonight's instance has run so far (`[22:00, now]`) — a midnight
    -wrapping window can occupy two disjoint slices of one civil day, and
    both count toward today's planned time.

    Full-elapsed-days term (`per_day * full_days` below) stays exact
    regardless: it's `_planned_seconds_per_day`'s own per-day total (the
    same figure this module already uses everywhere else for a fully
    -elapsed day), multiplied by the day count — entirely independent of
    `_elapsed_shift_seconds`/`current_day_only`. This is exact even for a
    midnight-wrapping shift: each civil day's two disjoint slices
    (yesterday's tail + tonight's start) sum to exactly one full window's
    worth of planned time, so per-day totals still add up correctly across
    a multi-day range. Only the LAST, still-open day uses the
    current-day-only treatment, and only for that day.

    0 when the effective window is empty or there's no positive planned time
    at all."""
    effective_end = min(period_end, now)

    if effective_end <= period_start:
        return 0.0

    per_day = _planned_seconds_per_day(settings, shift_filter)
    if per_day <= 0:
        return 0.0

    if effective_end == period_end:
        # The whole queried period has already elapsed — no proration.
        days = (period_end.date() - period_start.date()).days + 1
        return per_day * days

    full_days = (effective_end.date() - period_start.date()).days
    shifts = _configured_shifts(settings)
    if shift_filter is not None:
        shifts = [(sid, shift) for sid, shift in shifts if sid == shift_filter]

    if not shifts:
        # No configured shift windows -> implicit single 24h/day "shift"
        # starting at local midnight.
        last_day_planned = min(_seconds_of_day(effective_end), 24 * 3600.0)
    else:
        last_day_planned = sum(
            _elapsed_shift_seconds(shift, effective_end, current_day_only=True)
            for _, shift in shifts
        )

    return per_day * full_days + last_day_planned


# --------------------------------------------------------------------------
# 4. Location hierarchy + ticket -> location resolution.
# --------------------------------------------------------------------------


def _location_hierarchy(client: FirestoreClient, namespace_id: str) -> dict[str, Any]:
    # Resource-archiving rule 1: every UAP/line/workstation is loaded
    # unconditionally here, archived or not (no `is_active` filtering at
    # load time) -- their past tickets still need attributing to them for
    # KPI history, archiving must never erase it. Downstream callers decide
    # per-ticket, per-rule whether a given archived resource still counts
    # (rule 2's open-ticket bound, rule 4's perimeter-at-ticket-date).
    #
    # 3 independent collection scans -- parallelized (see `_run_parallel`).
    # Order is preserved regardless of which future finishes first.
    uaps, lines, stations = _run_parallel(
        [
            lambda: client.find_documents(UAP_COLLECTION, {"namespace_id": namespace_id}),
            lambda: client.find_documents(
                PRODUCTION_LINE_COLLECTION, {"namespace_id": namespace_id}
            ),
            lambda: client.find_documents(
                WORKSTATION_COLLECTION, {"namespace_id": namespace_id}
            ),
        ]
    )

    lines_by_uap: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in lines:
        if line.get("uap_id"):
            lines_by_uap[line["uap_id"]].append(line)

    stations_by_line: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for station in stations:
        if station.get("production_line_id"):
            stations_by_line[station["production_line_id"]].append(station)

    # Perf (review W3): precompute the per-UAP workstation count once here
    # instead of re-summing `stations_by_line` over `lines_by_uap` every time
    # `_row_weight`/`_locations_for_ticket` need a UAP's total — with 300
    # stations and 2000 tickets that re-sum was happening per ticket per row.
    uap_station_counts: dict[str, int] = {
        uap_id: sum(len(stations_by_line.get(line["id"], [])) for line in lines_here)
        for uap_id, lines_here in lines_by_uap.items()
    }

    # Resource-archiving rule 4 — `_row_weight`'s "uap" spread branch needs
    # the actual station DOCUMENTS under a UAP (not just their count) to
    # filter them by `archived_at` relative to each ticket's own
    # `created_at`, so a raw per-UAP station list is precomputed once here,
    # alongside `uap_station_counts`, mirroring `stations_by_line` at the
    # line level -- never rebuilt per ticket per row.
    stations_by_uap: dict[str, list[dict[str, Any]]] = {
        uap_id: [s for line in lines_here for s in stations_by_line.get(line["id"], [])]
        for uap_id, lines_here in lines_by_uap.items()
    }

    # kpi-workstation-type-slices §9 performance — the per-perimeter
    # workstation-TYPE counts, precomputed ONCE per request right alongside
    # the rest of the hierarchy, exactly like `uap_station_counts` above:
    # `_row_type_weights`/the `overall`/`by_shift` slices must never rebuild
    # a ticket's station-type tally per `(row, type)` pair.
    type_counts_by_line: dict[str, dict[str, int]] = {}
    for line_id, stations_here in stations_by_line.items():
        counts = _empty_type_counts()
        for station in stations_here:
            counts[_station_type(station)] += 1
        type_counts_by_line[line_id] = counts
    type_counts_by_uap: dict[str, dict[str, int]] = {}
    for uap_id, lines_here in lines_by_uap.items():
        counts = _empty_type_counts()
        for line in lines_here:
            for type_key, type_count in type_counts_by_line.get(line["id"], {}).items():
                counts[type_key] += type_count
        type_counts_by_uap[uap_id] = counts
    type_counts_namespace = _empty_type_counts()
    for station in stations:
        type_counts_namespace[_station_type(station)] += 1

    return {
        "uaps": {u["id"]: u for u in uaps},
        "lines": {l["id"]: l for l in lines},
        "stations": {s["id"]: s for s in stations},
        "lines_by_uap": dict(lines_by_uap),
        "stations_by_line": dict(stations_by_line),
        "line_to_uap": {l["id"]: l.get("uap_id") for l in lines},
        "station_to_line": {s["id"]: s.get("production_line_id") for s in stations},
        "uap_station_counts": uap_station_counts,
        "stations_by_uap": stations_by_uap,
        "type_counts_by_line": type_counts_by_line,
        "type_counts_by_uap": type_counts_by_uap,
        "type_counts_namespace": type_counts_namespace,
    }


def _resolved_stations_from_ids(issue: dict[str, Any], hierarchy: dict[str, Any]) -> set[str]:
    """Legacy fallback (§9.1 fix): the CONCRETE, real station ids resolvable
    from the most specific of the ticket's own stored `workstation_id` /
    `production_line_id` / `uap_id` (none of the three -> plant-wide, every
    real station). May be EMPTY — an unresolved `workstation_id` (absent
    from the hierarchy, e.g. a since-deleted workstation), a line/UAP with
    no workstations under it, or (degenerate) a namespace with none at all.
    `_weight_from_ids` derives its floored-at-1 count from this same set, so
    the two can never disagree; `_ticket_type_weights` uses the set itself
    to know exactly WHICH real stations (hence types) the weight belongs to,
    falling back to the unexposed `standard` share when it's empty (§5)."""
    if issue.get("workstation_id"):
        wid = issue["workstation_id"]
        return {wid} if wid in hierarchy["stations"] else set()
    line_id = issue.get("production_line_id")
    if line_id:
        return {s["id"] for s in hierarchy["stations_by_line"].get(line_id, [])}
    uap_id = issue.get("uap_id")
    if uap_id:
        lines = hierarchy["lines_by_uap"].get(uap_id, [])
        ids: set[str] = set()
        for line in lines:
            ids.update(s["id"] for s in hierarchy["stations_by_line"].get(line["id"], []))
        return ids
    return set(hierarchy["stations"].keys())


def _weight_from_ids(issue: dict[str, Any], hierarchy: dict[str, Any]) -> int:
    """Legacy fallback: infers a weight from the most specific of the
    ticket's own stored `workstation_id` / `production_line_id` / `uap_id`
    (none of the three -> plant-wide); floored at 1 so a line/UAP with no
    workstations referenced under it still counts as 1, never 0. Used by
    `_ticket_weight` only when `down_time_scope` is absent/unrecognized, or
    names a level whose id the ticket doesn't actually carry. Derived from
    `_resolved_stations_from_ids` (§9.1 fix) so the root weight and the
    concrete station set behind it can never disagree."""
    return max(1, len(_resolved_stations_from_ids(issue, hierarchy)))


def _ticket_stations_raw(issue: dict[str, Any], hierarchy: dict[str, Any]) -> set[str]:
    """§9.1 fix — the CONCRETE, real station ids `issue`'s scope resolves to,
    mirroring `_ticket_weight`'s own branching on `down_time_scope` exactly
    (same order, same fallbacks), but returning the actual station id set
    instead of just its count. Deliberately UNFILTERED by archiving — this is
    the RAW resolution, whose emptiness means "there was nothing to resolve"
    (a since-deleted workstation, a line/UAP with no workstations under it),
    which is exactly the signal `_ticket_weight`/`_row_weight` need to tell
    that case apart from resource-archiving rule 4's "resolved to something,
    then all of it was archived before this ticket" — see `_ticket_stations`
    for the rule-4-filtered view built on top of this one, and the module
    docstring's "subtle trap" note for why the two must stay distinct
    functions rather than being collapsed into one.

    May be EMPTY (unresolved reference / empty line-or-UAP) —
    `_ticket_type_weights` is what turns that into the unexposed `standard`
    share instead of silently vanishing."""
    scope = issue.get("down_time_scope")
    if scope == ProductionScope.WORK_STATION.value:
        wid = issue.get("workstation_id")
        if wid:
            return {wid} if wid in hierarchy["stations"] else set()
        return _resolved_stations_from_ids(issue, hierarchy)
    if scope == ProductionScope.PRODUCTION_LINE.value:
        line_id = issue.get("production_line_id")
        if line_id:
            return {s["id"] for s in hierarchy["stations_by_line"].get(line_id, [])}
        return _resolved_stations_from_ids(issue, hierarchy)
    if scope == ProductionScope.UAP.value:
        uap_id = issue.get("uap_id")
        if uap_id:
            lines = hierarchy["lines_by_uap"].get(uap_id, [])
            ids: set[str] = set()
            for line in lines:
                ids.update(s["id"] for s in hierarchy["stations_by_line"].get(line["id"], []))
            return ids
        return _resolved_stations_from_ids(issue, hierarchy)
    if scope == ProductionScope.PLANT.value:
        return set(hierarchy["stations"].keys())
    # Absent/unrecognized `down_time_scope` (legacy document) -> infer.
    return _resolved_stations_from_ids(issue, hierarchy)


def _active_at_ticket_date(resource: dict[str, Any], created_at: Optional[datetime]) -> bool:
    """Resource-archiving rule 4's perimeter predicate — whether `resource`
    still counts in a ticket dated `created_at`: never archived at all
    (`archiving.is_active`, the shared predicate — reused rather than
    re-implementing `not resource.get("archived_at")` here), or archived
    STRICTLY AFTER `created_at`. Equality does NOT satisfy "strictly after"
    (the pinned boundary convention, `TestPerimeterBoundary`) — a resource
    archived at the exact instant the ticket was created is excluded, same as
    one archived earlier. `created_at is None` (a ticket with no parsable
    `created_at` at all) conservatively excludes an archived resource — there
    is no date to compare `archived_at` against."""
    if is_active(resource):
        return True
    if created_at is None:
        return False
    archived_at = _parse_iso(resource.get("archived_at"))
    return archived_at is not None and archived_at > created_at


def _active_station_ids(
    station_ids: set[str], hierarchy: dict[str, Any], created_at: Optional[datetime]
) -> set[str]:
    """`station_ids` narrowed to the ones still active at `created_at`
    (`_active_at_ticket_date`). A station id absent from `hierarchy["stations"]`
    defaults to ACTIVE (kept, never dropped) rather than excluded — in
    production every id in `station_ids` is always drawn from that same dict
    (`_location_hierarchy` builds both from the one `stations` read), so this
    only ever matters for a caller/test passing a partial hierarchy that
    doesn't carry a document for an id it otherwise knows about; degrading to
    "assume active" there preserves today's pre-archiving behavior instead of
    silently zeroing out an otherwise-resolved perimeter."""
    return {
        sid
        for sid in station_ids
        if _active_at_ticket_date(hierarchy["stations"].get(sid, {}), created_at)
    }


def _ticket_stations(issue: dict[str, Any], hierarchy: dict[str, Any]) -> set[str]:
    """Resource-archiving rule 4 — `_ticket_stations_raw` narrowed to the
    stations still active at `issue`'s own `created_at`
    (`_active_station_ids`). This is the set every caller that needs the
    ticket's TRUE current-perimeter attribution (the type split, the weight
    below) must use; `_ticket_stations_raw` remains separately available
    purely to tell "empty because unresolvable" apart from "empty because
    entirely archived before this ticket" — see that function's docstring."""
    created_at = _parse_iso(issue.get("created_at"))
    return _active_station_ids(_ticket_stations_raw(issue, hierarchy), hierarchy, created_at)


def _ticket_weight(issue: dict[str, Any], hierarchy: dict[str, Any]) -> int:
    """§5bis.1bis (revision 2) — number of workstations `issue`'s scope
    affects, the weight every downtime-seconds sum multiplies that ticket's
    clamped duration by. Branches on the ticket's own stored
    `down_time_scope` (the `ProductionScope` value `add_down_time` stores,
    review fix W1) first — a ticket declared at UAP level weighs the UAP's
    workstations even if it also carries a (legitimate, contextual)
    `production_line_id`/`workstation_id`. Falls back to inferring the scope
    from the most specific id present (`_weight_from_ids`) only for legacy
    documents with no `down_time_scope`, an unrecognized value, or a stored
    scope whose own id field is missing from the ticket.

    Resource-archiving rule 4 (the module docstring's "subtle trap"): the
    floor-at-1 is preserved for its ORIGINAL case and suppressed for the new
    one. `_ticket_stations_raw` empty -> nothing was resolvable at all
    (missing/unresolvable data, the floor's original justification) -> 1.
    `_ticket_stations_raw` non-empty -> something WAS resolved, so the weight
    is the count of it still active at the ticket's own `created_at`
    (`_ticket_stations`) — deliberately NOT floored, so a perimeter that
    resolved to something and then was entirely archived before this ticket
    correctly weighs 0, rather than inventing a workstation that no longer
    existed when the ticket was opened."""
    raw = _ticket_stations_raw(issue, hierarchy)
    if not raw:
        return 1
    created_at = _parse_iso(issue.get("created_at"))
    return len(_active_station_ids(raw, hierarchy, created_at))


def _weight_of_builder(hierarchy: dict[str, Any]) -> Callable[[dict[str, Any]], int]:
    """A `weight_of` closure over `hierarchy`, built once per request and
    threaded through every downtime-sum computation (`_compute_kpis` and the
    process/shift/type aggregations). Memoizes per ticket id (review I2 — a
    ticket is otherwise re-weighed once per aggregation it appears in,
    ~5-6x per dashboard request); falls back to a direct (uncached) call when
    a ticket has no `id`."""
    cache: dict[str, int] = {}

    def weight_of(issue: dict[str, Any]) -> int:
        issue_id = issue.get("id")
        if issue_id is None:
            return _ticket_weight(issue, hierarchy)
        if issue_id not in cache:
            cache[issue_id] = _ticket_weight(issue, hierarchy)
        return cache[issue_id]

    return weight_of


def _flat_weight(_issue: dict[str, Any]) -> int:
    """Default `weight_of` (flat weight 1) used when a caller omits it —
    keeps every downtime-sum helper directly unit-testable without a
    hierarchy fixture."""
    return 1


# --------------------------------------------------------------------------
# 4bis. Workstation-type slices (kpi-workstation-type-slices contract) —
# `bottleneck`/`critical` divisions of every `Kpis` object.
#
# The one invariant this section exists to guarantee: for ANY ticket shape,
# `sum(_ticket_type_weights(issue, hierarchy).values()) ==
# _ticket_weight(issue, hierarchy)`, by construction — both are plain
# derivations of the SAME concrete station set (`_ticket_stations`), never
# two independently-maintained numbers that can drift apart (the defect an
# earlier attempt shipped: the root used `_ticket_weight`'s fallback chain,
# the slices used a fallback-less, set-intersection-only computation, and
# the two disagreed on any ticket shape with a missing/unresolved id).
# --------------------------------------------------------------------------


def _empty_type_counts() -> dict[str, int]:
    return {t.value: 0 for t in WorkstationType}


def _station_type(station: dict[str, Any]) -> str:
    """A workstation's type, `standard` for a legacy document with no stored
    `type` (or an unrecognized value) — §5 of the contract."""
    try:
        return WorkstationType(station.get("type")).value
    except ValueError:
        return WorkstationType.STANDARD.value


def _tally_station_types(
    station_ids: set[str], hierarchy: dict[str, Any]
) -> dict[str, int]:
    """`{type: count}` over the real stations in `station_ids` (a station id
    absent from the hierarchy is never expected here — callers only ever
    pass ids drawn from `hierarchy["stations"]` itself)."""
    counts = _empty_type_counts()
    for station_id in station_ids:
        station = hierarchy["stations"].get(station_id)
        counts[_station_type(station)] += 1 if station is not None else 0
    return counts


def _ticket_type_weights(issue: dict[str, Any], hierarchy: dict[str, Any]) -> dict[str, int]:
    """§3.2/§9.1 — `issue`'s root weight (`_ticket_weight`), split by
    workstation type. Always sums to exactly `_ticket_weight(issue,
    hierarchy)`, so it mirrors `_ticket_weight`'s own raw-vs-filtered
    branching (resource-archiving rule 4) exactly: when
    `_ticket_stations_raw` is empty (an unresolved `workstation_id`, or a
    line/UAP with no workstations under it — §5's "unresolved reference"
    rule, the floor's original case), the whole floored-at-1 weight is
    attributed to the unexposed `standard` share rather than vanishing or
    landing in a real type. When it's non-empty, this is a plain per-type
    tally of `_ticket_stations` (the rule-4-filtered, active-at-ticket-date
    set `_ticket_weight` is itself `len()` of) — which may total 0 when
    every resolved station was archived before this ticket, exactly like
    `_ticket_weight` in that same case (never floored here either)."""
    raw = _ticket_stations_raw(issue, hierarchy)
    if not raw:
        counts = _empty_type_counts()
        counts[WorkstationType.STANDARD.value] = 1
        return counts
    return _tally_station_types(_ticket_stations(issue, hierarchy), hierarchy)


def _ticket_type_weight_fn_builder(
    hierarchy: dict[str, Any],
) -> Callable[[dict[str, Any]], dict[str, int]]:
    """A `type_weight_fn` closure over `hierarchy`, memoized per ticket id —
    the type-weight analogue of `_weight_of_builder`, used wherever the
    OBJECT's perimeter is the whole namespace (`overall`, `by_shift` rows,
    a drill-down with a `shift` step but no location step)."""
    cache: dict[str, dict[str, int]] = {}

    def type_weight_of(issue: dict[str, Any]) -> dict[str, int]:
        issue_id = issue.get("id")
        if issue_id is None:
            return _ticket_type_weights(issue, hierarchy)
        if issue_id not in cache:
            cache[issue_id] = _ticket_type_weights(issue, hierarchy)
        return cache[issue_id]

    return type_weight_of


def _resolve_location(
    issue: dict[str, Any], hierarchy: dict[str, Any]
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """`(uap_id, line_id, station_id)` attributable to `issue`, rolling a
    workstation ticket up to its line's UAP (and a line ticket up to its
    UAP) via the hierarchy — not just the ticket's own stored ids."""
    station_id = issue.get("workstation_id")
    line_id = issue.get("production_line_id")
    uap_id = issue.get("uap_id")
    if station_id and not line_id:
        line_id = hierarchy["station_to_line"].get(station_id)
    if line_id and not uap_id:
        uap_id = hierarchy["line_to_uap"].get(line_id)
    return uap_id, line_id, station_id


# §2 (contract kpi-scope-spread) — downward spread. A ticket declared at a
# wide `down_time_scope` is attributable not only to its own stored
# location but to every descendant of it, symmetric with the existing
# upward roll-up in `_resolve_location`. Rank order narrow -> wide.
_SCOPE_RANK: dict[str, int] = {
    ProductionScope.WORK_STATION.value: 0,
    ProductionScope.PRODUCTION_LINE.value: 1,
    ProductionScope.UAP.value: 2,
    ProductionScope.PLANT.value: 3,
}
_KIND_RANK: dict[str, int] = {"station": 0, "line": 1, "uap": 2}


def _stored_id_rank(issue: dict[str, Any]) -> Optional[int]:
    """§9.4/W2 — the rank (`_KIND_RANK`) of `issue`'s own deepest STORED id
    (`workstation_id` > `production_line_id` > `uap_id`, most specific
    first), or `None` if it carries no location id at all. Used to tell a
    genuine upward ROLL-UP (`_resolve_location` deriving a value for a
    `kind` ABOVE this rank, e.g. a line ticket's own `uap` row — always
    deterministic, always trusted) from a plain IDENTITY read (`kind`
    exactly at this rank, e.g. reading `production_line_id` back for a
    `line`-kind query) — the two need different trust rules, see
    `_locations_for_ticket`."""
    if issue.get("workstation_id"):
        return _KIND_RANK["station"]
    if issue.get("production_line_id"):
        return _KIND_RANK["line"]
    if issue.get("uap_id"):
        return _KIND_RANK["uap"]
    return None


def _locations_for_ticket(
    issue: dict[str, Any], hierarchy: dict[str, Any], kind: str
) -> set[str]:
    """§2 — the ids of type `kind` that `issue` is attributable to.

    First tries `issue`'s own location at `kind`'s level, rolled UP via
    `_resolve_location` exactly as today (a station ticket's own `uap`/
    `line` row, a line ticket's own `uap` row, ...). Whenever that roll-up
    yields a concrete id, `_stored_id_rank` tells whether it's a genuine
    UPWARD roll-up (`kind` strictly ABOVE the ticket's own deepest stored
    id — e.g. a `line` ticket's own `uap` row: deterministic, always
    trusted, no ambiguity) or a plain IDENTITY read (`kind` sits exactly AT
    that deepest stored id's own level — e.g. reading `production_line_id`
    back for a `line`-kind query). A roll-up always wins outright — full
    stop, no spreading, whatever `down_time_scope` says (this is what keeps
    a ticket declared "plant" that nonetheless carries a specific
    `production_line_id` attributed to that one line's UAP, not sprayed
    across every UAP: the roll-up is the more specific, unambiguous fact).

    An IDENTITY read only wins when `kind` is at or above the ticket's own
    DECLARED `down_time_scope` level (`kind_rank >= scope_rank`, or the
    scope is absent/unrecognized). Below that (`kind_rank < scope_rank`),
    the stored id is CONTEXT, not a restriction, and is never consulted —
    `_ticket_weight`/`_weight_from_ids` already treat a scope's own id
    field as authoritative when present (`:689`) and only fall back to the
    most-specific id when it's missing, so a `uap`-scope ticket with no
    `uap_id` but a `production_line_id` must still spread across every line
    of the UAP that line resolves to (§9.4/W2's own scenario), not collapse
    onto that one line — this is what treating ANY concrete id as
    authoritative, identity or roll-up alike, would do, and is the anomaly
    the developer raised back after the first pass of this contract's
    revision 2.

    Once `own` is not trusted (either it's `None`, or it's an identity read
    below the declared scope), `down_time_scope` (read the same way
    `_ticket_weight` already does, `:689`) fills the row set, and only when
    it is strictly WIDER than `kind`: a `plant` ticket reaches every
    uap/line/station; a `uap` ticket (via its own RESOLVED uap, `uap_id`)
    reaches every line/station under that uap; a `production line` ticket
    (via its own RESOLVED line, `production_line_id`) reaches every station
    under that line. "Resolved" (§9.4/W2) means the ids already unpacked at
    the top of this function via `_resolve_location` — NOT the ticket's raw
    stored fields — so a `uap`-scope ticket carrying only a
    `production_line_id` (no `uap_id`) still spreads from the UAP that line
    rolls up to, instead of disappearing from every row.

    A legacy document with no `down_time_scope`, an unrecognized value, or
    a scope that is not strictly wider than `kind` gets today's behavior
    only: nothing at this level — never inferred or spread from absent
    ids ("on ne devine pas un scope large à partir d'ids absents", §2).

    §9.3/W4 — reconciliation (§7) beats the weight floor for a SPREAD
    ticket: a `kind`/id with zero descendant workstations is never included
    here when spreading (a `uap`/`line` with no workstations under it is
    dropped from the result). This does not affect a ticket declared
    (`own` above) exactly at that empty location — that row still exists,
    floored at 1 by `_row_weight`, just never populated via spread.
    """
    uap_id, line_id, station_id = _resolve_location(issue, hierarchy)
    scope = issue.get("down_time_scope")
    scope_rank = _SCOPE_RANK.get(scope) if isinstance(scope, str) else None
    kind_rank = _KIND_RANK[kind]
    stored_rank = _stored_id_rank(issue)

    own = {"uap": uap_id, "line": line_id, "station": station_id}[kind]
    if own is not None:
        is_roll_up = stored_rank is not None and kind_rank > stored_rank
        # Addendum §8's own worked example ("a `plant` ticket carrying a
        # `uap_id` stays attributed to that one UAP") is deliberately kept
        # as-is for `plant` specifically — `plant` has no "own id field" at
        # all (the §8 validator forbids one on every NEW document), so any
        # id found on a `plant`-scope ticket is legacy data Addendum §8
        # already ruled should restrict attribution, not spread. §9.4/W2's
        # narrower-than-declared-scope case is different: `uap`/`production
        # line` DO have a well-defined own id field, and when THAT field is
        # missing but a narrower one is present, `_ticket_weight`'s own
        # fallback (`:689`) already treats it as "scope's own id missing",
        # so `own` must not block the scope-driven spread below either.
        if (
            is_roll_up
            or scope_rank is None
            or kind_rank >= scope_rank
            or scope == ProductionScope.PLANT.value
        ):
            return {own}

    if scope_rank is None or scope_rank <= kind_rank:
        return set()

    if scope == ProductionScope.PLANT.value:
        if kind == "uap":
            return {
                u for u in hierarchy["uaps"] if hierarchy["uap_station_counts"].get(u, 0) > 0
            }
        if kind == "line":
            return {l for l in hierarchy["lines"] if hierarchy["stations_by_line"].get(l)}
        return set(hierarchy["stations"].keys())
    if scope == ProductionScope.UAP.value:
        uap_scope_id = uap_id  # resolved (§9.4/W2), not the raw `issue.get("uap_id")`
        if not uap_scope_id:
            return set()
        lines = hierarchy["lines_by_uap"].get(uap_scope_id, [])
        if kind == "line":
            return {
                line["id"] for line in lines if hierarchy["stations_by_line"].get(line["id"])
            }
        ids: set[str] = set()
        for line in lines:
            ids.update(s["id"] for s in hierarchy["stations_by_line"].get(line["id"], []))
        return ids
    if scope == ProductionScope.PRODUCTION_LINE.value:
        line_scope_id = line_id  # resolved (§9.4/W2), not the raw `issue.get("production_line_id")`
        if not line_scope_id:
            return set()
        return {s["id"] for s in hierarchy["stations_by_line"].get(line_scope_id, [])}
    return set()


def _row_weight(
    issue: dict[str, Any], hierarchy: dict[str, Any], kind: str, loc_id: str
) -> int:
    """§3 — the weight `issue` carries in the `kind`/`loc_id` breakdown row:
    the workstations it touches IN THAT ROW, floored at 1. Mirrors
    `_locations_for_ticket`'s own-location-first rule: when `issue` has a
    concrete rolled-up location at `kind`'s level (not spread into this
    row), this is exactly `_ticket_weight(issue, hierarchy)` — no existing
    number moves. Only a ticket spread into `loc_id` from a strictly wider
    `down_time_scope` (no id of its own at this level) gets that row's OWN
    share (never the whole ticket's weight, which would
    triple/quintuple-count a wide-scope ticket across the rows it spreads
    into).

    Worked example (§3): a plant with 3 UAPs — A=10 workstations, B=6, C=4
    (20 total) — logs one 30-minute plant-wide stop. The header KPI is
    `30 * 20 = 600` workstation-minutes. Weighing every row by the ticket's
    FULL weight (20) would give each of A/B/C `30 * 20 = 600`, summing to
    1800 — triple the header, and A/B/C would look equally hurt despite
    having different workstation counts. Weighing each row by its OWN share
    instead gives A: `30 * 10 = 300`, B: `30 * 6 = 180`, C: `30 * 4 = 120` —
    summing back to exactly 600, and preserving the A > B > C ranking.

    §9.4/W2 (revision 2): mirrors `_locations_for_ticket`'s own-trust rule
    exactly (`_stored_id_rank`) — a genuine upward roll-up (`kind` above the
    ticket's own deepest stored id) always wins; a plain identity read
    (`kind` AT that stored id's own level) only wins when `kind` is at or
    above the ticket's DECLARED `down_time_scope` level. Below that, the
    narrower id is context, not a restriction, and must not stop the
    ticket's OWN-share spread weight from applying to a sibling row
    `_locations_for_ticket` now reaches.

    Resource-archiving rule 4, spread branch (`kind == "line"`/`"uap"`):
    same floor-preserved-for-its-original-case-only rule as `_ticket_weight`
    — an EMPTY `stations_by_line`/`stations_by_uap` raw list (no workstation
    registered under this row at all) still floors to 1; a NON-EMPTY raw
    list is instead counted down to the stations still active at `issue`'s
    own `created_at`, which may legitimately total 0 (never floored) when
    every one of them was archived before this ticket."""
    uap_id, line_id, station_id = _resolve_location(issue, hierarchy)
    scope = issue.get("down_time_scope")
    scope_rank = _SCOPE_RANK.get(scope) if isinstance(scope, str) else None
    kind_rank = _KIND_RANK[kind]
    stored_rank = _stored_id_rank(issue)

    own = {"uap": uap_id, "line": line_id, "station": station_id}[kind]
    if own is not None:
        is_roll_up = stored_rank is not None and kind_rank > stored_rank
        # See `_locations_for_ticket`'s matching comment: `plant` is kept
        # special-cased (Addendum §8), every other scope's narrower-id case
        # is §9.4/W2's fallback-not-restriction rule.
        if (
            is_roll_up
            or scope_rank is None
            or kind_rank >= scope_rank
            or scope == ProductionScope.PLANT.value
        ):
            return _ticket_weight(issue, hierarchy)

    if scope_rank is None or scope_rank <= kind_rank:
        return _ticket_weight(issue, hierarchy)
    if kind == "station":
        return 1
    raw_stations = (
        hierarchy["stations_by_line"].get(loc_id, [])
        if kind == "line"
        else hierarchy["stations_by_uap"].get(loc_id, [])
    )
    if not raw_stations:
        return 1
    created_at = _parse_iso(issue.get("created_at"))
    return sum(1 for s in raw_stations if _active_at_ticket_date(s, created_at))


def _location_weight_fn(
    hierarchy: dict[str, Any], kind: str, loc_id: str
) -> Callable[[dict[str, Any]], int]:
    """Per-row `weight_of` closure for one `(kind, loc_id)` breakdown row —
    `_row_weight` memoized by ticket id, but the cache is scoped to THIS row
    only (never shared across rows/kinds). This is the fix for the
    `_weight_of_builder` trap (§5.1): that closure's cache is keyed by
    ticket id alone, so a spread ticket appearing in several rows would be
    served the first row's weight everywhere else. Here the row is baked
    into the closure itself, so the effective cache key is
    `(ticket_id, kind, loc_id)`."""
    cache: dict[str, int] = {}

    def weight_of(issue: dict[str, Any]) -> int:
        issue_id = issue.get("id")
        if issue_id is None:
            return _row_weight(issue, hierarchy, kind, loc_id)
        if issue_id not in cache:
            cache[issue_id] = _row_weight(issue, hierarchy, kind, loc_id)
        return cache[issue_id]

    return weight_of


def _row_type_weights(
    issue: dict[str, Any], hierarchy: dict[str, Any], kind: str, loc_id: str
) -> dict[str, int]:
    """§3.2 — the same own-vs-spread branching as `_row_weight`, split by
    workstation type instead of collapsed to a single count. Mirrors
    `_row_weight` exactly:

    - "own" row (this `(kind, loc_id)` IS where `issue`'s own/rolled-up
      location lives, per `_row_weight`'s own-trust rule) -> the full
      per-type breakdown of the ticket's own resolved stations
      (`_ticket_type_weights`) — always sums to `_row_weight`'s own-branch
      return value (`_ticket_weight(issue, hierarchy)`), since both are
      derived from the same `_ticket_stations` set, which for an "own" row
      already lives entirely inside that row's perimeter.
    - spread row (a wider-scope ticket landing in a row it doesn't own) ->
      that row's OWN type composition, tallied from the raw station
      documents (`stations_by_line`/`stations_by_uap`) and filtered down to
      the ones still active at `issue`'s own `created_at`
      (`_active_at_ticket_date`) -- this is `_row_weight`'s own "the row's
      own share, not the whole ticket" rule, applied per-type, AND mirrors
      `_row_weight`'s spread-branch archival filtering exactly (resource-
      archiving rule 4), so the three type shares of a spread row always sum
      back to `_row_weight`'s return value for that same row, archived or
      not. The precomputed static `type_counts_by_line`/`type_counts_by_uap`
      (unfiltered by archival, used elsewhere for perimeter-wide
      composition) is deliberately NOT reused here for that reason.

    Only ever called on a ticket already known to belong to this row (via
    `_group_tickets_by_location`/`_locations_for_ticket`), exactly like
    `_row_weight` -- so no explicit `own == loc_id` check is needed here
    either."""
    uap_id, line_id, station_id = _resolve_location(issue, hierarchy)
    scope = issue.get("down_time_scope")
    scope_rank = _SCOPE_RANK.get(scope) if isinstance(scope, str) else None
    kind_rank = _KIND_RANK[kind]
    stored_rank = _stored_id_rank(issue)

    own = {"uap": uap_id, "line": line_id, "station": station_id}[kind]
    if own is not None:
        is_roll_up = stored_rank is not None and kind_rank > stored_rank
        if (
            is_roll_up
            or scope_rank is None
            or kind_rank >= scope_rank
            or scope == ProductionScope.PLANT.value
        ):
            return _ticket_type_weights(issue, hierarchy)

    if scope_rank is None or scope_rank <= kind_rank:
        return _ticket_type_weights(issue, hierarchy)
    if kind == "station":
        # Never actually reached in practice — a `station`-kind row's slices
        # are always `None` (§3.3) and this function is only wired up for
        # `uap`/`line` rows. Kept for symmetry with `_row_weight`.
        counts = _empty_type_counts()
        counts[WorkstationType.STANDARD.value] = 1
        return counts
    raw_stations = (
        hierarchy["stations_by_line"].get(loc_id, [])
        if kind == "line"
        else hierarchy["stations_by_uap"].get(loc_id, [])
    )
    created_at = _parse_iso(issue.get("created_at"))
    counts = _empty_type_counts()
    for station in raw_stations:
        if _active_at_ticket_date(station, created_at):
            counts[_station_type(station)] += 1
    return counts


def _row_type_weight_fn_builder(
    hierarchy: dict[str, Any], kind: str, loc_id: str
) -> Callable[[dict[str, Any]], dict[str, int]]:
    """Per-row `type_weight_fn` closure — `_row_type_weights` memoized by
    ticket id, cache scoped to THIS `(kind, loc_id)` row only, mirroring
    `_location_weight_fn`'s own per-row cache scoping exactly (same trap it
    fixes: a ticket-id-only cache would serve one row's type split to every
    other row a spread ticket also appears in)."""
    cache: dict[str, dict[str, int]] = {}

    def type_weight_of(issue: dict[str, Any]) -> dict[str, int]:
        issue_id = issue.get("id")
        if issue_id is None:
            return _row_type_weights(issue, hierarchy, kind, loc_id)
        if issue_id not in cache:
            cache[issue_id] = _row_type_weights(issue, hierarchy, kind, loc_id)
        return cache[issue_id]

    return type_weight_of


def _row_perimeter_type_counts(
    hierarchy: dict[str, Any], kind: str, loc_id: str
) -> Optional[dict[str, int]]:
    """The `(kind, loc_id)` row's OWN perimeter type composition (§3.1) —
    `None` for a `station`-kind row (a workstation already has exactly one
    type, splitting its own row by type is meaningless, §3.3), which is what
    tells `_group_by_location` not to compute slices for it at all."""
    if kind == "uap":
        return hierarchy["type_counts_by_uap"].get(loc_id, _empty_type_counts())
    if kind == "line":
        return hierarchy["type_counts_by_line"].get(loc_id, _empty_type_counts())
    return None


def _has_orphan_child(hierarchy: dict[str, Any], kind: str) -> bool:
    """True when at least one entity of the level BELOW `kind` has no parent
    at `kind`'s level, and so cannot roll up into any real row of a `kind`
    breakdown: a production line with no `uap_id` for "uap", a workstation
    with no `production_line_id` for "line". Such an orphan is a group in
    its own right (it lands in the breakdown's `unassigned` row), so it
    counts alongside the real rows when deciding whether `kind` is a
    meaningful granularity.

    Always exactly ONE level down. `_unassigned_count` answers a different
    question -- how many WORKSTATIONS a `kind` breakdown cannot reach, at
    any depth -- which is right for sizing the `unassigned` row but wrong
    here: at the "uap" level it also counts line-less workstations, whose
    line is *undefined* rather than UAP-less, and one stray line-less
    station would then collapse an informative `line` breakdown down to a
    single UAP row plus `unassigned`."""
    if kind == "uap":
        return any(not uap_id for uap_id in hierarchy["line_to_uap"].values())
    # kind == "line"
    return any(
        not s.get("production_line_id") for s in hierarchy["stations"].values()
    )


def _pick_location_kind(hierarchy: dict[str, Any]) -> str:
    """UAPs when there's more than one distinguishable top-level group, else
    lines when more than one, else stations. At each level the real rows are
    counted alongside one extra group for the orphans of the level just
    below (`_has_orphan_child`) -- a UAP-less line for "uap", a line-less
    workstation for "line" -- since those cannot roll up into any real row
    and would otherwise be invisible.

    Resource-archiving rule 5: an ARCHIVED UAP/line is excluded from
    `uap_count`/`line_count` outright, regardless of tickets. An archived
    resource only ever becomes a `by_location` row through
    `_group_by_location`'s ticket-driven grouping (rows are built from where
    tickets land, never by iterating the hierarchy directly, so an archived
    resource with zero tickets in the queried period never becomes a row on
    its own already) -- so counting it here too would inflate the perceived
    number of "distinguishable" groups with one that structurally cannot
    contribute a row by itself, pushing the granularity decision up to a
    coarser `kind` than the breakdown will actually show."""
    uap_count = sum(1 for u in hierarchy["uaps"].values() if is_active(u))
    line_count = sum(1 for l in hierarchy["lines"].values() if is_active(l))
    if uap_count + (1 if _has_orphan_child(hierarchy, "uap") else 0) > 1:
        return "uap"
    if line_count + (1 if _has_orphan_child(hierarchy, "line") else 0) > 1:
        return "line"
    return "station"


# --------------------------------------------------------------------------
# 5. Breakdown builders.
# --------------------------------------------------------------------------


def _group_tickets_by_location(
    tickets: list[dict[str, Any]], hierarchy: dict[str, Any], kind: str
) -> dict[str, list[dict[str, Any]]]:
    """Buckets `tickets` by every `kind`-level location id each is
    attributable to (§2 — `_locations_for_ticket`), not just a single
    rolled-up id: a wide-scope ticket (e.g. `plant`) lands in EVERY row of
    this kind, each row's list carrying that same ticket instance."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for issue in tickets:
        for loc_id in _locations_for_ticket(issue, hierarchy, kind):
            groups[loc_id].append(issue)
    return groups


def _spreads_from_plant(issue: dict[str, Any], hierarchy: dict[str, Any], kind: str) -> bool:
    """§9.2/B2 — true when `issue` is a `plant`-scope ticket with no concrete
    own location at `kind`'s level, i.e. exactly the kind of ticket whose
    weight (`_ticket_weight`) already counts EVERY workstation in the plant,
    including ones `_locations_for_ticket` can place in no real row
    (workstations with no `production_line_id`, or under a line with no
    `uap_id`). Used only to populate the explicit `unassigned` row below —
    a legacy/unrecognized-scope ticket never matches this (§2: no spread)."""
    if issue.get("down_time_scope") != ProductionScope.PLANT.value:
        return False
    uap_id, line_id, station_id = _resolve_location(issue, hierarchy)
    own = {"uap": uap_id, "line": line_id, "station": station_id}[kind]
    return own is None


def _unassigned_count(hierarchy: dict[str, Any], kind: str) -> int:
    """§9.2/B2 — the number of workstations `kind`'s real rows structurally
    cannot reach: a `station` breakdown has no such gap (every real station
    is its own row regardless of its `production_line_id`). A `line`
    breakdown misses workstations with no `production_line_id` at all. A
    `uap` breakdown additionally misses workstations whose line itself has
    no `uap_id` (the line rolls up to nothing) — not just line-less
    workstations."""
    if kind == "station":
        return 0
    if kind == "line":
        return sum(
            1 for s in hierarchy["stations"].values() if not s.get("production_line_id")
        )
    # kind == "uap"
    count = 0
    for s in hierarchy["stations"].values():
        line_id = s.get("production_line_id")
        if not line_id or not hierarchy["line_to_uap"].get(line_id):
            count += 1
    return count


def _group_by_location(
    tickets: list[dict[str, Any]],
    hierarchy: dict[str, Any],
    kind: str,
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    count_tickets: list[dict[str, Any]],
) -> list[BreakdownRow]:
    """Tickets not attributable to `kind`'s level are excluded from the real
    rows below (never bucketed under a synthetic row there). `tickets`
    (downtime aggregation, current + carry-over per fix #1) and
    `count_tickets` (current-range only, for `count`/`mttr`) are grouped
    independently. Rows never carry a meaningful `mtbf_seconds` (fix #5 — no
    single planned-time denominator makes sense for one location/type
    slice).

    §2/§3 (contract kpi-scope-spread): a wide-scope ticket (e.g. `plant`)
    is bucketed into EVERY row of this `kind` (`_group_tickets_by_location`),
    each row weighted by its OWN share of the ticket (`_row_weight`, via a
    per-row `_location_weight_fn` closure — a request-wide `weight_of` is
    deliberately never reused here, to avoid a ticket-id-only cache serving
    one row's weight to every other row the same ticket appears in).

    §4 (explicit, not a bug): `count`/`mttr` are never weighted, so a
    spread ticket counts 1 in EACH row it lands in — three UAP rows at
    `count == 1` for a single plant-wide stop. A breakdown's `count`/`mttr`
    therefore do NOT reconcile against the header's (the header counts the
    ticket once).

    §9.2/B2: an explicit `id="unassigned"`/`label=""` row (this breakdown's
    `kind`) is appended, weighted by the FIXED count of workstations no real
    row can reach (`_unassigned_count`), for the plant-scope tickets that
    structurally include them (`_spreads_from_plant`) — emitted ONLY when
    that count is > 0 (never a zero row), and never drillable (this
    function never treats `"unassigned"` as a real hierarchy id anywhere
    else).

    Given both of the above, `sum(row.downtime_seconds for row in rows) ==
    header.downtime_seconds` holds whenever every ticket contributing to the
    header is either (a) attributable to a real `kind` row (own location or
    a spread that lands in a non-empty one, §9.3/W4) or (b) a plant-scope
    ticket captured by the `unassigned` row — i.e. NOT for a legacy/
    unrecognized-scope ticket with no id (§2 deliberately never spreads or
    counts it toward `unassigned` either, so its header weight has no
    matching row at all — an existing, unchanged gap this contract does not
    claim to close)."""
    names: dict[str, str]
    if kind == "uap":
        names = {i: d.get("name", "") for i, d in hierarchy["uaps"].items()}
    elif kind == "line":
        names = {i: d.get("name", "") for i, d in hierarchy["lines"].items()}
    else:
        names = {i: d.get("name", "") for i, d in hierarchy["stations"].items()}

    downtime_groups = _group_tickets_by_location(tickets, hierarchy, kind)
    count_groups = _group_tickets_by_location(count_tickets, hierarchy, kind)

    rows = []
    for loc_id in set(downtime_groups) | set(count_groups):
        # kpi-workstation-type-slices §4: only `uap`/`line` rows carry a
        # `bottleneck`/`critical` division — a `station` row is always
        # `None` (a workstation already has exactly one type, §3.3).
        perimeter_type_counts = _row_perimeter_type_counts(hierarchy, kind, loc_id)
        type_weight_fn = (
            _row_type_weight_fn_builder(hierarchy, kind, loc_id)
            if perimeter_type_counts is not None
            else None
        )
        rows.append(
            BreakdownRow(
                kind=kind,
                id=loc_id,
                label=names.get(loc_id, ""),
                kpis=_compute_kpis(
                    downtime_groups.get(loc_id, []),
                    period_start,
                    period_end,
                    now,
                    0.0,
                    count_tickets=count_groups.get(loc_id, []),
                    weight_of=_location_weight_fn(hierarchy, kind, loc_id),
                    type_weight_fn=type_weight_fn,
                    perimeter_type_counts=perimeter_type_counts,
                    hierarchy=hierarchy,
                ),
            )
        )

    unassigned_count = _unassigned_count(hierarchy, kind)
    if unassigned_count > 0:
        unassigned_tickets = [t for t in tickets if _spreads_from_plant(t, hierarchy, kind)]
        unassigned_count_tickets = [
            t for t in count_tickets if _spreads_from_plant(t, hierarchy, kind)
        ]
        if unassigned_tickets or unassigned_count_tickets:
            rows.append(
                BreakdownRow(
                    kind=kind,
                    id="unassigned",
                    label="",
                    kpis=_compute_kpis(
                        unassigned_tickets,
                        period_start,
                        period_end,
                        now,
                        0.0,
                        count_tickets=unassigned_count_tickets,
                        weight_of=lambda _issue, _n=unassigned_count: _n,
                        hierarchy=hierarchy,
                    ),
                )
            )

    rows.sort(key=lambda row: row.kpis.downtime_seconds, reverse=True)
    return rows


def _group_by_shift(
    current: list[dict[str, Any]],
    carry_overs: list[dict[str, Any]],
    settings: dict[str, Any],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None,
    type_weight_fn: Optional[Callable[[dict[str, Any]], dict[str, int]]] = None,
    perimeter_type_counts: Optional[dict[str, int]] = None,
    hierarchy: Optional[dict[str, Any]] = None,
) -> list[BreakdownRow]:
    """§5bis.5 — empty when the namespace runs a single shift; a shift with
    no configured clock window emits no row at all (fix #3/#5 companion: a
    row with a permanently `None` planned time isn't useful). Tickets
    without a stored `shift` are excluded (no "unassigned" bucket). Each
    shift's own planned time (its own window minus its break, counted up to
    now for the in-progress day per §5bis.4bis) feeds its MTBF; downtime aggregates current + carry-over tickets
    (fix #1), weighted per ticket (§5bis.1bis) — count/mttr stay on
    current-range only, unweighted.

    kpi-workstation-type-slices §4 — a `by_shift` row's perimeter is the
    whole namespace (a shift spans the whole plant), so `type_weight_fn`/
    `perimeter_type_counts` are simply the request-wide namespace ones,
    passed through unchanged for every shift row.

    `hierarchy`, forwarded to `_compute_kpis`, applies resource-archiving
    rule 2's open-ticket bound to each shift row's own downtime sum."""
    shift_number = settings.get("shift_number", 1)
    if shift_number <= 1:
        return []
    configured = dict(_configured_shifts(settings))
    all_tickets = current + carry_overs
    rows = []
    for i in range(1, shift_number + 1):
        sid = str(i)
        if sid not in configured:
            continue
        count_tickets = [issue for issue in current if str(issue.get("shift")) == sid]
        downtime_tickets = [issue for issue in all_tickets if str(issue.get("shift")) == sid]
        planned = _planned_seconds(settings, period_start, period_end, now, shift_filter=sid)
        kpis = _compute_kpis(
            downtime_tickets,
            period_start,
            period_end,
            now,
            planned,
            count_tickets=count_tickets,
            weight_of=weight_of,
            type_weight_fn=type_weight_fn,
            perimeter_type_counts=perimeter_type_counts,
            hierarchy=hierarchy,
        )
        rows.append(BreakdownRow(kind="shift", id=sid, label=sid, kpis=kpis))
    return rows


def _group_by_type(
    tickets: list[dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    count_tickets: list[dict[str, Any]],
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None,
    hierarchy: Optional[dict[str, Any]] = None,
) -> list[BreakdownRow]:
    def _group(ticket_list: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for issue in ticket_list:
            type_id = _type_id_for_ticket(issue)
            if type_id is not None:
                groups[type_id].append(issue)
        return groups

    downtime_groups = _group(tickets)
    count_groups = _group(count_tickets)
    rows = [
        BreakdownRow(
            kind="type",
            id=type_id,
            label=type_id,
            kpis=_compute_kpis(
                downtime_groups.get(type_id, []),
                period_start,
                period_end,
                now,
                0.0,
                count_tickets=count_groups.get(type_id, []),
                weight_of=weight_of,
                hierarchy=hierarchy,
            ),
        )
        for type_id in set(downtime_groups) | set(count_groups)
    ]
    rows.sort(key=lambda row: row.kpis.downtime_seconds, reverse=True)
    return rows


def _downtime_by_process(
    tickets: list[dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None,
    hierarchy: Optional[dict[str, Any]] = None,
) -> dict[str, float]:
    weight_fn = weight_of if weight_of is not None else _flat_weight
    totals: dict[str, float] = defaultdict(float)
    for issue in tickets:
        process = _process_for_ticket(issue)
        if process is not None:
            totals[process] += _ticket_downtime_seconds(
                issue, period_start, period_end, now, hierarchy
            ) * weight_fn(issue)
    return dict(totals)


def _pareto_by_process(
    tickets: list[dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None,
    hierarchy: Optional[dict[str, Any]] = None,
) -> list[ParetoRow]:
    """Share of total (weighted, §5bis.1bis) downtime per process, sorted
    desc, running cumulative. Empty list when total downtime is 0 (nothing
    to chart). `hierarchy`, forwarded to `_downtime_by_process`, applies
    resource-archiving rule 2's open-ticket bound."""
    totals = _downtime_by_process(tickets, period_start, period_end, now, weight_of, hierarchy)
    total = sum(totals.values())
    if total <= 0:
        return []
    rows = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    result = []
    cumulative = 0.0
    for process_id, seconds in rows:
        share = seconds / total
        cumulative = min(1.0, cumulative + share)
        result.append(
            ParetoRow(id=process_id, label=process_id, share=round(share, 4), cumulative=round(cumulative, 4))
        )
    return result


def _repair_by_process(tickets: list[dict[str, Any]]) -> list[Bar]:
    """Summed `resolved_at - created_at` of CLOSED tickets per process,
    sorted desc."""
    totals: dict[str, float] = defaultdict(float)
    for issue in tickets:
        if issue.get("status") != DownTimeStatus.CLOSED.value:
            continue
        process = _process_for_ticket(issue)
        if process is None:
            continue
        created_at = _parse_iso(issue.get("created_at"))
        resolved_at = _parse_iso(issue.get("resolved_at"))
        if created_at is None or resolved_at is None:
            continue
        totals[process] += max(0.0, (resolved_at - created_at).total_seconds())
    bars = [Bar(id=pid, label=pid, value=int(round(sec))) for pid, sec in totals.items()]
    bars.sort(key=lambda bar: bar.value, reverse=True)
    return bars


def _downtime_by_shift_bars(
    tickets: list[dict[str, Any]],
    settings: dict[str, Any],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None,
    hierarchy: Optional[dict[str, Any]] = None,
) -> list[Bar]:
    shift_number = settings.get("shift_number", 1)
    if shift_number <= 1:
        return []
    weight_fn = weight_of if weight_of is not None else _flat_weight
    totals: dict[str, float] = defaultdict(float)
    for issue in tickets:
        shift_value = issue.get("shift")
        if shift_value is None:
            continue
        totals[str(shift_value)] += _ticket_downtime_seconds(
            issue, period_start, period_end, now, hierarchy
        ) * weight_fn(issue)
    bars = [Bar(id=sid, label=sid, value=int(round(sec))) for sid, sec in totals.items()]
    bars.sort(key=lambda bar: bar.value, reverse=True)
    return bars


def _downtime_by_type_bars(
    tickets: list[dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None,
    hierarchy: Optional[dict[str, Any]] = None,
) -> list[Bar]:
    weight_fn = weight_of if weight_of is not None else _flat_weight
    totals: dict[str, float] = defaultdict(float)
    for issue in tickets:
        type_id = _type_id_for_ticket(issue)
        if type_id is not None:
            totals[type_id] += _ticket_downtime_seconds(
                issue, period_start, period_end, now, hierarchy
            ) * weight_fn(issue)
    bars = [Bar(id=tid, label=tid, value=int(round(sec))) for tid, sec in totals.items()]
    bars.sort(key=lambda bar: bar.value, reverse=True)
    return bars


def _agent_label(agent_id: str, users_by_id: dict[str, dict[str, Any]]) -> str:
    user = users_by_id.get(agent_id)
    if user:
        name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        if name:
            return name
    return agent_id


def _by_agent_bars(
    client: FirestoreClient, tickets: list[dict[str, Any]]
) -> tuple[list[Bar], list[Bar]]:
    """§5bis.6 — `(mttr_by_agent, count_by_agent)` over CLOSED tickets,
    attributed to `resolved_by`. Agent display names resolved from the Users
    collection, falling back to the raw id. `tickets` may include carry-over
    tickets (fix #1) — closed carry-overs resolved inside the window are
    genuine completions for the period and belong here."""
    durations: dict[str, list[float]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    for issue in tickets:
        if issue.get("status") != DownTimeStatus.CLOSED.value:
            continue
        agent_id = issue.get("resolved_by")
        if not agent_id:
            continue
        counts[agent_id] += 1
        created_at = _parse_iso(issue.get("created_at"))
        resolved_at = _parse_iso(issue.get("resolved_at"))
        if created_at is not None and resolved_at is not None:
            durations[agent_id].append(max(0.0, (resolved_at - created_at).total_seconds()))

    agent_ids = list(counts.keys())
    users_by_id = client.get_documents(USERS_COLLECTION, agent_ids) if agent_ids else {}

    mttr_bars = [
        Bar(
            id=agent_id,
            label=_agent_label(agent_id, users_by_id),
            value=int(round(sum(durs) / len(durs))) if durs else 0,
        )
        for agent_id, durs in durations.items()
    ]
    mttr_bars.sort(key=lambda bar: bar.value, reverse=True)

    count_bars = [
        Bar(id=agent_id, label=_agent_label(agent_id, users_by_id), value=count)
        for agent_id, count in counts.items()
    ]
    count_bars.sort(key=lambda bar: bar.value, reverse=True)

    return mttr_bars, count_bars


# --------------------------------------------------------------------------
# Drill-down path parsing.
# --------------------------------------------------------------------------

_VALID_PATH_KINDS = {"uap", "line", "station", "shift", "type", "process"}
_LOCATION_PATH_KINDS = {"uap", "line", "station"}


def _parse_drill_path(path: str) -> list[tuple[str, str]]:
    """Parses `kind:id` steps separated by `>`. Raises 422 on any malformed
    segment, unknown kind, or more than `MAX_PATH_STEPS` steps (fix #11)."""
    steps: list[tuple[str, str]] = []
    for raw in path.split(">"):
        segment = raw.strip()
        if not segment or ":" not in segment:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"path: malformed segment {segment!r} (expected 'kind:id').",
            )
        kind, _, seg_id = segment.partition(":")
        kind = kind.strip()
        seg_id = seg_id.strip()
        if kind not in _VALID_PATH_KINDS or not seg_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"path: unknown kind or missing id in {segment!r}.",
            )
        steps.append((kind, seg_id))
    if not steps:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="path: must not be empty."
        )
    if len(steps) > MAX_PATH_STEPS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"path: at most {MAX_PATH_STEPS} steps allowed.",
        )
    return steps


def _apply_path_step(
    tickets: list[dict[str, Any]], hierarchy: dict[str, Any], kind: str, seg_id: str
) -> list[dict[str, Any]]:
    if kind in ("uap", "line", "station"):
        # §1/§2 (contract kpi-scope-spread) — a location path step must keep
        # a wide-scope ticket that spreads down into `seg_id` (e.g. a
        # `plant` ticket drilled into via `uap:<id>`), same rule as
        # `_filter_by_scope`; otherwise a drill-down path silently loses the
        # very ticket its own children block would show.
        return [t for t in tickets if seg_id in _locations_for_ticket(t, hierarchy, kind)]
    if kind == "shift":
        return [t for t in tickets if str(t.get("shift")) == seg_id]
    if kind == "process":
        return [t for t in tickets if _process_for_ticket(t) == seg_id]
    if kind == "type":
        return [t for t in tickets if _type_id_for_ticket(t) == seg_id]
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"path: unknown kind {kind!r}."
    )


# --------------------------------------------------------------------------
# Shared setup.
# --------------------------------------------------------------------------


def _validate_date_range(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="to: must not be before from.",
        )


def _period_bounds(date_from: date, date_to: date, tz: Any) -> tuple[datetime, datetime]:
    return (
        datetime.combine(date_from, time.min, tzinfo=tz),
        datetime.combine(date_to, time.max, tzinfo=tz),
    )


# Statuses that make a ticket "still open" for carry-over purposes (b).
_OPEN_STATUSES = [
    DownTimeStatus.PENDING.value,
    DownTimeStatus.ONGOING.value,
    DownTimeStatus.RESOLVED.value,
]


def _fetch_tickets(
    client: FirestoreClient, namespace_id: str, period_start: datetime, period_end: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(current, carry_overs)` (fix #1):

    - `current` — (a) the unchanged `created_at` range query. The only
      source for `count`/`mttr`/count+mttr daily buckets.
    - `carry_overs` — tickets created BEFORE `period_start`, deduped by id,
      still relevant to this period's downtime-based aggregations:
      (b) any currently-open (non-closed) ticket created before the period,
      plus (c) a CLOSED ticket created before the period whose
      `resolved_at` falls inside it (resolved during the window — kept only
      when `created_at < period_start`, so it's never double-counted with
      (a)). `current + carry_overs` feeds every downtime-based aggregation;
      `_ticket_downtime_seconds`'s clamp restricts each ticket's
      contribution to the queried window regardless of when it started.
    """
    # The 3 queries below are mutually independent (each filters on a
    # different field/purpose) -- parallelized (see `_run_parallel`). Order
    # is preserved regardless of which future finishes first.
    #
    # Each carry-over query filters on ONE field only: mixing an equality/`in`
    # on `status` with a range on a date field would require a Firestore
    # composite index. The remaining condition is applied in Python, on the
    # narrower of the two sets: (b) starts from the open tickets (always a
    # small set), (c) from the tickets resolved since `period_start`.
    current, still_open, resolved_in_range = _run_parallel(
        [
            lambda: client.find_subdocuments(
                DOWN_TIME_COLLECTION,
                namespace_id,
                ISSUES_SUBCOLLECTION,
                params={
                    "created_at": [
                        (">=", period_start.isoformat()),
                        ("<=", period_end.isoformat()),
                    ]
                },
            ),
            lambda: client.find_subdocuments(
                DOWN_TIME_COLLECTION,
                namespace_id,
                ISSUES_SUBCOLLECTION,
                params={"status": [("in", _OPEN_STATUSES)]},
            ),
            lambda: client.find_subdocuments(
                DOWN_TIME_COLLECTION,
                namespace_id,
                ISSUES_SUBCOLLECTION,
                params={"resolved_at": [(">=", period_start.isoformat())]},
            ),
        ]
    )
    current_ids = {issue.get("id") for issue in current}

    open_before = [
        issue
        for issue in still_open
        if (created := _parse_iso(issue.get("created_at"))) is not None and created < period_start
    ]

    closed_carry_overs = [
        issue
        for issue in resolved_in_range
        if issue.get("status") == DownTimeStatus.CLOSED.value
        and (created := _parse_iso(issue.get("created_at"))) is not None
        and created < period_start
    ]

    carry_overs: dict[str, dict[str, Any]] = {}
    for issue in (*open_before, *closed_carry_overs):
        issue_id = issue.get("id")
        if issue_id and issue_id not in current_ids:
            carry_overs[issue_id] = issue

    return current, list(carry_overs.values())


def _namespace_context(
    client: FirestoreClient, namespace_id: str
) -> tuple[dict[str, Any], Any, dict[str, Any]]:
    """`(namespace_doc, tz, settings_doc)` — settings defaults to `{}` (24h/day
    — see `_planned_seconds_per_day`)."""
    # The namespace doc and the settings doc are independent reads (`tz` only
    # depends on the namespace doc, not on settings) -- parallelized (see
    # `_run_parallel`). Order is preserved regardless of which future
    # finishes first.
    namespace, settings = _run_parallel(
        [
            lambda: client.get_document(NAMESPACE_COLLECTION, namespace_id) or {},
            lambda: client.get_subdocument(
                NAMESPACE_SETTINGS_COLLECTION, namespace_id, SETTINGS_SUBCOLLECTION, namespace_id
            )
            or {},
        ]
    )
    tz = namespace_timezone(namespace_id, namespace)
    return namespace, tz, settings


# --------------------------------------------------------------------------
# 6. Public entry points.
# --------------------------------------------------------------------------


def get_dashboard(query: DashboardQueryIn, namespace_id: str) -> DashboardData:
    _validate_date_range(query.date_from, query.date_to)
    client = get_firestore_client()
    namespace, tz, settings = _namespace_context(client, namespace_id)
    period_start, period_end = _period_bounds(query.date_from, query.date_to, tz)
    now = datetime.now(tz)

    current, carry_overs = _fetch_tickets(client, namespace_id, period_start, period_end)
    all_tickets = current + carry_overs
    hierarchy = _location_hierarchy(client, namespace_id)
    weight_of = _weight_of_builder(hierarchy)
    # kpi-workstation-type-slices §4 — `overall`/`by_shift`'s own perimeter
    # is the whole namespace.
    namespace_type_weight_fn = _ticket_type_weight_fn_builder(hierarchy)
    namespace_type_counts = hierarchy["type_counts_namespace"]

    uap_count = len(hierarchy["uaps"])
    line_count = len(hierarchy["lines"])
    station_count = len(hierarchy["stations"])
    location_kind = _pick_location_kind(hierarchy)

    planned = _planned_seconds(settings, period_start, period_end, now)

    return DashboardData(
        namespace=NamespaceMeta(
            name=namespace.get("company_name") or "",
            shift_number=settings.get("shift_number", 1),
            shifts=[
                ShiftWindow(
                    id=sid,
                    start_time=shift.get("start_time", ""),
                    end_time=shift.get("end_time", ""),
                )
                for sid, shift in _configured_shifts(settings)
            ],
            uap_count=uap_count,
            line_count=line_count,
            station_count=station_count,
        ),
        overall=_compute_kpis(
            all_tickets,
            period_start,
            period_end,
            now,
            planned,
            count_tickets=current,
            weight_of=weight_of,
            type_weight_fn=namespace_type_weight_fn,
            perimeter_type_counts=namespace_type_counts,
            hierarchy=hierarchy,
        ),
        by_shift=_group_by_shift(
            current,
            carry_overs,
            settings,
            period_start,
            period_end,
            now,
            weight_of,
            type_weight_fn=namespace_type_weight_fn,
            perimeter_type_counts=namespace_type_counts,
            hierarchy=hierarchy,
        ),
        by_location=_group_by_location(
            all_tickets, hierarchy, location_kind, period_start, period_end, now, current
        ),
        pareto_by_process=_pareto_by_process(
            all_tickets, period_start, period_end, now, weight_of, hierarchy
        ),
        repair_by_process=_repair_by_process(current),
        by_type=_group_by_type(
            all_tickets, period_start, period_end, now, current, weight_of, hierarchy
        ),
    )


def get_drilldown(query: DrilldownQueryIn, namespace_id: str) -> DrilldownData:
    _validate_date_range(query.date_from, query.date_to)
    client = get_firestore_client()
    _namespace, tz, settings = _namespace_context(client, namespace_id)
    period_start, period_end = _period_bounds(query.date_from, query.date_to, tz)
    now = datetime.now(tz)

    current, carry_overs = _fetch_tickets(client, namespace_id, period_start, period_end)
    hierarchy = _location_hierarchy(client, namespace_id)

    steps = _parse_drill_path(query.path)

    dims_fixed: set[str] = set()
    shift_in_path: Optional[str] = None
    type_in_path: Optional[str] = None
    process_in_path: Optional[str] = None
    # Fix #4: the deepest LOCATION step anywhere in the path (not
    # necessarily the last step) is what `children` derives from.
    last_location_kind: Optional[str] = None
    last_location_id: Optional[str] = None
    for kind, seg_id in steps:
        current = _apply_path_step(current, hierarchy, kind, seg_id)
        carry_overs = _apply_path_step(carry_overs, hierarchy, kind, seg_id)
        dims_fixed.add(kind)
        if kind == "shift":
            shift_in_path = seg_id
        if kind == "process":
            process_in_path = seg_id
        if kind == "type":
            type_in_path = seg_id
        if kind in _LOCATION_PATH_KINDS:
            last_location_kind = kind
            last_location_id = seg_id

    # §9.1/B1 (contract kpi-scope-spread, revision 2): once the path fixes a
    # location, the request-wide weight must be that location's OWN share
    # (`_location_weight_fn`, exactly what `get_daily` already does for its
    # `scope_kind`/`scope_id` filter), not the whole-plant `weight_of` —
    # otherwise the header (and every aggregation below that reuses it)
    # shows the entire plant's weight for a UAP/line/station drill-down and
    # doesn't reconcile with its own `children` block. The location step(s)
    # above are applied to `current`/`carry_overs` BEFORE this point, so
    # every ticket reaching the aggregations below is already confined to
    # this location's subtree — the substitution is safe. `_weight_of_builder`
    # is kept only for a path with NO location step at all.
    weight_of = (
        _location_weight_fn(hierarchy, last_location_kind, last_location_id)
        if last_location_kind is not None
        else _weight_of_builder(hierarchy)
    )

    # kpi-workstation-type-slices §4/§9.3 — one populate rule for `shift`
    # AND location: populated with the path's deepest LOCATION perimeter
    # (`uap`/`line`; `station` is always `None`, §3.3), or — when no
    # location step exists anywhere in the path — with the namespace
    # perimeter whenever a `shift` step exists ANYWHERE in the path (not
    # only as the last step). No location and no shift -> not applicable.
    if last_location_kind in ("uap", "line"):
        slice_perimeter_type_counts: Optional[dict[str, int]] = _row_perimeter_type_counts(
            hierarchy, last_location_kind, last_location_id
        )
        slice_type_weight_fn: Optional[Callable[[dict[str, Any]], dict[str, int]]] = (
            _row_type_weight_fn_builder(hierarchy, last_location_kind, last_location_id)
        )
    elif last_location_kind is None and shift_in_path is not None:
        slice_perimeter_type_counts = hierarchy["type_counts_namespace"]
        slice_type_weight_fn = _ticket_type_weight_fn_builder(hierarchy)
    else:
        slice_perimeter_type_counts = None
        slice_type_weight_fn = None

    if query.process:
        current = [t for t in current if _process_for_ticket(t) == query.process]
        carry_overs = [t for t in carry_overs if _process_for_ticket(t) == query.process]
        dims_fixed.add("process")
    if query.shift:
        current = [t for t in current if str(t.get("shift")) == query.shift]
        carry_overs = [t for t in carry_overs if str(t.get("shift")) == query.shift]
        dims_fixed.add("shift")
    if type_in_path:
        # Client decision (revises review fix W3): a downtime TYPE is now
        # analyzed by WHO intervenes on it, not by process — a type slice
        # structurally spans several processes (§5bis.7 reads process off
        # each ticket, never infers it from the type), which is exactly why
        # a per-process breakdown is not a meaningful lens for a type: the
        # client wants `mttr_by_agent`/`count_by_agent` instead. Fixing
        # `process` here is what suppresses `pareto_by_process` /
        # `repair_by_process` below (`"process" not in dims_fixed`); a plain
        # `process` query param (no `type` step) keeps its current, separate
        # behavior untouched. `children` are unaffected — a type still
        # decorticates by places, never by types.
        dims_fixed.add("process")

    all_tickets = current + carry_overs

    shift_filter = query.shift or shift_in_path
    planned = _planned_seconds(settings, period_start, period_end, now, shift_filter=shift_filter)
    kpis = _compute_kpis(
        all_tickets,
        period_start,
        period_end,
        now,
        planned,
        count_tickets=current,
        weight_of=weight_of,
        type_weight_fn=slice_type_weight_fn,
        perimeter_type_counts=slice_perimeter_type_counts,
        hierarchy=hierarchy,
    )

    last_kind, _last_id = steps[-1]
    children: Optional[list[BreakdownRow]] = None
    children_hint_key: Optional[str] = None

    if last_location_kind == "uap":
        child_lines = hierarchy["lines_by_uap"].get(last_location_id, [])
        if child_lines:
            children = [
                BreakdownRow(
                    kind="line",
                    id=line["id"],
                    label=line.get("name", ""),
                    kpis=_compute_kpis(
                        [
                            t
                            for t in all_tickets
                            if line["id"] in _locations_for_ticket(t, hierarchy, "line")
                        ],
                        period_start,
                        period_end,
                        now,
                        0.0,
                        count_tickets=[
                            t
                            for t in current
                            if line["id"] in _locations_for_ticket(t, hierarchy, "line")
                        ],
                        weight_of=_location_weight_fn(hierarchy, "line", line["id"]),
                        hierarchy=hierarchy,
                    ),
                )
                for line in child_lines
            ]
            children_hint_key = "dashboard.drill.linesHint"
        else:
            # No production lines under this UAP — per the schema a
            # workstation only attaches via a `production_line_id`, so there
            # is structurally no direct UAP -> workstation edge. The hint key
            # + empty list still let the frontend render the "no lines"
            # state; flagged in the hand-off report.
            children = []
            children_hint_key = "dashboard.drill.noLinesHint"
    elif last_location_kind == "line":
        child_stations = hierarchy["stations_by_line"].get(last_location_id, [])
        children = [
            BreakdownRow(
                kind="station",
                id=station["id"],
                label=station.get("name", ""),
                kpis=_compute_kpis(
                    [
                        t
                        for t in all_tickets
                        if station["id"] in _locations_for_ticket(t, hierarchy, "station")
                    ],
                    period_start,
                    period_end,
                    now,
                    0.0,
                    count_tickets=[
                        t
                        for t in current
                        if station["id"] in _locations_for_ticket(t, hierarchy, "station")
                    ],
                    weight_of=_location_weight_fn(hierarchy, "station", station["id"]),
                    hierarchy=hierarchy,
                ),
            )
            for station in child_stations
        ]
        children_hint_key = "dashboard.drill.stationsHint"
    elif last_location_kind == "station":
        children = None  # leaf.
    elif last_kind in ("shift", "type", "process"):
        # No location step anywhere in the path — fall back to the
        # dashboard's plant-wide top location level.
        top_kind = _pick_location_kind(hierarchy)
        children = _group_by_location(
            all_tickets, hierarchy, top_kind, period_start, period_end, now, current
        )
        children_hint_key = "dashboard.drill.locationsHint"

    pareto = repair = None
    if "process" not in dims_fixed:
        pareto = _pareto_by_process(
            all_tickets, period_start, period_end, now, weight_of, hierarchy
        )
        repair = _repair_by_process(current)

    downtime_by_shift = None
    if "shift" not in dims_fixed:
        downtime_by_shift = _downtime_by_shift_bars(
            all_tickets, settings, period_start, period_end, now, weight_of, hierarchy
        )

    # `type` is only ever fixed by being a path step itself (there is no
    # `type` query param) — a fixed `process` still allows viewing its types.
    downtime_by_type = None
    if "type" not in {kind for kind, _ in steps}:
        downtime_by_type = _downtime_by_type_bars(
            all_tickets, period_start, period_end, now, weight_of, hierarchy
        )

    # Fix #13 / client decision above: a `type` step counts as "process
    # effectively fixed" too (it now fixes `process` in `dims_fixed`), so the
    # by-agent sections are computed for a type slice even though there's no
    # single "effective process" value to name for OTHERS/Setup-Changeover
    # (the type's own ticket set already carries whatever process each
    # ticket belongs to, and `_by_agent_bars` doesn't need one — it groups by
    # `resolved_by`, not by process).
    process_effectively_fixed = bool(query.process or process_in_path or type_in_path)
    mttr_by_agent = count_by_agent = None
    if process_effectively_fixed:
        mttr_by_agent, count_by_agent = _by_agent_bars(client, current)

    return DrilldownData(
        kpis=kpis,
        children=children,
        children_hint_key=children_hint_key,
        pareto_by_process=pareto,
        repair_by_process=repair,
        downtime_by_shift=downtime_by_shift,
        downtime_by_type=downtime_by_type,
        mttr_by_agent=mttr_by_agent,
        count_by_agent=count_by_agent,
    )


def _filter_by_scope(
    tickets: list[dict[str, Any]], hierarchy: dict[str, Any], scope_kind: str, scope_id: str
) -> list[dict[str, Any]]:
    """§5.1/§1 — a ticket is retained for `(scope_kind, scope_id)` when
    `scope_id` is one of the ids `_locations_for_ticket` attributes it to at
    that level (§2's downward spread), so a `plant`-scope ticket is no
    longer dropped from every drill-down/daily scope filter — the same rule
    `_group_tickets_by_location` uses for the dashboard breakdown, which is
    what keeps the two views reconciled for the same location (§1)."""
    if scope_kind in ("uap", "line", "station"):
        return [t for t in tickets if scope_id in _locations_for_ticket(t, hierarchy, scope_kind)]
    return tickets


def _daily_metric_value(
    metric: str,
    day_tickets: list[dict[str, Any]],
    day_start: datetime,
    day_end: datetime,
    now: datetime,
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None,
    hierarchy: Optional[dict[str, Any]] = None,
) -> float:
    """`metric`'s value for a single day.

    `count`/`mttr`: `day_tickets` is that day's `created_at`-bucketed,
    current-range-only tickets (unchanged) and `day_start`/`day_end` are
    unused.

    `duration`: `day_tickets` is instead the SAME full set for every day of
    the period (`current + carry_overs`, no per-day bucketing) — each
    ticket's downtime is clamped to `[day_start, day_end]` by
    `_ticket_downtime_seconds`, which naturally floors a ticket that doesn't
    touch this day to 0, so a multi-day ticket contributes its own slice to
    every day it overlaps instead of a single lump sum on its creation day.
    Weighted per workstation affected (§5bis.1bis), same as every other
    downtime aggregation in this module.
    """
    if metric == "count":
        return float(len(day_tickets))
    if metric == "mttr":
        # A day with no CLOSED ticket has no MTTR (`None`); the daily series
        # reports it as 0, which the web chart reads as "no repair that day".
        mttr = _mttr_seconds(day_tickets)
        return mttr if mttr is not None else 0.0
    weight_fn = weight_of if weight_of is not None else _flat_weight
    return sum(
        _ticket_downtime_seconds(issue, day_start, day_end, now, hierarchy) * weight_fn(issue)
        for issue in day_tickets
    )


def get_daily(query: DailyQueryIn, namespace_id: str) -> DailyPointsOut:
    _validate_date_range(query.date_from, query.date_to)
    if query.scope_kind != "plant" and not query.scope_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="scope_id: required unless scope_kind is 'plant'.",
        )

    client = get_firestore_client()
    _namespace, tz, _settings = _namespace_context(client, namespace_id)
    period_start, period_end = _period_bounds(query.date_from, query.date_to, tz)
    now = datetime.now(tz)

    current, carry_overs = _fetch_tickets(client, namespace_id, period_start, period_end)

    # The hierarchy (3 full-collection reads) is only needed for scope
    # filtering (any `scope_kind` other than plant) or to weight `duration`
    # by workstations affected (§5bis.1bis) — skip it for plant-scoped
    # `count`/`mttr` requests, which use neither (review fix W5).
    needs_hierarchy = query.scope_kind != "plant" or query.metric == "duration"
    hierarchy = _location_hierarchy(client, namespace_id) if needs_hierarchy else None
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None
    if query.scope_kind != "plant":
        assert hierarchy is not None  # `needs_hierarchy` guarantees this
        current = _filter_by_scope(current, hierarchy, query.scope_kind, query.scope_id or "")
        carry_overs = _filter_by_scope(
            carry_overs, hierarchy, query.scope_kind, query.scope_id or ""
        )
        # §1/§3 (contract kpi-scope-spread): once filtered to a scope, a
        # spread ticket's `duration` contribution here must be its OWN share
        # of THAT scope row (`_location_weight_fn`), not its whole-ticket
        # weight (`_weight_of_builder`) — otherwise this drill-down/daily
        # total stops matching the dashboard's `by_location` row for the
        # same location (the exact coherence this contract exists for).
        weight_of = _location_weight_fn(hierarchy, query.scope_kind, query.scope_id or "")
    elif hierarchy is not None:
        weight_of = _weight_of_builder(hierarchy)
    if query.process:
        current = [t for t in current if _process_for_ticket(t) == query.process]
        carry_overs = [t for t in carry_overs if _process_for_ticket(t) == query.process]
    if query.shift:
        current = [t for t in current if str(t.get("shift")) == query.shift]
        carry_overs = [t for t in carry_overs if str(t.get("shift")) == query.shift]

    # `count`/`mttr` bucket only current-range tickets, by their own
    # `created_at` day (fix #1) — unchanged.
    buckets: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for issue in current:
        created_at = _parse_iso(issue.get("created_at"))
        if created_at is None:
            continue
        buckets[created_at.astimezone(tz).date()].append(issue)

    # `duration` instead considers the SAME ticket set (current + carry_overs)
    # for every day of the period — no bucketing by creation day, no special
    # -casing of the first day — and lets `_ticket_downtime_seconds`'s own
    # clamp restrict each ticket's contribution to that one day
    # (`_daily_metric_value`'s docstring). This is what turns a multi-day
    # downtime into a plateau across the days it actually spans instead of a
    # single spike on its creation day, and stops a carry-over ticket from
    # dumping its whole clamped duration onto the window's first day.
    duration_tickets = current + carry_overs

    points: list[DailyPoint] = []
    day = query.date_from
    while day <= query.date_to:
        if query.metric == "duration":
            day_start, day_end = _period_bounds(day, day, tz)
            day_tickets = duration_tickets
        else:
            day_start, day_end = period_start, period_end
            day_tickets = buckets.get(day, [])
        value = _daily_metric_value(
            query.metric, day_tickets, day_start, day_end, now, weight_of, hierarchy
        )
        points.append(DailyPoint(date=day.isoformat(), value=int(round(value))))
        day += timedelta(days=1)

    return DailyPointsOut(points=points)
