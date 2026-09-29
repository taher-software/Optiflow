# BOM — KPI: downtime counts only while the plant is open, split by shift overlap

Feature branch: `feature/kpi-shift-downtime-overlap`.
Status: **DONE** — bucket A ruled on (A1–A5), suites validated and green (2026-09-29).

## 1. Goal

Two linked changes to every downtime aggregation of the KPI module
(`backend/src/app/routers/kpi/services.py`):

1. **Open-time clipping (all downtime).** Downtime only accrues while the plant
   is *open* — inside a configured shift window, outside that shift's break.
   Time when the plant is closed is never production downtime, even if the
   resource stays unavailable. Applies to `overall`, `by_location`, `by_type`,
   pareto, drilldown and daily `duration` alike.
2. **Shift attribution by overlap.** A shift's downtime is the time the stop
   actually overlapped *that* shift's open windows, not the whole ticket booked
   on the shift stored on the ticket (`issue["shift"]`, the shift it was
   opened in).

Example — shifts 1 = 06:00–14:00, 2 = 14:00–22:00, no night shift. A stop
from 20:00 to 08:00 next day: shift 2 = 2h, shift 1 = 2h, `overall` = **4h**
(was 12h). 22:00–06:00 is closed time and counts nowhere.

## 2. Definitions

- **Ticket interval** — unchanged: `[max(created_at, period_start),
  min(natural_end, period_end, now)]`; `natural_end` = `resolved_at` (CLOSED),
  else `now` bounded by the own resource's `archived_at` (resource-archiving
  rule 2).
- **Shift instances** — for each configured shift `S` (`_configured_shifts`),
  one instance per civil day `d` in the namespace timezone:
  `[d @ start_time, d @ end_time)`, or `[d @ start_time, (d+1) @ end_time)`
  when the window wraps midnight (`end_time <= start_time`). Days considered
  include `period_start.date() - 1` so the tail of a night shift started the
  day before the period is counted (then clamped by the ticket interval).
- **Shift open windows of `S`** — its instances minus its break
  (`[break_start_time, break_end_time)` inside the instance, when
  `_valid_break` returns one; an invalid break is ignored, as today).
- **Plant open windows** — the **union** of every configured shift's open
  windows. When the namespace has **no** configured shift window at all, the
  plant is open 24h/day (same fallback as `_planned_seconds_per_day`) and
  downtime is unchanged from today.
- **Ticket downtime (every aggregation)** = `|ticket interval ∩ plant open
  windows|`.
- **Ticket downtime in shift `S`** = `|ticket interval ∩ S's open windows|`.

Weighting is unchanged everywhere: per-workstation `weight_of` (§5bis.1bis),
per-row location weights, `bottleneck`/`critical` type-slice weights. Only the
per-ticket seconds change.

## 3. Units

| id | owner | produces | depends_on |
|---|---|---|---|
| `contract.bom` | orchestrator | this file | — |
| `gate.triage` | HUMAN | bucket-A answers (§6) | done |
| `test.kpi_open_time` | test | failing suite `backend/tests/api/test_kpi_open_time.py` + updated expectations in existing KPI tests (§5) | needs contract.bom |
| `gate.tests` | HUMAN | validated suite (frozen) — VALIDATED 2026-09-29 | gates test.kpi_open_time |
| `api.kpi_open_time` | api | open-window helpers + callers in §4 | gates gate.tests |
| `review.crosscut` | review | advisory report | observes api.kpi_open_time |

Acceptance for `api.kpi_open_time`: frozen suite green with zero test-file
edits, full `backend/tests` suite green.

## 4. Call sites affected

| Call site | Change |
|---|---|
| `_ticket_downtime_seconds` and every caller (`_compute_base_kpis`, `_compute_type_slice`, `_downtime_by_process`, `_downtime_by_type_bars`, `_daily_metric_value`) | clip to plant open windows (needs `settings` + `tz`) |
| `_group_by_shift` (dashboard `by_shift`) — `downtime_seconds` | overlap with the row's shift open windows; tickets = `current + carry_overs`, **regardless of stored `shift`** |
| `_downtime_by_shift_bars` (drilldown `downtime_by_shift`) | same overlap rule, one bar per configured shift |
| drilldown `shift` filter (`query.shift`, `path … shift:N`) | downtime = overlap with shift N's open windows over all tickets of the scope; `count`/`mttr`/`mtbf` keep selecting tickets by stored `shift` |
| daily `shift` filter, `metric=duration` | same overlap rule per day; `count`/`mttr` keep stored `shift` |

Unchanged: `count`, `mttr` (raw `created_at → resolved_at` of CLOSED tickets),
`mtbf` (planned / count), `repair_by_process` (repair time, not downtime),
planned-time computation, the Gantt endpoint.

## 5. Existing tests that encode the old rule

Any KPI test whose expected `downtime_seconds`/`value` involves a ticket
outside a configured shift window, or relies on stored-`shift` attribution —
at least `test_kpi_dashboard.py` (by_shift block ~L202, "ticket C (no
`shift`) excluded"), `test_kpi_weighting.py::test_by_shift_downtime_is_weighted`,
`test_kpi_type_slices.py::test_by_shift_rows_have_populated_slices`. The
test-agent re-derives those expectations under this contract; the edits are
part of the suite the developer validates.

## 6. Decisions (bucket A)

- **A1 — breaks: excluded.** Downtime during a shift's break is not booked on
  that shift, nor on `overall` unless another shift is open at that time.
- **A2 — count / mttr / mtbf: unchanged.** Still by stored `shift`, current
  range only.
- **A3 — generalize.** Drilldown bars, drilldown shift filter and daily shift
  filter all use the overlap rule for downtime.
- **A4 — closed time is never downtime.** Downtime outside every shift window
  is dropped from every aggregation (§1.1), so `Σ by_shift == overall`
  whenever shift windows don't overlap each other.
- **A5 — drilldown breakdowns under a shift filter follow the overlap rule.**
  When a drilldown has a shift filter (`query.shift` or path `shift:N`), every
  downtime figure below the header — `children` rows, `pareto_by_process`,
  `downtime_by_type` — is computed over ALL scope tickets (not filtered by
  stored `shift`) clipped to shift N's open windows, exactly like the header,
  so Σ children downtime == header downtime (same attribution rules as
  `by_location`). `count`/`mttr` in those rows keep stored `shift` (A2).
  `repair_by_process` (repair time, not downtime) is unchanged.

## 7. Bucket C (not tested)

Overlapping shift windows (overlap counted once in `overall`, in each shift's
row); DST change inside a night shift; corrupted break (ignored, as today).
