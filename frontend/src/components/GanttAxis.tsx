import { useTranslation } from "react-i18next";

import {
  COLOR_NON_PLANNED,
  type GanttShift,
} from "../constants/downTimesGantt";
import {
  bandOf,
  breakBands,
  clockOf,
  type AxisTick,
  type WindowMs,
} from "../utils/ganttGeometry";

interface GanttAxisProps {
  shifts: GanttShift[];
  win: WindowMs;
  /** Hourly graduation of the window, derived once by the page (`hourTicks`)
   * and shared by every division's axis. */
  ticks: AxisTick[];
  /** Width class of the row-label gutter, shared with the rows so the axis and
   * the tracks stay aligned. */
  labelWidthClass: string;
}

/** X axis of the gantt: the plant's working time for the production day.
 * Shift bands with their number and window on top, an HOURLY graduation below,
 * breaks shown as non-planned time. Presentational. */
export function GanttAxis({
  shifts,
  win,
  ticks,
  labelWidthClass,
}: GanttAxisProps) {
  const { t } = useTranslation();
  const breaks = breakBands(shifts, win);

  return (
    <div className="mb-1 flex items-stretch gap-3">
      <div
        className={`${labelWidthClass} shrink-0 text-[11px] font-bold uppercase tracking-wider text-[#9ca3af]`}
      >
        {t("downTimes.axis.workingTime")}
      </div>
      <div className="min-w-0 flex-1">
        <div className="relative h-5">
          {shifts.map((shift) => {
            const band = bandOf(shift.start, shift.end, win);
            if (!band) return null;
            return (
              <div
                key={`${shift.shift}-${shift.start}`}
                className="absolute inset-y-0 overflow-hidden rounded-[4px] border border-[#e8e8ec] bg-[#f6f7f9] px-1.5 text-[10px] font-semibold leading-5 text-[#6b7280]"
                style={{ left: `${band.left}%`, width: `${band.width}%` }}
                title={`${t("downTimes.axis.shift", { n: shift.shift })} · ${clockOf(shift.start) ?? ""}–${clockOf(shift.end) ?? ""}`}
              >
                <span className="block truncate">
                  {t("downTimes.axis.shift", { n: shift.shift })}
                </span>
              </div>
            );
          })}
          {/* Same key rule as the rows: two shifts can share a break offset,
              so the position in the list is the unique key, not the geometry. */}
          {breaks.map((band, index) => (
            <div
              key={`break-${index}`}
              className="absolute inset-y-0"
              style={{
                left: `${band.left}%`,
                width: `${band.width}%`,
                background: COLOR_NON_PLANNED,
              }}
              title={t("downTimes.legend.nonPlanned")}
            />
          ))}
        </div>
        {/* Hourly graduation: a gridline on every whole hour, the label only
            where `hourTicks` allowed one — the axis repeats under every
            division, so it stays deliberately thin. */}
        <div className="relative h-5">
          {ticks.map((tick) => (
            <span
              key={tick.id}
              className="absolute top-0 flex -translate-x-1/2 flex-col items-center"
              style={{ left: `${tick.left}%` }}
            >
              <span
                aria-hidden="true"
                className={`w-px ${tick.bound ? "h-[5px] bg-[#cbd1d9]" : "h-[3px] bg-[#e2e5ea]"}`}
              />
              {tick.labelled && (
                <span
                  className={`text-[10px] leading-4 tabular-nums ${tick.bound ? "text-[#6b7280]" : "text-[#9ca3af]"}`}
                >
                  {tick.label}
                </span>
              )}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

export default GanttAxis;
