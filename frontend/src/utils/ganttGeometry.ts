import type {
  GanttInterval,
  GanttShift,
  GanttWindow,
} from "../constants/downTimesGantt";

/** The production-day window as absolute milliseconds. */
export interface WindowMs {
  start: number;
  end: number;
}

/** A horizontal band of the chart, in percent of the window width. */
export interface Band {
  left: number;
  width: number;
}

/** A graduation of the X axis, positioned in percent of the window width. */
export interface AxisTick {
  /** Stable key (the absolute instant it marks). */
  id: string;
  left: number;
  /** Clock time in the NAMESPACE timezone, e.g. "06:00". */
  label: string;
  /** Whether the label is printed. `false` = gridline only (density rule). */
  labelled: boolean;
  /** A window bound that is not a whole hour — styled apart from the hours. */
  bound: boolean;
}

/** One hour in milliseconds. */
const HOUR_MS = 3_600_000;

/** Above this many hours a 1-label-per-hour axis stops being readable, so only
 * every second hour is labelled. 14 h = the widest 2-shift day. */
const DENSE_ABOVE_HOURS = 14;

/** Minimum horizontal gap (percent of the window) between two printed labels.
 * Keeps a bound label from colliding with the hour label next to it. */
const MIN_LABEL_GAP = 3;

/** Absolute instant of an ISO datetime, or `null` when unparsable.
 * Instants are timezone-agnostic, so arithmetic on them is correct whatever
 * the browser's own timezone. Pure. */
export function msOf(iso: string): number | null {
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

/** Clock time of an ISO datetime IN ITS OWN OFFSET, e.g.
 * "2026-09-11T06:00:00+02:00" → "06:00". Read straight off the string on
 * purpose: `new Date(...).getHours()` would re-project the instant onto the
 * browser's timezone and label a 06:00 plant shift "05:00" for a visitor in
 * another country. `null` when the string is not an ISO datetime. Pure. */
export function clockOf(iso: string): string | null {
  const match = /^\d{4}-\d{2}-\d{2}T(\d{2}:\d{2})/.exec(iso);
  return match ? match[1] : null;
}

/** The window as milliseconds, or `null` when its bounds are unusable
 * (unparsable, or zero/negative length — nothing can be positioned on it). Pure. */
export function windowMs(window: GanttWindow): WindowMs | null {
  const start = msOf(window.start);
  const end = msOf(window.end);
  if (start === null || end === null || end <= start) return null;
  return { start, end };
}

/** Band covering [startIso..endIso], clamped to the window. `null` when either
 * bound is unparsable or the clamped span is empty (entirely outside). Pure. */
export function bandOf(
  startIso: string,
  endIso: string,
  win: WindowMs,
): Band | null {
  const rawStart = msOf(startIso);
  const rawEnd = msOf(endIso);
  if (rawStart === null || rawEnd === null) return null;
  const start = Math.max(rawStart, win.start);
  const end = Math.min(rawEnd, win.end);
  if (end <= start) return null;
  const span = win.end - win.start;
  return {
    left: ((start - win.start) / span) * 100,
    width: ((end - start) / span) * 100,
  };
}

/** Offset of an instant inside the window, in percent. `null` when unparsable
 * or outside the window. Pure. */
export function offsetOf(iso: string, win: WindowMs): number | null {
  const ms = msOf(iso);
  if (ms === null || ms < win.start || ms > win.end) return null;
  return ((ms - win.start) / (win.end - win.start)) * 100;
}

/** Non-planned bands of the day: every shift break, clamped to the window.
 * Shifts without a complete break pair contribute nothing. Pure. */
export function breakBands(shifts: GanttShift[], win: WindowMs): Band[] {
  const bands: Band[] = [];
  for (const shift of shifts) {
    if (!shift.break_start || !shift.break_end) continue;
    const band = bandOf(shift.break_start, shift.break_end, win);
    if (band) bands.push(band);
  }
  return bands;
}

/** Milliseconds elapsed since the top of the hour, read off the ISO string —
 * same reason as `clockOf`: the browser's own timezone must never take part.
 * `null` when the string is not an ISO datetime. Pure. */
export function subHourMs(iso: string): number | null {
  const match =
    /^\d{4}-\d{2}-\d{2}T\d{2}:(\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?/.exec(iso);
  if (!match) return null;
  const minutes = Number(match[1]);
  const seconds = Number(match[2] ?? "0");
  const millis = Number((match[3] ?? "0").padEnd(3, "0"));
  return minutes * 60_000 + seconds * 1_000 + millis;
}

/** X-axis graduation: one tick per WHOLE HOUR of the production-day window,
 * from the first whole hour at or after `window.start` to the last one at or
 * before `window.end`, plus the window's own bounds when they are not whole
 * hours — so the axis is always closed on both sides.
 *
 * Clock labels are derived from `window.start`'s own clock and plain hour
 * arithmetic, never from `new Date(...).getHours()`: a 06:00 plant shift stays
 * "06:00" for a visitor in another timezone.
 *
 * Density: every hour gets a tick, but a window longer than `DENSE_ABOVE_HOURS`
 * (a 3-shift 24 h day) prints a label on even hours only. The two bounding
 * ticks are always labelled, and an hour label too close to one of them is
 * dropped rather than overprinted. Pure. */
export function hourTicks(window: GanttWindow): AxisTick[] {
  const win = windowMs(window);
  const startClock = clockOf(window.start);
  const endClock = clockOf(window.end);
  const startSub = subHourMs(window.start);
  const endSub = subHourMs(window.end);
  if (!win || !startClock || !endClock || startSub === null || endSub === null)
    return [];

  const span = win.end - win.start;
  const dense = span > DENSE_ABOVE_HOURS * HOUR_MS;

  /* First whole hour at or after the start, and the clock it reads. */
  const lead = startSub === 0 ? 0 : HOUR_MS - startSub;
  const firstMs = win.start + lead;
  const firstHour =
    (Number(startClock.slice(0, 2)) + (lead === 0 ? 0 : 1)) % 24;
  const lastMs = win.end - endSub;

  const ticks: AxisTick[] = [];
  if (startSub !== 0)
    ticks.push({
      id: String(win.start),
      left: 0,
      label: startClock,
      labelled: true,
      bound: true,
    });

  for (let ms = firstMs, step = 0; ms <= lastMs; ms += HOUR_MS, step += 1) {
    const hour = (firstHour + step) % 24;
    ticks.push({
      id: String(ms),
      left: ((ms - win.start) / span) * 100,
      label: `${String(hour).padStart(2, "0")}:00`,
      labelled: !dense || hour % 2 === 0,
      bound: false,
    });
  }

  if (endSub !== 0)
    ticks.push({
      id: String(win.end),
      left: 100,
      label: endClock,
      labelled: true,
      bound: true,
    });

  if (ticks.length === 0) return ticks;
  /* The axis is closed by its own bounds: whatever the density rule said, the
     first and the last graduation always carry their clock. */
  ticks[0].labelled = true;
  ticks[ticks.length - 1].labelled = true;

  /* Drop any label that would overprint the one kept before it. A bound label
     wins over the hour label crowding it — the axis must stay closed. */
  let kept = 0;
  for (let i = 1; i < ticks.length; i += 1) {
    const tick = ticks[i];
    if (!tick.labelled) continue;
    if (tick.left - ticks[kept].left >= MIN_LABEL_GAP) {
      kept = i;
    } else if (tick.bound && !ticks[kept].bound) {
      ticks[kept].labelled = false;
      kept = i;
    } else {
      tick.labelled = false;
    }
  }
  return ticks;
}

/** Total seconds an interval list covers inside the window, per state.
 * The backend already merged and de-overlapped the segments (§2.3), so a plain
 * sum is exact — no re-merging here. Pure. */
export function totalSeconds(
  intervals: GanttInterval[],
  win: WindowMs,
  state: GanttInterval["state"],
): number {
  const span = win.end - win.start;
  let percent = 0;
  for (const interval of intervals) {
    if (interval.state !== state) continue;
    const band = bandOf(interval.start_time, interval.end_time, win);
    if (band) percent += band.width;
  }
  return (percent / 100) * (span / 1000);
}
