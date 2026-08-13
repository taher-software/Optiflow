import { useTranslation } from "react-i18next";

import {
  PROCESS_IDS,
  SHIFT_IDS,
  type StatsFilters,
} from "../constants/dashboard";

interface ScopeOption {
  kind: "plant" | "uap" | "line" | "station";
  id: string;
  label: string;
}

interface EpisodeCardProps {
  color: string;
  title: string;
  filters: StatsFilters;
  scopeOptions: ScopeOption[];
  onChange: (patch: Partial<StatsFilters>) => void;
}

const inputCls =
  "rounded-lg border border-[#d1d5db] bg-white px-2.5 py-1.5 text-[13px] text-[#16181d] focus:border-[#0d9488] focus:outline-none";
const labelCls =
  "flex min-w-0 flex-col gap-1 text-[11px] font-bold uppercase tracking-wider text-[#9ca3af]";

/** Carte de filtres d'un épisode de comparaison (scope, processus, équipe,
 * période) — liseré supérieur à la couleur de l'épisode. Présentationnel. */
export function EpisodeCard({
  color,
  title,
  filters,
  scopeOptions,
  onChange,
}: EpisodeCardProps) {
  const { t } = useTranslation();
  const scopeValue = `${filters.scope_kind}:${filters.scope_id}`;

  return (
    <div
      className="rounded-2xl border border-[#e8e8ec] bg-white p-4"
      style={{ borderTopWidth: 3, borderTopColor: color }}
    >
      <h4 className="mb-2.5 flex items-center gap-2 text-[13px] font-semibold text-[#16181d]">
        <span
          className="h-2.5 w-2.5 rounded-[3px]"
          style={{ background: color }}
        />
        {title}
      </h4>
      <div className="grid grid-cols-2 gap-2">
        <label className={labelCls}>
          {t("stats.filters.scope")}
          <select
            value={scopeValue}
            onChange={(e) => {
              const [kind, id] = e.target.value.split(":");
              onChange({
                scope_kind: kind as StatsFilters["scope_kind"],
                scope_id: id ?? "",
              });
            }}
            className={`${inputCls} font-normal normal-case tracking-normal`}
          >
            {scopeOptions.map((o) => (
              <option key={`${o.kind}:${o.id}`} value={`${o.kind}:${o.id}`}>
                {o.kind === "plant" ? t("stats.filters.wholePlant") : o.label}
              </option>
            ))}
          </select>
        </label>
        <label className={labelCls}>
          {t("dashboard.filters.process")}
          <select
            value={filters.process}
            onChange={(e) => onChange({ process: e.target.value })}
            className={`${inputCls} font-normal normal-case tracking-normal`}
          >
            <option value="">{t("dashboard.filters.allProcesses")}</option>
            {PROCESS_IDS.map((p) => (
              <option key={p} value={p}>
                {t(`dashboard.process.${p}`)}
              </option>
            ))}
          </select>
        </label>
        <label className={labelCls}>
          {t("dashboard.filters.shift")}
          <select
            value={filters.shift}
            onChange={(e) => onChange({ shift: e.target.value })}
            className={`${inputCls} font-normal normal-case tracking-normal`}
          >
            <option value="">{t("dashboard.filters.allShifts")}</option>
            {SHIFT_IDS.map((s) => (
              <option key={s} value={s}>
                {t("dashboard.shiftN", { n: s })}
              </option>
            ))}
          </select>
        </label>
        <span className="grid grid-cols-2 gap-2">
          <label className={labelCls}>
            {t("dashboard.period.from")}
            <input
              type="date"
              value={filters.from}
              max={filters.to}
              onChange={(e) => onChange({ from: e.target.value })}
              className={inputCls}
            />
          </label>
          <label className={labelCls}>
            {t("dashboard.period.to")}
            <input
              type="date"
              value={filters.to}
              min={filters.from}
              onChange={(e) => onChange({ to: e.target.value })}
              className={inputCls}
            />
          </label>
        </span>
      </div>
    </div>
  );
}

export default EpisodeCard;
