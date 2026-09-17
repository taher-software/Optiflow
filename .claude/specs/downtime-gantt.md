# BOM — Downtime Gantt (day view) + single-open-downtime guard

Feature branch: `feature/downtime-gantt`.
Status: **VALIDATED** — every business decision below was ruled on by the
developer at the scenario-triage gate (2026-09-11). Implementation units build
on this file, never on each other's code.

## 1. Goal

A day-scoped Gantt of the plant: for the selected production day, every resource
that encountered at least one downtime is one row, grouped in three horizontal
divisions (UAPs / production lines / workstations). X axis = the plant's working
time for that day, derived from the namespace shift configuration. Optional
filter on workstation type (bottleneck / critical / all).

Plus a new product rule: **a downtime cannot be declared on a resource that is
already down** (§4).

## 2. Backend — `GET /down-times/gantt`

Router `src/app/routers/down_time`, service in the same package.

| Item | Value |
|---|---|
| Auth | authenticated user |
| Scope | `require_roles(OWNER, ADMIN, MANAGER, PRODUCTION_SUPERVISOR)` — same set as `_kpi_scope` |
| Tenancy | caller's `namespace_id` only |
| Query `day` | ISO `YYYY-MM-DD`, optional — default: today in the namespace timezone |
| Query `type` | `bottleneck` \| `critical`, optional — default: no filter |
| Response | `ApiResponse[DownTimeGanttOut]` |
| 403 | caller lacks the role |
| 422 | malformed `day` / unknown `type` |

### 2.1 Response shape

```jsonc
{
  "day": "2026-09-11",                     // the resolved production day (namespace tz)
  "window": { "start": "2026-09-11T06:00:00+02:00",
              "end":   "2026-09-12T06:00:00+02:00" },
  "shifts": [
    { "shift": "1",
      "start": "2026-09-11T06:00:00+02:00", "end": "2026-09-11T14:00:00+02:00",
      "break_start": "2026-09-11T09:30:00+02:00", "break_end": "2026-09-11T10:00:00+02:00" }
  ],
  "uaps":          [ { "uap_id": "...",  "name": "...", "down_times": [ ... ] } ],
  "lines":         [ { "line_id": "...", "name": "...", "down_times": [ ... ] } ],
  "work_stations": [ { "workstation_id": "...", "name": "...", "type": "bottleneck",
                       "down_times": [ { "start_time": "2026-09-11T08:12:00+02:00",
                                         "end_time":   "2026-09-11T09:04:00+02:00",
                                         "state": "down" } ] } ]
}
```

- **All timestamps are full ISO datetimes** in the namespace timezone — never `HH:MM`.
- A resource appears **only if it has at least one interval** on that day.
- `down_times[]` ordered by `start_time` ascending.
- The three keys are always present (possibly empty lists).

### 2.2 The production day (`window`)

- `window.start` = the **earliest** projected shift start of `day`;
  `window.end` = the **latest** projected shift end, **carried to the next
  calendar day whenever the schedule wraps past midnight** (3-shift plants). The
  window is therefore a production day, not a calendar day.
  Bounds are `min`/`max` over the projected datetimes, NEVER the first/last entry
  of the `shift_1..shift_N` declaration order — a plant that declares its night
  shift as `shift_1` would otherwise get a zero-length window and an empty gantt
  (review finding B1, 2026-09-11). Whenever the computed `window.end` is not
  strictly after `window.start`, fall back to the calendar day.
- `shifts[]` lists the configured shifts of the namespace (same "configured
  shift" notion as the KPI services: `shift_number`, parsable clock windows,
  optional break), already projected onto absolute datetimes of that production
  day, ordered chronologically. Breaks are reported so the frontend can render
  them as non-planned time; a break is only reported when it is valid **and falls
  inside its own shift** — reuse the KPI services' break validation rather than a
  bare clock parse, so a corrupted break is ignored here exactly as the KPIs
  ignore it.
- Fallback when the namespace has no usable shift configuration: the calendar day
  `00:00 → 24:00` in the namespace timezone, `shifts: []`.

### 2.3 Which intervals, and in which state

Every issue of the namespace whose downtime overlaps `window` contributes:

| State | Interval | Meaning |
|---|---|---|
| `down` | `created_at` → `resolved_at` | resource confirmed stopped |
| `unconfirmed` | `resolved_at` → `closed_at` | fixed but production has **not** validated the return — availability is not certain |

- A ticket never resolved: `down` runs to `window.end` (open bar).
- A ticket resolved but never closed: `unconfirmed` runs to `window.end`.
- **A rejected resolution leaves no trace to draw.** `reject_resolution` nulls
  `resolved_at` when production sends a fix back, so the resolved→rejected
  `unconfirmed` slice is simply not recoverable from the stored document. Such a
  ticket therefore renders as one continuous `down` bar — the conservative and
  honest rendering, since production itself said the resource was not back.
  Accepted as-is (developer ruling, 2026-09-11); no `rejected_at` branch is to be
  kept in the service, and no test may seed a document carrying `resolved_at` and
  `rejected_at` together, which the application never produces.
- **Clamping** — every interval is clamped to `window`; a ticket started before
  the window and still down inside it is included, clamped to `window.start`.
  Intervals that end up empty are dropped.
- **Merging** — per resource and per state, overlapping or touching intervals are
  merged into one. Then `down` wins over `unconfirmed`: any overlap is subtracted
  from the `unconfirmed` intervals (a confirmed stop beats an unsure availability).

### 2.4 Row attribution

- A ticket scoped `uap` / `production line` / `work station` appears **only on its
  own resource row** — no propagation down to children.
- A `plant`-scoped ticket names no resource: it is spread over **every resource of
  the dominant location level**, the exact rule the dashboard's `by_location` uses
  — UAPs when the namespace has more than one UAP, else production lines when it
  has more than one line, else workstations. Reuse the KPI services' existing
  level-selection helper rather than re-deriving it.
- The plant spread covers **active resources only**: an archived UAP/line/station
  must not receive a red bar for a plant-wide ticket it never lived through. This
  does not contradict §2.6 — an archived resource still appears when it carries a
  ticket of its own.

### 2.5 The `type` filter — a workstation-only view

`type=bottleneck|critical` does **not** narrow the three divisions; it switches
the answer to a workstation-only view (developer ruling, 2026-09-11):

- `uaps` and `lines` are returned **empty**. Showing a line or a UAP makes no
  sense when the question asked is "which bottleneck/critical stations were
  down today".
- `work_stations` contains **only** the workstations whose `type` matches — the
  matching stations of the whole namespace, whether they hang under a production
  line or under none (the data model links a workstation to a line or to
  nothing — never straight to a UAP).
- **Ancestor downtime propagates down in this mode**: a matching station's
  intervals are the union of the tickets scoped on the station itself and the
  tickets scoped on its production line, on its UAP, and on the plant. A
  bottleneck whose line is stopped IS unavailable, and must show its red bar —
  the opposite would paint it as producing.
- The interval rules of §2.3 then apply to that union as usual: clamping,
  per-state merging, and `down` subtracted from `unconfirmed`.
- A matching station with no interval at all that day is still absent.

Without `type`, nothing changes: each resource shows only its own scope's
tickets (§2.4), and a plant ticket is spread over the dominant location level.

### 2.6 Visibility

- **Archived resources are included** here (unlike `GET /down-times`, which
  hides them): an archived resource that was down during the day must still be
  drawn, with its stored name. This is a KPI-style read.
- No role-based process narrowing: the endpoint's role scope is the only filter.

## 3. Frontend (web)

- Sidebar: new entry **"Down times"** under Dashboard, visible to the
  `_kpi_scope` roles only. Route `/app/down-times` → `ROUTES.downTimes`.
- `DownTimesPage`: day picker (default: today), type filter (all / bottleneck /
  critical) initialised from the `?type=` query param, and the Gantt — three
  stacked divisions (UAPs, lines, workstations), X axis from `window`/`shifts`
  (breaks drawn as non-planned), availability in the neutral color, `down` in the
  alert color, `unconfirmed` in a distinct third color (availability not certain)
  with a legend.
- Dashboard `KpiCards`: the bottleneck and critical divisions become clickable →
  `/app/down-times?type=bottleneck` / `?type=critical`.
- One Zustand store `useDownTimesGanttStore`, i18n fr + en.
- **No test station exists for frontend** — these units ship ungated.

## 4. Product rule — one open downtime per resource

`POST /down-times` must refuse a declaration on a resource that already has an
open downtime.

- **Conflict definition**: a declaration is refused when the target resource
  **or any of its ancestors** already carries an issue in status `pending` or
  `ongoing` — a plant-wide open ticket blocks everything, an open line ticket
  blocks that line's workstations, an open UAP ticket blocks its lines and
  their workstations. A parent that is already down makes a child declaration
  meaningless (developer ruling, 2026-09-11).
  A `resolved` (not yet closed) ticket does **not** block — the fix is done and
  a new stop is a new incident.
  The reverse direction (declaring a *parent* while a child is down) stays
  allowed: a broader stop is new information, not a duplicate. ⟨pending
  confirmation⟩
- **Response**: `409 Conflict` whose `detail` is a **structured object**, so no
  client has to parse prose:
  `{"code": "downtime_already_open", "blocking_scope": "production line",
  "blocking_ticket_id": "<id>", "message_fr": "<French sentence>",
  "message_en": "<English sentence>"}`. The two messages are the same
  user-facing sentence, naming the blocking level and ticket; the client shows
  the one matching its language as-is (developer ruling, 2026-09-17).
  `blocking_ticket_id` is **always the blocking ticket's id**. Review finding W10
  suspected a visibility leak here; it does not exist and the guard against it was
  removed rather than kept as unreachable code (developer ruling, 2026-09-11):
  declaring a downtime is restricted to `production agent`
  (`_down_time_report_scope`), and `production agent` is in
  `_FULL_VISIBILITY_ROLES` — the only role that can ever receive this 409 already
  reads every ticket of its namespace through `GET /down-times/{id}`. Hiding the
  id would have been inconsistent, and the `_is_visible` check would have cost one
  Firestore read per conflict for a branch that can never fire.
  **If the declaring role set ever widens beyond full-visibility roles, this
  decision must be revisited** — that is the single condition that makes W10 real.
- **Where**: checked synchronously in the endpoint's service (so the caller gets
  the 409), and re-checked defensively in the `add_down_time` async handler,
  which aborts without creating the ticket when the conflict exists (the endpoint
  only publishes; it never runs the handler in-process).
- **Mobile**: `DeclareDownTimeScreen` shows the 409 as a toast carrying
  `message_fr` or `message_en`, whichever matches the app language (itself
  taken from the device), falling back to the other version, then to a local
  generic sentence when the body carries neither.
- **Known residual race** (review finding W6, accepted 2026-09-11): the check and
  the write are two operations with no transaction, so two simultaneous
  declarations on the same resource can both pass. The window is small, the
  consequence is a duplicate ticket rather than data loss, and closing it
  properly means a lock document with its own lifecycle — deliberately deferred,
  stated here rather than discovered later.

## 5. Out of scope

Multi-day ranges. Export. Any mobile work beyond the §4 message.
