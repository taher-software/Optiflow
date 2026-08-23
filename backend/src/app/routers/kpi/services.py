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
)

from src.app.routers.kpi.modelsIn import (
    MAX_PATH_STEPS,
    DailyQueryIn,
    DashboardQueryIn,
    DrilldownQueryIn,
)
from src.app.routers.kpi.modelsOut import (
    Bar,
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


def _ticket_downtime_seconds(
    issue: dict[str, Any], period_start: datetime, period_end: datetime, now: datetime
) -> float:
    """A single ticket's downtime, clamped to the queried period (§5bis.1):
    closed -> `created_at -> resolved_at`; not closed -> `created_at -> now`;
    effective window = `[max(created_at, period_start), min(natural_end,
    min(period_end, now))]`, floored at 0. This clamp is what makes a
    carry-over ticket (created before `period_start`) contribute only its
    in-window slice once it's included in a downtime aggregation (fix #1)."""
    created_at = _parse_iso(issue.get("created_at"))
    if created_at is None:
        return 0.0
    if issue.get("status") == DownTimeStatus.CLOSED.value:
        natural_end = _parse_iso(issue.get("resolved_at")) or created_at
    else:
        natural_end = now

    period_upper = min(period_end, now)
    effective_end = min(natural_end, period_upper)
    effective_start = max(created_at, period_start)
    return max(0.0, (effective_end - effective_start).total_seconds())


def _mttr_seconds(tickets: list[dict[str, Any]]) -> float:
    """§5bis.2 — mean `created_at -> resolved_at` over CLOSED tickets only
    (0 when there are none)."""
    durations: list[float] = []
    for issue in tickets:
        if issue.get("status") != DownTimeStatus.CLOSED.value:
            continue
        created_at = _parse_iso(issue.get("created_at"))
        resolved_at = _parse_iso(issue.get("resolved_at"))
        if created_at is None or resolved_at is None:
            continue
        durations.append(max(0.0, (resolved_at - created_at).total_seconds()))
    return sum(durations) / len(durations) if durations else 0.0


def _compute_kpis(
    tickets: list[dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    planned_seconds: float,
    count_tickets: Optional[list[dict[str, Any]]] = None,
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None,
) -> Kpis:
    """The 4 headline KPIs for a slice (§5bis.3/4/empty-slice rule;
    availability removed in revision 2).

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
    """
    count_source = tickets if count_tickets is None else count_tickets
    weight_fn = weight_of if weight_of is not None else _flat_weight
    downtime = sum(
        _ticket_downtime_seconds(issue, period_start, period_end, now) * weight_fn(issue)
        for issue in tickets
    )
    count = len(count_source)
    mttr = _mttr_seconds(count_source)
    if planned_seconds <= 0:
        mtbf: Optional[float] = None
    else:
        mtbf = planned_seconds if count == 0 else planned_seconds / count
    return Kpis(
        downtime_seconds=int(round(downtime)),
        count=count,
        mttr_seconds=int(round(mttr)),
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


def _break_seconds(shift: dict[str, Any]) -> float:
    """The shift's break duration in seconds (revision 3, §5bis.4bis), read
    from `break_start_time`/`break_end_time`. `0.0` when the shift has no
    break (either field absent/`None` — includes legacy documents with a
    residual `break_minutes`, which is ignored) or when the pair fails
    `break_minutes_in_window`'s validation (unparsable clock time, or a
    corrupted/out-of-window pair on a stored document that predates
    request-time validation): same tolerant-degrade philosophy as fix #9 —
    logged, the break is ignored rather than failing the whole request."""
    break_start = shift.get("break_start_time")
    break_end = shift.get("break_end_time")
    if not break_start or not break_end:
        return 0.0
    try:
        return float(
            break_minutes_in_window(
                shift.get("start_time", ""), shift.get("end_time", ""), break_start, break_end
            )
            * 60
        )
    except ValueError:
        logger.warning(
            "kpi: unparsable/invalid shift break %r/%r, ignoring break.",
            break_start,
            break_end,
        )
        return 0.0


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


def _elapsed_shift_seconds(shift: dict[str, Any], now_local: datetime) -> float:
    """Seconds of `shift`'s clock window elapsed by `now_local`'s
    time-of-day (namespace-local), clamped to `[0, full window length]`.
    Midnight-wrap aware. 0 when the window doesn't parse."""
    start = _parse_hhmm(shift.get("start_time", ""))
    end = _parse_hhmm(shift.get("end_time", ""))
    if start is None or end is None:
        return 0.0
    start_sec, end_sec = start * 60.0, end * 60.0
    now_sec = _seconds_of_day(now_local)
    if end_sec > start_sec:
        return min(max(now_sec - start_sec, 0.0), end_sec - start_sec)
    # Midnight-wrap window: [start, 24h) followed by [0, end).
    day_sec = 24 * 3600.0
    if now_sec >= start_sec:
        return now_sec - start_sec
    if now_sec <= end_sec:
        return (day_sec - start_sec) + now_sec
    return 0.0


def _shift_seconds_prorated(shift: dict[str, Any], now_local: datetime) -> float:
    """`shift`'s planned seconds (its window, net of its break — revision 3,
    §5bis.4bis, see `_shift_window_seconds`), prorated by the elapsed
    fraction of the shift's own **raw clock window** as of `now_local` (fix
    #2). The fraction denominator is deliberately the full window, not the
    break-adjusted one: a linear approximation of "how far into today's
    shift are we", not a break-aware simulation of exactly when the break
    falls. 0 when the window doesn't parse or has zero length."""
    start = _parse_hhmm(shift.get("start_time", ""))
    end = _parse_hhmm(shift.get("end_time", ""))
    if start is None or end is None:
        return 0.0
    window_minutes = (end - start) if end > start else (24 * 60 - start) + end
    if window_minutes <= 0:
        return 0.0
    elapsed = _elapsed_shift_seconds(shift, now_local)
    fraction = min(elapsed / (window_minutes * 60.0), 1.0)
    return fraction * (_shift_window_seconds(shift) or 0.0)


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
    the still-in-progress final day is prorated by the elapsed fraction of
    each configured shift's clock window (namespace-local) instead of
    counting it in full. 0 when the effective window is empty or there's no
    positive planned time at all."""
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
        last_day_planned = sum(_shift_seconds_prorated(shift, effective_end) for _, shift in shifts)

    return per_day * full_days + last_day_planned


# --------------------------------------------------------------------------
# 4. Location hierarchy + ticket -> location resolution.
# --------------------------------------------------------------------------


def _location_hierarchy(client: FirestoreClient, namespace_id: str) -> dict[str, Any]:
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

    return {
        "uaps": {u["id"]: u for u in uaps},
        "lines": {l["id"]: l for l in lines},
        "stations": {s["id"]: s for s in stations},
        "lines_by_uap": dict(lines_by_uap),
        "stations_by_line": dict(stations_by_line),
        "line_to_uap": {l["id"]: l.get("uap_id") for l in lines},
        "station_to_line": {s["id"]: s.get("production_line_id") for s in stations},
    }


def _weight_from_ids(issue: dict[str, Any], hierarchy: dict[str, Any]) -> int:
    """Legacy fallback: infers a weight from the most specific of the
    ticket's own stored `workstation_id` / `production_line_id` / `uap_id`
    (none of the three -> plant-wide); floored at 1 so a line/UAP with no
    workstations referenced under it still counts as 1, never 0. Used by
    `_ticket_weight` only when `down_time_scope` is absent/unrecognized, or
    names a level whose id the ticket doesn't actually carry."""
    if issue.get("workstation_id"):
        return 1
    line_id = issue.get("production_line_id")
    if line_id:
        return max(1, len(hierarchy["stations_by_line"].get(line_id, [])))
    uap_id = issue.get("uap_id")
    if uap_id:
        lines = hierarchy["lines_by_uap"].get(uap_id, [])
        total = sum(len(hierarchy["stations_by_line"].get(line["id"], [])) for line in lines)
        return max(1, total)
    return max(1, len(hierarchy["stations"]))


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
    scope whose own id field is missing from the ticket. Floored at 1 in
    every branch."""
    scope = issue.get("down_time_scope")
    if scope == ProductionScope.WORK_STATION.value:
        if issue.get("workstation_id"):
            return 1
        return _weight_from_ids(issue, hierarchy)
    if scope == ProductionScope.PRODUCTION_LINE.value:
        line_id = issue.get("production_line_id")
        if line_id:
            return max(1, len(hierarchy["stations_by_line"].get(line_id, [])))
        return _weight_from_ids(issue, hierarchy)
    if scope == ProductionScope.UAP.value:
        uap_id = issue.get("uap_id")
        if uap_id:
            lines = hierarchy["lines_by_uap"].get(uap_id, [])
            total = sum(len(hierarchy["stations_by_line"].get(line["id"], [])) for line in lines)
            return max(1, total)
        return _weight_from_ids(issue, hierarchy)
    if scope == ProductionScope.PLANT.value:
        return max(1, len(hierarchy["stations"]))
    # Absent/unrecognized `down_time_scope` (legacy document) -> infer.
    return _weight_from_ids(issue, hierarchy)


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


def _pick_location_kind(uap_count: int, line_count: int, station_count: int) -> str:
    """§3 — UAPs when there's more than one, else lines when more than one,
    else stations."""
    if uap_count > 1:
        return "uap"
    if line_count > 1:
        return "line"
    return "station"


# --------------------------------------------------------------------------
# 5. Breakdown builders.
# --------------------------------------------------------------------------


def _group_tickets_by_location(
    tickets: list[dict[str, Any]], hierarchy: dict[str, Any], kind: str
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for issue in tickets:
        uap_id, line_id, station_id = _resolve_location(issue, hierarchy)
        loc_id = {"uap": uap_id, "line": line_id, "station": station_id}[kind]
        if loc_id:
            groups[loc_id].append(issue)
    return groups


def _group_by_location(
    tickets: list[dict[str, Any]],
    hierarchy: dict[str, Any],
    kind: str,
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    count_tickets: list[dict[str, Any]],
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None,
) -> list[BreakdownRow]:
    """Tickets not attributable to `kind`'s level are excluded (never bucketed
    under a synthetic "unassigned" row). `tickets` (downtime aggregation,
    current + carry-over per fix #1) and `count_tickets` (current-range only,
    for `count`/`mttr`) are grouped independently. Rows never carry a
    meaningful `mtbf_seconds` (fix #5 — no single planned-time denominator
    makes sense for one location/type slice)."""
    names: dict[str, str]
    if kind == "uap":
        names = {i: d.get("name", "") for i, d in hierarchy["uaps"].items()}
    elif kind == "line":
        names = {i: d.get("name", "") for i, d in hierarchy["lines"].items()}
    else:
        names = {i: d.get("name", "") for i, d in hierarchy["stations"].items()}

    downtime_groups = _group_tickets_by_location(tickets, hierarchy, kind)
    count_groups = _group_tickets_by_location(count_tickets, hierarchy, kind)

    rows = [
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
                weight_of=weight_of,
            ),
        )
        for loc_id in set(downtime_groups) | set(count_groups)
    ]
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
) -> list[BreakdownRow]:
    """§5bis.5 — empty when the namespace runs a single shift; a shift with
    no configured clock window emits no row at all (fix #3/#5 companion: a
    row with a permanently `None` planned time isn't useful). Tickets
    without a stored `shift` are excluded (no "unassigned" bucket). Each
    shift's own planned time (its own window, carried-to-now/prorated per
    fix #2) feeds its MTBF; downtime aggregates current + carry-over tickets
    (fix #1), weighted per ticket (§5bis.1bis) — count/mttr stay on
    current-range only, unweighted."""
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
) -> dict[str, float]:
    weight_fn = weight_of if weight_of is not None else _flat_weight
    totals: dict[str, float] = defaultdict(float)
    for issue in tickets:
        process = _process_for_ticket(issue)
        if process is not None:
            totals[process] += _ticket_downtime_seconds(
                issue, period_start, period_end, now
            ) * weight_fn(issue)
    return dict(totals)


def _pareto_by_process(
    tickets: list[dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None,
) -> list[ParetoRow]:
    """Share of total (weighted, §5bis.1bis) downtime per process, sorted
    desc, running cumulative. Empty list when total downtime is 0 (nothing
    to chart)."""
    totals = _downtime_by_process(tickets, period_start, period_end, now, weight_of)
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
            issue, period_start, period_end, now
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
) -> list[Bar]:
    weight_fn = weight_of if weight_of is not None else _flat_weight
    totals: dict[str, float] = defaultdict(float)
    for issue in tickets:
        type_id = _type_id_for_ticket(issue)
        if type_id is not None:
            totals[type_id] += _ticket_downtime_seconds(
                issue, period_start, period_end, now
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
    if kind == "uap":
        return [t for t in tickets if _resolve_location(t, hierarchy)[0] == seg_id]
    if kind == "line":
        return [t for t in tickets if _resolve_location(t, hierarchy)[1] == seg_id]
    if kind == "station":
        return [t for t in tickets if t.get("workstation_id") == seg_id]
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

    uap_count = len(hierarchy["uaps"])
    line_count = len(hierarchy["lines"])
    station_count = len(hierarchy["stations"])
    location_kind = _pick_location_kind(uap_count, line_count, station_count)

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
        ),
        by_shift=_group_by_shift(
            current, carry_overs, settings, period_start, period_end, now, weight_of
        ),
        by_location=_group_by_location(
            all_tickets, hierarchy, location_kind, period_start, period_end, now, current, weight_of
        ),
        pareto_by_process=_pareto_by_process(all_tickets, period_start, period_end, now, weight_of),
        repair_by_process=_repair_by_process(current),
        by_type=_group_by_type(all_tickets, period_start, period_end, now, current, weight_of),
    )


def get_drilldown(query: DrilldownQueryIn, namespace_id: str) -> DrilldownData:
    _validate_date_range(query.date_from, query.date_to)
    client = get_firestore_client()
    _namespace, tz, settings = _namespace_context(client, namespace_id)
    period_start, period_end = _period_bounds(query.date_from, query.date_to, tz)
    now = datetime.now(tz)

    current, carry_overs = _fetch_tickets(client, namespace_id, period_start, period_end)
    hierarchy = _location_hierarchy(client, namespace_id)
    weight_of = _weight_of_builder(hierarchy)

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
        all_tickets, period_start, period_end, now, planned, count_tickets=current, weight_of=weight_of
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
                        [t for t in all_tickets if _resolve_location(t, hierarchy)[1] == line["id"]],
                        period_start,
                        period_end,
                        now,
                        0.0,
                        count_tickets=[
                            t for t in current if _resolve_location(t, hierarchy)[1] == line["id"]
                        ],
                        weight_of=weight_of,
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
                    [t for t in all_tickets if t.get("workstation_id") == station["id"]],
                    period_start,
                    period_end,
                    now,
                    0.0,
                    count_tickets=[
                        t for t in current if t.get("workstation_id") == station["id"]
                    ],
                    weight_of=weight_of,
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
        top_kind = _pick_location_kind(
            len(hierarchy["uaps"]), len(hierarchy["lines"]), len(hierarchy["stations"])
        )
        children = _group_by_location(
            all_tickets, hierarchy, top_kind, period_start, period_end, now, current, weight_of
        )
        children_hint_key = "dashboard.drill.locationsHint"

    pareto = repair = None
    if "process" not in dims_fixed:
        pareto = _pareto_by_process(all_tickets, period_start, period_end, now, weight_of)
        repair = _repair_by_process(current)

    downtime_by_shift = None
    if "shift" not in dims_fixed:
        downtime_by_shift = _downtime_by_shift_bars(
            all_tickets, settings, period_start, period_end, now, weight_of
        )

    # `type` is only ever fixed by being a path step itself (there is no
    # `type` query param) — a fixed `process` still allows viewing its types.
    downtime_by_type = None
    if "type" not in {kind for kind, _ in steps}:
        downtime_by_type = _downtime_by_type_bars(
            all_tickets, period_start, period_end, now, weight_of
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
    if scope_kind == "uap":
        return [t for t in tickets if _resolve_location(t, hierarchy)[0] == scope_id]
    if scope_kind == "line":
        return [t for t in tickets if _resolve_location(t, hierarchy)[1] == scope_id]
    if scope_kind == "station":
        return [t for t in tickets if t.get("workstation_id") == scope_id]
    return tickets


def _daily_metric_value(
    metric: str,
    day_tickets: list[dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    now: datetime,
    weight_of: Optional[Callable[[dict[str, Any]], int]] = None,
) -> float:
    if metric == "count":
        return float(len(day_tickets))
    if metric == "mttr":
        return _mttr_seconds(day_tickets)
    # "duration": each ticket's full period-clamped downtime, attributed
    # wholly to its creation day (not re-clamped to the single day), weighted
    # per workstation affected (§5bis.1bis).
    weight_fn = weight_of if weight_of is not None else _flat_weight
    return sum(
        _ticket_downtime_seconds(issue, period_start, period_end, now) * weight_fn(issue)
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
    weight_of = _weight_of_builder(hierarchy) if hierarchy is not None else None
    if query.scope_kind != "plant":
        current = _filter_by_scope(current, hierarchy, query.scope_kind, query.scope_id or "")
        carry_overs = _filter_by_scope(
            carry_overs, hierarchy, query.scope_kind, query.scope_id or ""
        )
    if query.process:
        current = [t for t in current if _process_for_ticket(t) == query.process]
        carry_overs = [t for t in carry_overs if _process_for_ticket(t) == query.process]
    if query.shift:
        current = [t for t in current if str(t.get("shift")) == query.shift]
        carry_overs = [t for t in carry_overs if str(t.get("shift")) == query.shift]

    # `count`/`mttr` bucket only current-range tickets, by their own
    # `created_at` day (fix #1). `duration` also folds in carry-over
    # tickets, but rather than splitting a multi-day carry-over's clamped
    # downtime across every day it overlaps (invasive), it's attributed
    # wholly to the window's FIRST day — documented simplification (fix #1).
    buckets: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for issue in current:
        created_at = _parse_iso(issue.get("created_at"))
        if created_at is None:
            continue
        buckets[created_at.astimezone(tz).date()].append(issue)

    points: list[DailyPoint] = []
    day = query.date_from
    while day <= query.date_to:
        day_tickets = buckets.get(day, [])
        if query.metric == "duration" and day == query.date_from:
            day_tickets = day_tickets + carry_overs
        value = _daily_metric_value(
            query.metric, day_tickets, period_start, period_end, now, weight_of
        )
        points.append(DailyPoint(date=day.isoformat(), value=int(round(value))))
        day += timedelta(days=1)

    return DailyPointsOut(points=points)
