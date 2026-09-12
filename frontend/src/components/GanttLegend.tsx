import { useTranslation } from "react-i18next";

import {
  COLOR_AVAILABLE,
  COLOR_DOWN,
  COLOR_NON_PLANNED,
  COLOR_UNCONFIRMED,
} from "../constants/downTimesGantt";

const ITEMS = [
  { key: "available", color: COLOR_AVAILABLE },
  { key: "down", color: COLOR_DOWN },
  { key: "unconfirmed", color: COLOR_UNCONFIRMED },
  { key: "nonPlanned", color: COLOR_NON_PLANNED },
] as const;

/** Legend of the gantt. `unconfirmed` is spelled out rather than named: a
 * repaired-but-unvalidated stretch is not a known-available one, and a reader
 * who takes it for availability draws the wrong conclusion. Presentational. */
export function GanttLegend() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
      {ITEMS.map((item) => (
        <span
          key={item.key}
          className="flex items-center gap-1.5 text-[12px] text-[#4b5563]"
        >
          <span
            className="h-2.5 w-4 rounded-[3px]"
            style={{ background: item.color }}
          />
          {t(`downTimes.legend.${item.key}`)}
        </span>
      ))}
      <span className="text-[11px] text-[#9ca3af]">
        {t("downTimes.legend.unconfirmedHint")}
      </span>
    </div>
  );
}

export default GanttLegend;
