# Review — `review.crosscut` — feature/downtime-gantt

- **Mode**: cross-cutting (whole feature reviewed as one change)
- **Scope**: `git diff main...HEAD` + uncommitted working tree — backend
  (`routers/down_time/`, `core/down_time_conflict.py`, `async_jobs/add_down_time.py`),
  frontend (`DownTimesPage`, `useDownTimesGanttStore`, `Gantt*`, `ganttGeometry`/`ganttRows`,
  `KpiCards`, routes/sidebar/i18n), mobile (`DeclareDownTimeScreen`, `useDownTimeStore`,
  `ConflictNotice`, `utils/downTimeConflict.ts`, i18n)
- **Contract**: `.claude/specs/downtime-gantt.md` (VALIDATED)
- **Frozen suite**: 67 passed (`test_down_time_gantt.py`, `test_down_time_conflict_guard.py`,
  `test_add_down_time_conflict_guard.py`)
- **Nothing was blocked. No code was modified.**

## Severity counts

| blocking | warning | info |
|---|---|---|
| **1** | **9** | **6** |

**Score: 52 / 100** (informational; dragged by the single blocking finding — the rest of
the change is careful, well-documented and consistent with the existing KPI conventions).

Two known issues were excluded on instruction (`reject_resolution` nulling `resolved_at`;
the mobile sentence-parsing coupling). See "Known issues — new angles" for the one new
consequence of each that is not a re-report.

---

## Blocking

### B1 — A non-chronological shift configuration silently empties the whole Gantt

- **Location**: `backend/src/app/routers/down_time/services.py:1140-1141` (`_gantt_window`)
- **Severity**: blocking
- **Description**: `window_start` is taken from `shifts[0]` and `window_end` from
  `shifts[-1]`, i.e. from the *declaration order* of `shift_1..shift_N`, with no check that
  the result is a non-empty interval. Nothing in the settings model forces shift 1 to be the
  chronologically first shift. A 3-shift plant that numbers its night shift first
  (`shift_1` = 22:00→06:00, `shift_2` = 06:00→14:00, `shift_3` = 14:00→22:00) yields
  `window_start == window_end == 22:00` — verified by direct call:

  ```
  night-first: (2026-09-11 22:00:00+02:00, 2026-09-11 22:00:00+02:00)
  normal:      (2026-09-11 06:00:00+02:00, 2026-09-12 06:00:00+02:00)
  ```

  Every interval is then dropped by `_clamp_interval` (`clamped_start >= clamped_end`), every
  row is dropped for having no interval, and the endpoint returns a structurally valid
  `200` with three empty divisions. The frontend's `windowMs` also returns `null`
  (`end <= start`) and renders `downTimes.noWindow`. No error is raised anywhere, on either
  side. For a downtime tool the failure mode is the worst kind: a supervisor reads
  "nothing was down today" while the KPI dashboard, fed by the same tickets, reports
  downtime. The same happens for any non-chronological ordering (e.g. `shift_1` = 14:00→22:00,
  `shift_2` = 06:00→14:00).
- **Suggestion**: derive the window from the projected datetimes rather than from
  declaration order, and guard the degenerate case. In `_gantt_window`, after building
  `shifts`, compute
  `window_start = min(parsed starts)`, `window_end = max(parsed ends)`, and if
  `window_end <= window_start`, fall back to the calendar-day window
  (`[day 00:00, day+1 00:00)`) while still returning `shifts` — never return a zero-length or
  inverted window. Add a frozen-suite scenario for a night-first 3-shift namespace.

---

## Warnings

### W2 — The Gantt reads the tenant's entire `issues` subcollection for a one-day view

- **Location**: `backend/src/app/routers/down_time/services.py:1477-1479` (`get_down_time_gantt`)
- **Severity**: warning
- **Description**: `client.find_subdocuments(DOWN_TIME_COLLECTION, namespace_id,
  ISSUES_SUBCOLLECTION)` is called with **no `params`** — every downtime ticket the tenant
  has ever created is read on every request, to render one day. Cost and latency grow
  linearly with the tenant's history forever. The KPI layer already solved exactly this
  problem with a bounded, parallelised three-query union
  (`routers/kpi/services.py:2165-2191`: `created_at` range, `status in` open,
  `resolved_at >=` period start), so this is also convention drift away from an existing,
  better pattern in the same codebase. The cost is multiplied downstream: in
  `_type_filtered_station_rows` (`services.py:1417-1446`) `plant_issues` — the whole history
  of plant-scope tickets — is re-appended and re-segmented for *every* matching station,
  giving O(stations × plant tickets) Python work per request.
- **Suggestion**: mirror `kpi.services`'s union, using the resolved window as the period:
  (1) `created_at` in `[window_start, window_end]`, (2) `status in (pending, ongoing,
  resolved)` for tickets that started earlier and are still live, (3) `closed_at >=
  window_start` (or `resolved_at >= window_start`) for tickets that started earlier and
  ended inside the window; de-duplicate by `id` and run the three via
  `kpi_services._run_parallel`. Also hoist the plant-issue segment computation out of the
  per-station loop (compute the clamped/merged plant intervals once, then union per station).

### W3 — Tenant isolation is correct, but a plant-scope ticket is spread onto archived resources

- **Location**: `backend/src/app/routers/down_time/services.py:1396-1406` (`_unfiltered_gantt_rows`)
- **Severity**: warning
- **Description**: (Tenant scoping itself is clean everywhere on the new paths — the issue
  query is a namespace subcollection, `_location_hierarchy` filters on `namespace_id`, and
  `_resolve_ancestor_ids` re-checks `namespace_id` on every document it walks. No missing
  tenant filter found.) The problem is archiving: the plant-ticket spread iterates
  `hierarchy["uaps"]` / `["lines"]` / `["stations"]` directly, which by design contain
  archived resources. `_pick_location_kind` deliberately counts **active** resources only
  (rule 5), and the KPI layer applies rule 4 — "perimeter at ticket date", filtering a
  resource out of a ticket's spread when it was archived *before* that ticket's `created_at`.
  The Gantt applies neither: a UAP archived six months ago still gets a full-width red bar
  for today's plant-wide ticket. §2.6 asks archived resources to be kept so their *own* past
  tickets remain drawn — not so that new plant-wide tickets are attributed to resources that
  no longer exist. The result also contradicts the dashboard's `by_location` for the same day.
- **Suggestion**: when spreading `plant_issues`, filter the target resources the way rule 4
  does — skip a resource whose `archived_at` is earlier than the issue's `created_at` (reuse
  `core.archiving`/the KPI helper rather than re-deriving). Resources' own-scope tickets stay
  unfiltered, per §2.6.

### W4 — The Gantt renders shift breaks the KPI layer rejects as invalid

- **Location**: `backend/src/app/routers/down_time/services.py:1088-1096` (`_project_shift`)
- **Severity**: warning
- **Description**: `_project_shift` validates the break with a bare `parse_hhmm` pair, where
  `kpi.services._valid_break` additionally requires (via `break_minutes_in_window`) that the
  break be non-zero and fall **inside** the shift window. A stored break outside its shift is
  therefore ignored by every KPI computation but projected and returned here. Verified: a
  shift 06:00→14:00 carrying a break 20:00→21:00 logs
  `kpi: unparsable/invalid shift break '20:00'/'21:00', ignoring break` from the KPI helper,
  while the Gantt returns `break_start='2026-09-11T20:00:00+02:00'`,
  `break_end='...T21:00:00+02:00'` — a non-planned grey band drawn outside every shift, past
  the axis, by `breakBands`/`GanttRow`. Two layers disagree on the same namespace's planned
  time. The offset formula `(break_start_minutes - start_minutes) % (24*60)` also silently
  relocates an out-of-window break to a plausible-looking position rather than rejecting it.
- **Suggestion**: replace the local parse with `kpi_services._valid_break(shift)` and return
  `break_start=None/break_end=None` when it returns `None` — one validation rule, the KPI
  one, for both layers.

### W5 — The async re-check is not actually independent: it trusts ancestor ids from the payload

- **Location**: `backend/src/app/async_jobs/add_down_time.py:555-562`;
  `backend/src/app/core/down_time_conflict.py:96-120` (`_resolve_ancestor_ids`)
- **Severity**: warning
- **Description**: the handler passes `uap_id` / `production_line_id` / `workstation_id`
  straight from the job payload, and `_resolve_ancestor_ids` only fills in ids that are
  **missing** — it never verifies a supplied one. On the endpoint path that is safe
  (`_validate_workstation` / `_validate_production_line` reject a chain that doesn't match
  Firestore). But the whole stated purpose of this second check is to hold "against whatever
  Firestore's state is by the time this job actually runs", and `/pubsub_job` is
  unauthenticated by design and recopies the payload without revalidation (the handler's own
  §9.5/W5 comment says exactly that, a few lines above). A payload carrying a wrong or absent
  `production_line_id` for a workstation declaration makes the guard check the wrong ancestor
  chain and silently pass. So the defensive check inherits the trust of the very payload it
  is meant to be defensive about.
- **Suggestion**: in the handler, pass only the id of the declared scope
  (`workstation_id` for `work station`, `production_line_id` for `production line`, …) and let
  `find_blocking_conflict` resolve the chain from the resource documents, as its docstring
  already anticipates for this caller. Cost: at most two extra `get_document` reads on the
  create path only.

### W6 — The guard has no atomicity: two concurrent declarations can both create a ticket

- **Location**: `backend/src/app/core/down_time_conflict.py:180-186` +
  `backend/src/app/async_jobs/add_down_time.py:555` (check) /
  `create_subdocument` (write)
- **Severity**: warning
- **Description**: check and write are two separate Firestore operations with no transaction
  and no unique-key constraint. Two declarations on the same station published within the
  same window run both handlers in parallel; both read "no open issue" before either writes,
  and both create a ticket — exactly the state §4 exists to prevent. The endpoint-side check
  narrows the window; it does not close it. The frozen suite covers the sequential case only.
- **Suggestion**: make the invariant structural rather than advisory — e.g. write a lock
  document keyed deterministically on the blocked resource
  (`down_time/{namespace}/open_locks/{workstation_id|line_id|uap_id|plant}`) with
  `create_document` (fails if it already exists), cleared on resolve/close/delete; or perform
  the read-then-write inside a Firestore transaction. If the residual race is acceptable,
  say so explicitly in the BOM rather than leaving it implicit.

### W7 — A refused declaration is lost silently: the caller was already told `202 Accepted`

- **Location**: `backend/src/app/async_jobs/add_down_time.py:564-570`
- **Severity**: warning
- **Description**: when the handler's re-check fires, `FunctionalJobError` is logged and
  acked — no ticket, no retry, and **no signal to the reporter**, who received `202` with a
  `job_id` and a green "Downtime reported." toast on mobile. The information lost is limited
  (the resource is genuinely covered by another open ticket), but the reporter's own
  `down_time_type` / `department` and the fact that a second operator saw the stop are gone,
  and the UI stated the opposite of what happened. The endpoint's 409 path is the only one
  the user ever learns about.
- **Suggestion**: at minimum log at `warning` with the reporter's id and the blocking ticket
  id so the loss is traceable (currently the message carries the blocking id but not the
  reporter). Better: have the handler append the refused declaration as a note/event on the
  blocking ticket, so the second report is not erased. Either way, the mobile store should
  not treat a `202` as a guaranteed ticket.

### W8 — Mobile: the workstation picker never clears a stale conflict banner

- **Location**: `mobile/src/screens/DeclareDownTimeScreen.tsx:141` (`onStation` defined) vs.
  `:258` (`onChange={setStationSel}`)
- **Severity**: warning
- **Description**: the change adds `onStation`, which calls `clearConflict()` before
  `setStationSel`, alongside `onScope` / `onUap` / `onLine` / `onType` — but the station
  `OptionPicker` was never rewired and still calls `setStationSel` directly. `onStation` is
  dead code. Consequence: after a 409 on station A, selecting station B keeps the
  `ConflictNotice` on screen, with a message naming the old level and an "Open the existing
  ticket" button pointing at station A's ticket, while the form is now about station B. This
  is the single most-likely follow-up action after a conflict, so it will be hit constantly.
- **Suggestion**: `onChange={onStation}` on the station picker (line 258).

### W9 — Mobile: "Open the existing ticket" can dead-end on a 404

- **Location**: `mobile/src/screens/DeclareDownTimeScreen.tsx:279-300` (the `ConflictNotice`
  action) → `backend/src/app/routers/down_time/services.py:639-660` (`get_down_time`)
- **Severity**: warning
- **Description**: the banner offers to navigate to the blocking ticket, but `get_down_time`
  applies `_is_visible`: a non-full-visibility role (the declaring production agent) only
  sees tickets whose `process` matches their own. A blocking ticket routed to another process
  — very common for an ancestor-level stop declared by someone else — returns `404 Downtime
  ticket not found.`, so the primary call-to-action lands on an error screen.
- **Suggestion**: only render the action when the ticket is reachable (probe
  `GET /down-times/{id}` before showing the button, or have the 409 body carry a
  `blocking_ticket_visible` flag); otherwise show the reference as text only.

### W10 — The 409 body hands out a ticket id across the visibility boundary

- **Location**: `backend/src/app/routers/down_time/services.py:230-245` (`_conflict_detail`),
  raised at `:281-284`
- **Severity**: warning
- **Description**: the message embeds the blocking ticket's id unconditionally. `get_down_time`
  deliberately answers `404` rather than `403` for a ticket outside the caller's process
  "so existence isn't leaked across the visibility boundary" — this new message leaks exactly
  that: the existence, the id, and the scope level of a ticket the same caller is not allowed
  to read. The id was mandated by §4's example message, so the product ruling stands; what is
  new is that §4 never considered the process-visibility rule. Low impact (an opaque UUID
  within the caller's own tenant), but it contradicts a stated rule of this module.
- **Suggestion**: include the id only when `_is_visible(blocking_issue, current["role"])`;
  otherwise keep the level wording without the `(ticket …)` clause — which the mobile parser
  already tolerates (`ticketId === "" → null`, and the regex simply fails to match, falling
  back to level `"unknown"`).

---

## Info

### I1 — `_gantt_window` round-trips datetimes through ISO strings
- **Location**: `backend/src/app/routers/down_time/services.py:1140-1141`
- `datetime.fromisoformat(shifts[0].start)` re-parses a string the function itself just
  produced. **Suggestion**: have `_project_shift` return `(GanttShiftOut, start_dt, end_dt)`
  (or a small dataclass) and use the datetimes directly — it also makes B1's fix trivial.

### I2 — Interval timestamps are not normalised to the namespace timezone
- **Location**: `backend/src/app/routers/down_time/services.py:1331-1334` (`_row_intervals`)
- Clamped bounds are emitted with whatever offset the stored string carried, whereas the
  window/shifts carry the offset computed for the queried day. Across a DST boundary — or
  after a namespace timezone change — one response can mix offsets. Positions stay correct
  (the frontend uses absolute ms), but `clockOf` labels tooltips from the raw string, so a
  tooltip can disagree with the axis by an hour. `kpi.services` normalises with
  `.astimezone(tz)` (`services.py:2658`). **Suggestion**: `.astimezone(tz)` before
  `isoformat()`.

### I3 — `_conflict_detail` has an untyped parameter
- **Location**: `backend/src/app/routers/down_time/services.py:230`
- `def _conflict_detail(conflict) -> str` — every other helper in the module is annotated.
  **Suggestion**: `conflict: DownTimeConflict` (import the dataclass from
  `core.down_time_conflict`).

### I4 — §2.5's "directly under a UAP" has no counterpart in the data model
- **Location**: `.claude/specs/downtime-gantt.md` §2.5 vs.
  `backend/src/app/routers/workstation/modelsIn.py` (`production_line_id` only) and
  `core/down_time_conflict.py:_resolve_ancestor_ids`
- A workstation links to a line or to nothing; there is no `uap_id` on a station document.
  So a line-less station never inherits a UAP's downtime — in the Gantt's type-filtered view
  *or* in the conflict guard. The implementation is right for the model; the spec sentence is
  what is wrong. **Suggestion**: correct §2.5 to "under a production line, or independent",
  so nobody later "fixes" the code to match the spec.

### I5 — The KPI-card link drops the dashboard's selected period
- **Location**: `frontend/src/components/KpiCards.tsx:173`
- Clicking the bottleneck/critical division while the dashboard shows last month lands on
  *today's* Gantt. **Suggestion**: carry the dashboard's end date as `?day=` when the
  selected period is not the current day.

### I6 — `breakBands` React keys can collide
- **Location**: `frontend/src/components/GanttRow.tsx:63`
- `key={`break-${band.left}`}` — two shifts whose breaks start at the same offset (identical
  shift patterns) produce duplicate keys. **Suggestion**: key on the index, or on
  `${band.left}-${band.width}`.

---

## Known issues — new angles only

- **`reject_resolution` nulls `resolved_at`**: the new consequence is that the
  `rejected_after_resolve` branch of `_issue_segments`
  (`services.py:1181-1196`) is **unreachable in production** — with `resolved_at` cleared the
  function returns a single `created_at → window_end` `down` segment and never evaluates
  `rejected_at`. §2.3's "the `down` segment resumes at `rejected_at`" is therefore satisfied
  by accident (the bar is indeed red), but the `unconfirmed` slice that preceded the rejection
  is silently erased from the Gantt as well as from the ticket. Whatever fix is chosen for
  the `resolved_at` nulling, this branch needs a test seeded from a document the app really
  produces.
- **Mobile 409 sentence parsing**: judgement, since it was asked for — the coupling is
  **contained but genuinely fragile**. It is well isolated (one pure function, one regex, one
  label table, degrades to `"unknown"` rather than to a generic error), so a wording drift
  costs a less precise message, not a crash. But it is a *silent* degradation: nothing fails,
  no test on either side of the wire catches it (the backend suite asserts the sentence, the
  mobile side has no test station at all), and the backend message is also what W10 proposes
  to change. Rated: a warning-level coupling, not blocking — the fix is cheap and should be
  taken with the next touch of that endpoint: add `blocking_scope` / `blocking_ticket_id` to
  a structured 409 body and have the mobile store read fields instead of prose.

---

## Coverage gaps in the frozen suite (production will hit these)

- Non-chronological shift numbering (B1) — no scenario.
- A break stored outside its shift window (W4) — no scenario.
- The plant-ticket spread onto an archived resource (W3) — archiving is tested only for a
  resource's *own* tickets.
- Concurrency on the guard (W6) — only the sequential endpoint/handler paths are covered.
- A namespace with a large ticket history (W2) — no volume/read-count assertion.
- DST transition days for the window projection.
- Frontend and mobile ship **ungated**: there is no test station for either, so
  W8/W9/I5/I6 are caught by review only.

## Inputs obtained / not obtained

- Obtained: full diff + working tree, the validated BOM, the frozen suite (run green),
  the KPI service conventions the feature reuses.
- Not obtained: none material. The skill's `{TO_FILL}` project-specific anti-pattern list is
  still unset, so this pass used the standard rubric plus the conventions observable in
  `routers/kpi/services.py` and `async_jobs/`.
