/** Day-scoped downtime Gantt — types and colors.
 *
 * Contractual reference: `.claude/specs/downtime-gantt.md` §2 and the
 * authoritative Pydantic models in
 * `backend/src/app/routers/down_time/modelsOut.py` (`Gantt*` / `DownTimeGanttOut`).
 * Every field below mirrors that response exactly — all timestamps are full
 * ISO datetimes in the namespace timezone, never `HH:MM`. */

/** The production-day window (§2.2): shift-derived, may run past midnight. */
export interface GanttWindow {
  start: string;
  end: string;
}

/** One configured shift projected onto absolute datetimes of the queried day. */
export interface GanttShift {
  /** Shift number as a string (e.g. "1"). */
  shift: string;
  start: string;
  end: string;
  break_start: string | null;
  break_end: string | null;
}

/** The two states a segment can carry (§2.3). `unconfirmed` = repaired but not
 * yet validated by production: availability is NOT certain. */
export type GanttState = "down" | "unconfirmed";

/** One down/unconfirmed segment of a resource row, already clamped and merged. */
export interface GanttInterval {
  start_time: string;
  end_time: string;
  state: GanttState;
}

export interface GanttUapRow {
  uap_id: string;
  name: string;
  down_times: GanttInterval[];
}

export interface GanttLineRow {
  line_id: string;
  name: string;
  down_times: GanttInterval[];
}

export interface GanttWorkStationRow {
  workstation_id: string;
  name: string;
  /** standard / bottleneck / critical. */
  type: string;
  down_times: GanttInterval[];
}

/** Payload of `GET /down-times/gantt` (the `data` of the ApiResponse envelope). */
export interface DownTimeGantt {
  /** Resolved production day, ISO "YYYY-MM-DD". */
  day: string;
  window: GanttWindow;
  shifts: GanttShift[];
  uaps: GanttUapRow[];
  lines: GanttLineRow[];
  work_stations: GanttWorkStationRow[];
}

/** Tailwind width class of the row-label gutter. Shared by the axis and every
 * row so the tracks stay aligned under the shift bands. */
export const GANTT_LABEL_WIDTH = "w-52";

/** A resource row of any of the three divisions, normalised for rendering.
 * The three backend row shapes differ only by the name of their id field. */
export interface GanttResourceRow {
  id: string;
  name: string;
  /** Optional qualifier (the workstation type, translated). */
  badge?: string;
  intervals: GanttInterval[];
}

/** Workstation-type filter. `""` = no filter (the three divisions are shown). */
export type GanttTypeFilter = "" | "bottleneck" | "critical";

export const GANTT_TYPE_FILTERS: GanttTypeFilter[] = [
  "",
  "bottleneck",
  "critical",
];

/** Narrows a raw `?type=` query value to the filter the endpoint accepts.
 * Anything else (including a typo) means "no filter" — never forward a value
 * the backend would answer with a 422. */
export function parseTypeFilter(raw: string | null): GanttTypeFilter {
  return raw === "bottleneck" || raw === "critical" ? raw : "";
}

/** Narrows a raw `?day=` query value to an ISO "YYYY-MM-DD" production day.
 * Anything else (including a typo or a range) means "no day": the backend then
 * resolves the plant's current production day itself, in the namespace
 * timezone. Pure. */
export function parseDayParam(raw: string | null): string {
  return raw !== null && /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : "";
}

/* ---------------- Colors ---------------------------------------------------
 * `down` reuses the downtime ramp's alert red (the dashboard's downtime color),
 * `unconfirmed` gets a DISTINCT third color — it is neither available nor
 * confirmed stopped, and must not be readable as either. */
export const COLOR_AVAILABLE = "#e8e8ec";
export const COLOR_DOWN = "#dc2626";
export const COLOR_UNCONFIRMED = "#f59e0b";
/** Non-planned time (shift breaks): outside the plant's working time. */
export const COLOR_NON_PLANNED = "#cbd1d9";

export const STATE_COLOR: Record<GanttState, string> = {
  down: COLOR_DOWN,
  unconfirmed: COLOR_UNCONFIRMED,
};
