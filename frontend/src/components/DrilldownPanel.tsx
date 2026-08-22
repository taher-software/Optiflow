import type { ReactNode } from "react";
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

/** Squelette sobre affiché tant que la tranche n'est pas arrivée : mêmes
 * gabarits que le contenu final (KPIs + deux colonnes) pour éviter le saut de
 * mise en page. */
function DrilldownSkeleton({ label }: { label: string }) {
  return (
    <div aria-busy="true" aria-label={label}>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-20 animate-pulse rounded-xl border border-[#e8e8ec] bg-[#f3f4f6]"
          />
        ))}
      </div>
      <div className="mt-4 grid gap-5 lg:grid-cols-2">
        {[0, 1].map((col) => (
          <div key={col} className="space-y-2">
            <div className="h-3 w-32 animate-pulse rounded bg-[#f3f4f6]" />
            {[0, 1, 2, 3].map((row) => (
              <div
                key={row}
                className="h-8 animate-pulse rounded-lg bg-[#f3f4f6]"
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

interface DrilldownPanelProps {
  path: DrillStep[];
  /** `null` tant que la tranche n'est pas chargée : le squelette est rendu. */
  drilldown: DrilldownData | null;
  loading: boolean;
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
  loading,
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

      {!loading && drilldown ? (
        <DrilldownBody drilldown={drilldown} shifts={shifts} onPush={onPush} />
      ) : (
        <DrilldownSkeleton label={t("dashboard.drill.loading")} />
      )}
    </section>
  );
}

interface DrilldownBodyProps {
  drilldown: DrilldownData;
  shifts: ShiftWindow[];
  onPush: (row: BreakdownRow) => void;
}

/** Une section analytique : titre + graphique, rendue comme une cellule de la
 * grille à deux colonnes. */
function DrillSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div>
      <h4 className="mb-2 text-[12px] font-bold text-[#4b5563]">{title}</h4>
      {children}
    </div>
  );
}

/** Corps du panneau : KPIs de la tranche, enfants cliquables et sections
 * analytiques telles que le producteur les a fournies. */
function DrilldownBody({ drilldown, shifts, onPush }: DrilldownBodyProps) {
  const { t } = useTranslation();

  return (
    <>
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

      {/* Sections analytiques — une cellule par donnée effectivement fournie
       * par le producteur, aucune règle sur la dimension sélectionnée. La
       * grille place les cellules présentes de gauche à droite : deux
       * sections remplissent une ligne, quatre en remplissent deux. */}
      <div className="mt-4 grid gap-5 lg:grid-cols-2">
        {drilldown.pareto_by_process && (
          <DrillSection title={t("dashboard.cards.pareto")}>
            <ParetoRows rows={drilldown.pareto_by_process} />
          </DrillSection>
        )}
        {drilldown.repair_by_process && (
          <DrillSection title={t("dashboard.cards.repair")}>
            <HBars
              bars={drilldown.repair_by_process}
              ramp={RAMP_REPAIR}
              format={formatDuration}
              labelOf={(b) => t(`dashboard.process.${b.id}`)}
            />
          </DrillSection>
        )}
        {drilldown.mttr_by_agent && (
          <DrillSection title={t("dashboard.drill.mttrByAgent")}>
            <HBars
              bars={drilldown.mttr_by_agent}
              ramp={RAMP_REPAIR}
              format={formatDuration}
            />
          </DrillSection>
        )}
        {drilldown.count_by_agent && (
          <DrillSection title={t("dashboard.drill.countByAgent")}>
            <HBars
              bars={drilldown.count_by_agent}
              ramp={RAMP_COUNT[1]}
              format={String}
            />
          </DrillSection>
        )}
        {drilldown.downtime_by_shift && (
          <DrillSection title={t("dashboard.drill.downtimeByShift")}>
            <HBars
              bars={drilldown.downtime_by_shift}
              ramp={RAMP_DOWNTIME}
              format={formatDuration}
              labelOf={(b) => t("dashboard.shiftN", { n: b.id })}
            />
          </DrillSection>
        )}
        {drilldown.downtime_by_type && (
          <DrillSection title={t("dashboard.drill.downtimeByType")}>
            <HBars
              bars={drilldown.downtime_by_type}
              ramp={RAMP_DOWNTIME}
              format={formatDuration}
              labelOf={(b) => t(`dashboard.types.${b.id}`)}
            />
          </DrillSection>
        )}
      </div>
    </>
  );
}

export default DrilldownPanel;
