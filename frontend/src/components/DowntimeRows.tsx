import { useTranslation } from "react-i18next";

import {
  RAMP_DOWNTIME,
  type BreakdownRow,
  type ShiftWindow,
} from "../constants/dashboard";
import { formatDuration, shade } from "../utils/dashboardFormat";
import { dimensionLabel } from "../utils/dashboardLabels";

interface DowntimeRowsProps {
  rows: BreakdownRow[];
  /** id de la rangée active (surlignée) le cas échéant. */
  activeId?: string;
  /** Fenêtres horaires réelles du tenant, pour les rangées « équipe ». */
  shifts?: ShiftWindow[];
  onSelect: (row: BreakdownRow) => void;
}

/** Rangées « temps d'arrêt » cliquables (style maquette) :
 * libellé + méta | barre rouge (intensité ∝ volume) | valeur | ›  */
export function DowntimeRows({
  rows,
  activeId,
  shifts,
  onSelect,
}: DowntimeRowsProps) {
  const { t } = useTranslation();
  if (rows.length === 0) return null;
  const max = Math.max(...rows.map((r) => r.kpis.downtime_seconds), 1);

  return (
    <div>
      {rows.map((row) => {
        const ratio = row.kpis.downtime_seconds / max;
        const active = row.id === activeId;
        return (
          <button
            key={`${row.kind}-${row.id}`}
            type="button"
            onClick={() => onSelect(row)}
            className={`mb-2 grid w-full grid-cols-[minmax(110px,165px)_1fr_86px_12px] items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors ${
              active
                ? "border-[#0d9488]/40 bg-[#0d9488]/[.06]"
                : "border-[#e8e8ec] bg-white hover:border-[#d1d5db] hover:bg-[#fcfcfd]"
            }`}
          >
            <span className="min-w-0">
              <span className="block truncate text-[13.5px] font-semibold text-[#16181d]">
                {dimensionLabel(t, row.kind, row.id, row.label, shifts)}
              </span>
              <span className="block text-[11px] tabular-nums text-[#9ca3af]">
                {t("dashboard.rowMeta", {
                  count: row.kpis.count,
                  mttr: formatDuration(row.kpis.mttr_seconds),
                })}
              </span>
            </span>
            <span className="h-3 overflow-hidden rounded-md bg-[#f3f4f6]">
              <span
                className="block h-full rounded-md"
                style={{
                  width: `${Math.max(4, Math.round(ratio * 100))}%`,
                  background: shade(RAMP_DOWNTIME, ratio),
                }}
              />
            </span>
            <span className="text-right text-[13px] font-semibold tabular-nums text-[#16181d]">
              {formatDuration(row.kpis.downtime_seconds)}
            </span>
            <span className="text-[15px] text-[#9ca3af]">›</span>
          </button>
        );
      })}
    </div>
  );
}

export default DowntimeRows;
