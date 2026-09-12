import {
  GANTT_LABEL_WIDTH,
  type GanttResourceRow,
  type GanttShift,
} from "../constants/downTimesGantt";
import type { AxisTick, Band, WindowMs } from "../utils/ganttGeometry";
import { GanttAxis } from "./GanttAxis";
import { GanttRow } from "./GanttRow";

interface GanttDivisionProps {
  title: string;
  /** Never empty: an empty division is not rendered at all by the page. */
  rows: GanttResourceRow[];
  win: WindowMs;
  breaks: Band[];
  /** The day's shifts, for the axis this division carries under its rows. */
  shifts: GanttShift[];
  /** The window's hourly graduation, computed once for the whole page. */
  ticks: AxisTick[];
}

/** One horizontal division of the gantt (UAPs, production lines or work
 * stations): a titled block of resource rows, closed by its own time axis so
 * the reader never has to scroll back to the top to read a bar. The axis shares
 * the rows' `GANTT_LABEL_WIDTH` gutter, which is what keeps it aligned with
 * them. Presentational. */
export function GanttDivision({
  title,
  rows,
  win,
  breaks,
  shifts,
  ticks,
}: GanttDivisionProps) {
  return (
    <section className="rounded-2xl border border-[#e8e8ec] bg-white p-5 shadow-sm">
      <h3 className="mb-3 text-[13.5px] font-semibold text-[#4b5563]">
        {title}
        <span className="ml-1.5 font-normal tabular-nums text-[#9ca3af]">
          {rows.length}
        </span>
      </h3>
      <div className="divide-y divide-[#f1f1f4]">
        {rows.map((row) => (
          <GanttRow
            key={row.id}
            name={row.name}
            badge={row.badge}
            intervals={row.intervals}
            win={win}
            breaks={breaks}
          />
        ))}
      </div>
      <div className="mt-2 border-t border-[#f1f1f4] pt-2">
        <GanttAxis
          shifts={shifts}
          win={win}
          ticks={ticks}
          labelWidthClass={GANTT_LABEL_WIDTH}
        />
      </div>
    </section>
  );
}

export default GanttDivision;
