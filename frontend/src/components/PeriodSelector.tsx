import { useTranslation } from "react-i18next";

import { PERIOD_PRESETS, type PeriodPreset } from "../constants/dashboard";

interface PeriodSelectorProps {
  period: PeriodPreset;
  customFrom: string;
  customTo: string;
  onPreset: (preset: PeriodPreset) => void;
  onRange: (from: string, to: string) => void;
}

/** Sélecteur de période : Aujourd'hui / 7 j / 30 j / plage libre (un seul
 * jour possible en mettant from = to). Présentationnel. */
export function PeriodSelector({
  period,
  customFrom,
  customTo,
  onPreset,
  onRange,
}: PeriodSelectorProps) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {PERIOD_PRESETS.map((preset) => (
        <button
          key={preset}
          type="button"
          onClick={() => onPreset(preset)}
          className={`rounded-lg border px-3.5 py-1.5 text-[13px] font-medium transition-colors ${
            period === preset
              ? "border-[#0d9488] bg-[#0d9488] font-semibold text-white"
              : "border-[#d1d5db] bg-white text-[#4b5563] hover:text-[#16181d]"
          }`}
        >
          {t(`dashboard.period.${preset}`)}
        </button>
      ))}
      {period === "custom" && (
        <span className="flex items-center gap-1.5 text-[#9ca3af]">
          <input
            type="date"
            value={customFrom}
            max={customTo}
            aria-label={t("dashboard.period.from")}
            onChange={(e) => onRange(e.target.value, customTo)}
            className="rounded-lg border border-[#d1d5db] bg-white px-2 py-1.5 text-[13px] text-[#16181d] focus:border-[#0d9488] focus:outline-none"
          />
          →
          <input
            type="date"
            value={customTo}
            min={customFrom}
            aria-label={t("dashboard.period.to")}
            onChange={(e) => onRange(customFrom, e.target.value)}
            className="rounded-lg border border-[#d1d5db] bg-white px-2 py-1.5 text-[13px] text-[#16181d] focus:border-[#0d9488] focus:outline-none"
          />
        </span>
      )}
    </div>
  );
}

export default PeriodSelector;
