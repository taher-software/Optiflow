import { useTranslation } from "react-i18next";

import {
  COLOR_DISPO,
  RAMP_COUNT,
  RAMP_DOWNTIME,
  RAMP_REPAIR,
  type Kpis,
} from "../constants/dashboard";
import { formatDuration, formatPercent } from "../utils/dashboardFormat";

const TILES: {
  key: string;
  color: string;
  value: (k: Kpis) => string;
  hintKey?: string;
}[] = [
  {
    key: "downtime",
    color: RAMP_DOWNTIME[0],
    value: (k) => formatDuration(k.downtime_seconds),
  },
  { key: "count", color: RAMP_COUNT[1], value: (k) => String(k.count) },
  {
    key: "mttr",
    color: RAMP_REPAIR[0],
    value: (k) => formatDuration(k.mttr_seconds),
    hintKey: "dashboard.kpi.mttrHint",
  },
  {
    key: "mtbf",
    color: RAMP_REPAIR[0],
    value: (k) => formatDuration(k.mtbf_seconds),
    hintKey: "dashboard.kpi.mtbfHint",
  },
  {
    key: "availability",
    color: COLOR_DISPO,
    value: (k) => formatPercent(k.availability),
  },
];

/** Bandeau des 5 KPI (soulignement à la couleur de la métrique — spec §1).
 * `compact` : variante réduite pour le panneau drill-down. */
export function KpiCards({ kpis, compact }: { kpis: Kpis; compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
      {TILES.map((tile) => (
        <div
          key={tile.key}
          className={`rounded-xl border border-[#e8e8ec] bg-white ${compact ? "p-3" : "p-4 shadow-sm"}`}
        >
          <p className="text-[11px] font-bold uppercase tracking-wider text-[#9ca3af]">
            {t(`dashboard.kpi.${tile.key}`)}
          </p>
          <p
            className={`mt-1.5 font-bold tabular-nums text-[#16181d] ${compact ? "text-lg" : "text-2xl"}`}
          >
            {tile.value(kpis)}
          </p>
          <div
            className="mt-2 h-[3px] w-7 rounded-sm"
            style={{ background: tile.color }}
          />
          {!compact && tile.hintKey && (
            <p className="mt-1 text-[11px] text-[#9ca3af]">{t(tile.hintKey)}</p>
          )}
        </div>
      ))}
    </div>
  );
}

export default KpiCards;
