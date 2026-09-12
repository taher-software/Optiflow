import type {
  GanttLineRow,
  GanttResourceRow,
  GanttUapRow,
  GanttWorkStationRow,
} from "../constants/downTimesGantt";

/** UAP rows → renderable rows. Pure. */
export function uapRows(rows: GanttUapRow[]): GanttResourceRow[] {
  return rows.map((row) => ({
    id: row.uap_id,
    name: row.name,
    intervals: row.down_times,
  }));
}

/** Production-line rows → renderable rows. Pure. */
export function lineRows(rows: GanttLineRow[]): GanttResourceRow[] {
  return rows.map((row) => ({
    id: row.line_id,
    name: row.name,
    intervals: row.down_times,
  }));
}

/** Workstation rows → renderable rows, the station type carried as the badge.
 * `labelOf` translates the raw type; an unknown type falls back to its raw
 * value rather than disappearing. Pure. */
export function stationRows(
  rows: GanttWorkStationRow[],
  labelOf: (type: string) => string,
): GanttResourceRow[] {
  return rows.map((row) => ({
    id: row.workstation_id,
    name: row.name,
    badge: row.type ? labelOf(row.type) : undefined,
    intervals: row.down_times,
  }));
}
