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

- `window.start` = shift 1's `start_time` on `day`; `window.end` = the last
  configured shift's `end_time`, **carried to the next calendar day whenever the
  schedule wraps past midnight** (3-shift plants). The window is therefore a
  production day, not a calendar day.
- `shifts[]` lists the configured shifts of the namespace (same "configured
  shift" notion as the KPI services: `shift_number`, parsable clock windows,
  optional break), already projected onto absolute datetimes of that production
  day. Breaks are reported so the frontend can render them as non-planned time.
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
- A rejected resolution puts the ticket back to `ongoing`: the current `down`
  segment then resumes at `rejected_at` (the `unconfirmed` segment ends there).
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

### 2.5 Filters and visibility

- `type=bottleneck|critical` keeps: workstations whose `type` matches; **and** the
  production lines and UAPs that own at least one workstation of that type. A
  retained line/UAP still only shows its own tickets (§2.4).
- **Archived resources are included** here (unlike `GET /down-times`, which hides
  them): an archived resource that was down during the day must still be drawn,
  with its stored name. This is a KPI-style read.
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

- **Conflict definition**: an existing issue in the namespace with the *same*
  resource identity (same `production_scope` + same id; `plant` vs `plant`) whose
  status is `pending` or `ongoing`. A `resolved` (not yet closed) ticket does
  **not** block — the fix is done and a new stop is a new incident.
  Overlapping-but-different scopes (a station under an already-down line) do not
  block either.
- **Response**: `409 Conflict` with a clear, user-facing message naming the
  resource, e.g. `"A downtime is already open on this workstation (ticket
  <id>). Update the existing ticket instead of declaring a new one."`
- **Where**: checked synchronously in the endpoint's service (so the caller gets
  the 409), and re-checked defensively in the `add_down_time` async handler,
  which aborts without creating the ticket when the conflict exists (the endpoint
  only publishes; it never runs the handler in-process).
- **Mobile**: `DeclareDownTimeScreen` surfaces the 409 as a clear localised
  message (fr + en), not a generic error toast.

## 5. Out of scope

Multi-day ranges. Export. Any mobile work beyond the §4 message.
