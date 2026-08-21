import { useTranslation } from "react-i18next";

import {
  PROCESS_IDS,
  RAMP_COUNT,
  RAMP_DOWNTIME,
  RAMP_REPAIR,
  SHIFT_IDS,
  TYPE_PROCESS,
  type BreakdownRow,
  type DrilldownData,
  type DrillStep,
  type ShiftWindow,
} from "../constants/dashboard";
import { formatDuration } from "../utils/dashboardFormat";
import { dimensionLabel } from "../utils/dashboardLabels";
import { DowntimeRows } from "./DowntimeRows";
import { HBars } from "./HBars";
import { KpiCards } from "./KpiCards";
import { ParetoRows } from "./ParetoRows";

interface DrilldownPanelProps {
  path: DrillStep[];
  drilldown: DrilldownData;
  drillProcess: string;
  drillShift: string;
  /** Fenêtres horaires réelles du tenant (`namespace.shifts`). */
  shifts: ShiftWindow[];
  onPush: (row: BreakdownRow) => void;
  onPopTo: (index: number) => void;
  onClose: () => void;
  onProcessFilter: (process: string) => void;
  onShiftFilter: (shift: string) => void;
}

/** Panneau drill-down : fil d'Ariane, KPIs de la tranche, enfants
 * hiérarchiques cliquables et sections analytiques. Les sections présentes
 * viennent du producteur (règle « jamais sa propre dimension » — spec §3) ;
 * ce composant ne fait qu'afficher ce qu'on lui donne. */
export function DrilldownPanel({
  path,
  drilldown,
  drillProcess,
  drillShift,
  shifts,
  onPush,
  onPopTo,
  onClose,
  onProcessFilter,
  onShiftFilter,
}: DrilldownPanelProps) {
  const { t } = useTranslation();
  const sel = path[path.length - 1];
  const inPath = (kind: string) => path.some((s) => s.kind === kind);
  const showProcessFilter = !inPath("process") && !inPath("type");
  const showShiftFilter = !inPath("shift");
  const isProcess = sel.kind === "process";

  return (
    <section className="mb-5 rounded-2xl border border-[#0d9488]/40 bg-white p-5 shadow-sm">
      {/* Fil d'Ariane */}
      <nav className="mb-1 flex flex-wrap items-center gap-1 text-[12px] text-[#9ca3af]">
        <button
          type="button"
          onClick={onClose}
          className="rounded px-1 text-[#4b5563] hover:text-[#0d9488]"
        >
          {t("dashboard.drill.root")}
        </button>
        {path.map((step, i) => (
          <span
            key={`${step.kind}-${step.id}`}
            className="flex items-center gap-1"
          >
            <span className="opacity-60">›</span>
            {i < path.length - 1 ? (
              <button
                type="button"
                onClick={() => onPopTo(i)}
                className="rounded px-1 text-[#4b5563] hover:text-[#0d9488]"
              >
                {dimensionLabel(t, step.kind, step.id, step.label, shifts)}
              </button>
            ) : (
              <span className="px-1 text-[#16181d]">
                {dimensionLabel(t, step.kind, step.id, step.label, shifts)}
              </span>
            )}
          </span>
        ))}
      </nav>

      {/* Tête */}
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wider text-[#0d9488]">
            {t(`dashboard.dimension.${sel.kind}`)}
          </p>
          <h2 className="mt-0.5 text-lg font-bold text-[#16181d]">
            {dimensionLabel(t, sel.kind, sel.id, sel.label, shifts)}
          </h2>
          {sel.kind === "type" && TYPE_PROCESS[sel.id] && (
            <span className="mt-1.5 inline-flex items-center gap-1.5 rounded-lg bg-[#f3f4f6] px-2.5 py-1 text-[12px] text-[#4b5563]">
              {t("dashboard.drill.associatedProcess")}{" "}
              <b>{t(`dashboard.process.${TYPE_PROCESS[sel.id]}`)}</b>
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-[#d1d5db] bg-white px-3 py-1.5 text-[13px] text-[#4b5563] hover:text-[#16181d]"
        >
          ✕ {t("dashboard.drill.close")}
        </button>
      </div>

      {/* Filtres locaux (jamais une dimension déjà fixée par le chemin) */}
      {(showProcessFilter || showShiftFilter) && (
        <div className="mb-4 flex flex-wrap items-end gap-3">
          {showProcessFilter && (
            <label className="flex flex-col gap-1 text-[11px] font-bold uppercase tracking-wider text-[#9ca3af]">
              {t("dashboard.filters.process")}
              <select
                value={drillProcess}
                onChange={(e) => onProcessFilter(e.target.value)}
                className="rounded-lg border border-[#d1d5db] bg-white px-2.5 py-1.5 text-[13px] font-normal normal-case tracking-normal text-[#16181d] focus:border-[#0d9488] focus:outline-none"
              >
                <option value="">{t("dashboard.filters.allProcesses")}</option>
                {PROCESS_IDS.map((p) => (
                  <option key={p} value={p}>
                    {t(`dashboard.process.${p}`)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {showShiftFilter && (
            <label className="flex flex-col gap-1 text-[11px] font-bold uppercase tracking-wider text-[#9ca3af]">
              {t("dashboard.filters.shift")}
              <select
                value={drillShift}
                onChange={(e) => onShiftFilter(e.target.value)}
                className="rounded-lg border border-[#d1d5db] bg-white px-2.5 py-1.5 text-[13px] font-normal normal-case tracking-normal text-[#16181d] focus:border-[#0d9488] focus:outline-none"
              >
                <option value="">{t("dashboard.filters.allShifts")}</option>
                {SHIFT_IDS.map((s) => (
                  <option key={s} value={s}>
                    {t("dashboard.shiftN", { n: s })}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}

      <KpiCards kpis={drilldown.kpis} compact />

      {/* Enfants hiérarchiques */}
      {drilldown.children && drilldown.children.length > 0 && (
        <div className="mt-4">
          <h4 className="mb-1 text-[12px] font-bold text-[#4b5563]">
            {t("dashboard.drill.childrenTitle")}{" "}
            {drilldown.children_hint_key && (
              <span className="font-normal text-[#9ca3af]">
                — {t(drilldown.children_hint_key)}
              </span>
            )}
          </h4>
          <div className="grid gap-x-3 lg:grid-cols-2">
            <DowntimeRows
              rows={drilldown.children}
              shifts={shifts}
              onSelect={onPush}
            />
          </div>
        </div>
      )}

      {/* Sections analytiques */}
      {isProcess ? (
        <div className="mt-4 grid gap-5 lg:grid-cols-2">
          {drilldown.mttr_by_agent && (
            <div>
              <h4 className="mb-2 text-[12px] font-bold text-[#4b5563]">
                {t("dashboard.drill.mttrByAgent")}
              </h4>
              <HBars
                bars={drilldown.mttr_by_agent}
                ramp={RAMP_REPAIR}
                format={formatDuration}
              />
            </div>
          )}
          {drilldown.count_by_agent && (
            <div>
              <h4 className="mb-2 text-[12px] font-bold text-[#4b5563]">
                {t("dashboard.drill.countByAgent")}
              </h4>
              <HBars
                bars={drilldown.count_by_agent}
                ramp={RAMP_COUNT[1]}
                format={String}
              />
            </div>
          )}
        </div>
      ) : (
        <div className="mt-4 grid gap-5 lg:grid-cols-2">
          <div>
            {drilldown.pareto_by_process && (
              <>
                <h4 className="mb-2 text-[12px] font-bold text-[#4b5563]">
                  {t("dashboard.cards.pareto")}
                </h4>
                <ParetoRows rows={drilldown.pareto_by_process} />
              </>
            )}
            {drilldown.downtime_by_shift && (
              <>
                <h4 className="mb-2 mt-4 text-[12px] font-bold text-[#4b5563]">
                  {t("dashboard.drill.downtimeByShift")}
                </h4>
                <HBars
                  bars={drilldown.downtime_by_shift}
                  ramp={RAMP_DOWNTIME}
                  format={formatDuration}
                  labelOf={(b) => t("dashboard.shiftN", { n: b.id })}
                />
              </>
            )}
          </div>
          <div>
            {drilldown.repair_by_process && (
              <>
                <h4 className="mb-2 text-[12px] font-bold text-[#4b5563]">
                  {t("dashboard.cards.repair")}
                </h4>
                <HBars
                  bars={drilldown.repair_by_process}
                  ramp={RAMP_REPAIR}
                  format={formatDuration}
                  labelOf={(b) => t(`dashboard.process.${b.id}`)}
                />
              </>
            )}
            {drilldown.downtime_by_type && (
              <>
                <h4 className="mb-2 mt-4 text-[12px] font-bold text-[#4b5563]">
                  {t("dashboard.drill.downtimeByType")}
                </h4>
                <HBars
                  bars={drilldown.downtime_by_type}
                  ramp={RAMP_DOWNTIME}
                  format={formatDuration}
                  labelOf={(b) => t(`dashboard.types.${b.id}`)}
                />
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

export default DrilldownPanel;
