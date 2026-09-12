import { useTranslation } from "react-i18next";

import {
  COLOR_AVAILABLE,
  COLOR_NON_PLANNED,
  GANTT_LABEL_WIDTH,
  STATE_COLOR,
  type GanttInterval,
} from "../constants/downTimesGantt";
import { formatDuration } from "../utils/dashboardFormat";
import {
  bandOf,
  clockOf,
  msOf,
  totalSeconds,
  type Band,
  type WindowMs,
} from "../utils/ganttGeometry";

interface GanttRowProps {
  /** Resource name, as stored (an archived resource keeps its name). */
  name: string;
  /** Optional qualifier shown next to the name (e.g. the workstation type). */
  badge?: string;
  intervals: GanttInterval[];
  win: WindowMs;
  /** Non-planned bands (shift breaks) of the day, shared by every row. */
  breaks: Band[];
}

/** One resource row: a neutral available track, the day's non-planned time,
 * and the resource's `down` / `unconfirmed` segments. Presentational. */
export function GanttRow({
  name,
  badge,
  intervals,
  win,
  breaks,
}: GanttRowProps) {
  const { t } = useTranslation();

  return (
    <div className="flex items-center gap-3 py-1">
      <div className={`${GANTT_LABEL_WIDTH} shrink-0`}>
        <p
          className="truncate text-[12.5px] font-medium text-[#16181d]"
          title={name}
        >
          {name}
        </p>
        {badge && (
          <p className="text-[10px] font-semibold uppercase tracking-wide text-[#9ca3af]">
            {badge}
          </p>
        )}
      </div>
      <div
        className="relative h-5 min-w-0 flex-1 overflow-hidden rounded-[4px]"
        style={{ background: COLOR_AVAILABLE }}
      >
        {/* Two shifts can share a break offset (identical shift patterns), so
            the geometry is NOT a unique key: the position in the day's ordered
            break list is. The list is static for a render, and the bands carry
            no state. */}
        {breaks.map((band, index) => (
          <div
            key={`break-${index}`}
            className="absolute inset-y-0"
            style={{
              left: `${band.left}%`,
              width: `${band.width}%`,
              background: COLOR_NON_PLANNED,
            }}
          />
        ))}
        {intervals.map((interval) => {
          const band = bandOf(interval.start_time, interval.end_time, win);
          if (!band) return null;
          const from = msOf(interval.start_time);
          const to = msOf(interval.end_time);
          const seconds = from !== null && to !== null ? (to - from) / 1000 : 0;
          return (
            <div
              key={`${interval.state}-${interval.start_time}-${interval.end_time}`}
              className="absolute inset-y-0 rounded-[3px]"
              style={{
                left: `${band.left}%`,
                width: `${band.width}%`,
                background: STATE_COLOR[interval.state],
              }}
              title={`${t(`downTimes.state.${interval.state}`)} · ${clockOf(interval.start_time) ?? ""}–${clockOf(interval.end_time) ?? ""} · ${formatDuration(seconds)}`}
            />
          );
        })}
      </div>
      {/* The bars carry their detail in a `title`, which no screen reader and no
          keyboard user reaches: state the row's totals in text as well. */}
      <p className="sr-only">
        {t("downTimes.row.summary", {
          name,
          down: formatDuration(totalSeconds(intervals, win, "down")),
          unconfirmed: formatDuration(
            totalSeconds(intervals, win, "unconfirmed"),
          ),
        })}
      </p>
    </div>
  );
}

export default GanttRow;
