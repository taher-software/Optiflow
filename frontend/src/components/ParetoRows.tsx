import { useTranslation } from "react-i18next";

import { RAMP_COUNT, type ParetoRow } from "../constants/dashboard";

interface ParetoRowsProps {
  rows: ParetoRow[];
  activeId?: string;
  /** Absent = liste non cliquable (affichage seul). */
  onSelect?: (row: ParetoRow) => void;
}

/** Pareto des causes par processus (violet) : « X % · cumul Y % ». */
export function ParetoRows({ rows, activeId, onSelect }: ParetoRowsProps) {
  const { t } = useTranslation();
  if (rows.length === 0) return null;

  return (
    <div>
      {rows.map((row, idx) => {
        const active = row.id === activeId;
        const inner = (
          <>
            <span className="block truncate text-[13.5px] font-semibold text-[#16181d]">
              {t(`dashboard.process.${row.id}`)}
            </span>
            <span className="h-3 overflow-hidden rounded-md bg-[#f3f4f6]">
              <span
                className="block h-full rounded-md"
                style={{
                  width: `${Math.round(row.share * 100)}%`,
                  background: RAMP_COUNT[Math.min(idx, RAMP_COUNT.length - 1)],
                }}
              />
            </span>
            <span className="text-right text-[13px] font-semibold tabular-nums text-[#16181d]">
              {Math.round(row.share * 100)} %
              <span className="block text-[10.5px] font-normal text-[#9ca3af]">
                {t("dashboard.paretoCumul", {
                  pct: Math.round(row.cumulative * 100),
                })}
              </span>
            </span>
            <span className="text-[15px] text-[#9ca3af]">
              {onSelect ? "›" : ""}
            </span>
          </>
        );
        const cls = `mb-2 grid w-full grid-cols-[minmax(110px,165px)_1fr_86px_12px] items-center gap-3 rounded-xl border px-3 py-2.5 text-left ${
          active
            ? "border-[#0d9488]/40 bg-[#0d9488]/[.06]"
            : "border-[#e8e8ec] bg-white"
        }`;
        return onSelect ? (
          <button
            key={row.id}
            type="button"
            onClick={() => onSelect(row)}
            className={`${cls} transition-colors hover:border-[#d1d5db] hover:bg-[#fcfcfd]`}
          >
            {inner}
          </button>
        ) : (
          <div key={row.id} className={cls}>
            {inner}
          </div>
        );
      })}
    </div>
  );
}

export default ParetoRows;
