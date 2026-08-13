import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { DowntimeRows } from "../components/DowntimeRows";
import { DrilldownPanel } from "../components/DrilldownPanel";
import { HBars } from "../components/HBars";
import { KpiCards } from "../components/KpiCards";
import { ParetoRows } from "../components/ParetoRows";
import { PeriodSelector } from "../components/PeriodSelector";
import { RAMP_REPAIR, type BreakdownRow } from "../constants/dashboard";
import { ROUTES } from "../constants/routes";
import { useDashboardStore } from "../stores/useDashboardStore";
import { formatDuration } from "../utils/dashboardFormat";

/** Carte blanche titrée d'un décorticage. */
function Card({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[#e8e8ec] bg-white p-5 shadow-sm">
      <h3 className="mb-3 text-[13.5px] font-semibold text-[#4b5563]">
        {title}
        {hint && <span className="font-normal text-[#9ca3af]"> — {hint}</span>}
      </h3>
      {children}
    </section>
  );
}

/** Dashboard KPI de l'usine (spec `.claude/specs/kpi-dashboard.md`, visuel
 * `frontend/design/kpi-dashboard-mockup.html`). Thème CLAIR (décision
 * client) sur coque sombre. Données MOCK via le store — seul le store change
 * quand les endpoints /kpi/* existeront. */
export function DashboardPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const data = useDashboardStore((s) => s.data);
  const drilldown = useDashboardStore((s) => s.drilldown);
  const period = useDashboardStore((s) => s.period);
  const customFrom = useDashboardStore((s) => s.customFrom);
  const customTo = useDashboardStore((s) => s.customTo);
  const drillPath = useDashboardStore((s) => s.drillPath);
  const drillProcess = useDashboardStore((s) => s.drillProcess);
  const drillShift = useDashboardStore((s) => s.drillShift);
  const loading = useDashboardStore((s) => s.loading);
  const fetchDashboard = useDashboardStore((s) => s.fetchDashboard);
  const setPeriod = useDashboardStore((s) => s.setPeriod);
  const setCustomRange = useDashboardStore((s) => s.setCustomRange);
  const openDrill = useDashboardStore((s) => s.openDrill);
  const pushDrill = useDashboardStore((s) => s.pushDrill);
  const popTo = useDashboardStore((s) => s.popTo);
  const closeDrill = useDashboardStore((s) => s.closeDrill);
  const setDrillProcess = useDashboardStore((s) => s.setDrillProcess);
  const setDrillShift = useDashboardStore((s) => s.setDrillShift);

  useEffect(() => {
    void fetchDashboard();
  }, [fetchDashboard]);

  const open = (row: BreakdownRow) =>
    openDrill({ kind: row.kind, id: row.id, label: row.label });
  const push = (row: BreakdownRow) =>
    pushDrill({ kind: row.kind, id: row.id, label: row.label });
  const activeId = (kind: string) => {
    const last = drillPath[drillPath.length - 1];
    return last && last.kind === kind ? last.id : undefined;
  };

  const locationKind = data?.by_location[0]?.kind ?? "uap";
  const locationTitleKey =
    locationKind === "line"
      ? "dashboard.cards.byLine"
      : locationKind === "station"
        ? "dashboard.cards.byStation"
        : "dashboard.cards.byUap";

  return (
    <div className="min-h-full bg-[#fafafa] px-8 py-8 text-[#16181d]">
      <div className="mx-auto max-w-6xl">
        {/* En-tête — rangée 1 : titre + actions « stats » épinglées en haut à
            droite ; rangée 2 : sélecteur de période aligné à droite. */}
        <div className="mb-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[11px] font-bold uppercase tracking-widest text-[#0d9488]">
                {t("dashboard.eyebrow")}
              </p>
              <h1 className="mt-0.5 text-[22px] font-bold tracking-tight">
                {data?.namespace.name ?? t("dashboard.title")}
              </h1>
              <p className="mt-1 max-w-xl text-[13px] text-[#4b5563]">
                {t("dashboard.subtitle")}
              </p>
            </div>
            <div className="flex shrink-0 gap-2">
              <button
                type="button"
                onClick={() => navigate(ROUTES.stats)}
                className="rounded-lg border border-[#d1d5db] bg-white px-3 py-1.5 text-[13px] text-[#4b5563] hover:text-[#16181d]"
              >
                {t("dashboard.exploreStats")}
              </button>
              <button
                type="button"
                onClick={() => navigate(`${ROUTES.stats}?mode=compare`)}
                className="rounded-lg border border-[#d1d5db] bg-white px-3 py-1.5 text-[13px] text-[#4b5563] hover:text-[#16181d]"
              >
                ⇄ {t("dashboard.compareEpisodes")}
              </button>
            </div>
          </div>
          <div className="mt-3 flex justify-end">
            <PeriodSelector
              period={period}
              customFrom={customFrom}
              customTo={customTo}
              onPreset={setPeriod}
              onRange={setCustomRange}
            />
          </div>
        </div>

        {!data ? (
          <p className="mt-10 text-[13px] text-[#9ca3af]">
            {loading ? t("dashboard.loading") : t("dashboard.empty")}
          </p>
        ) : (
          <>
            <KpiCards kpis={data.overall} />

            <div className="mt-5">
              {drillPath.length > 0 && drilldown && (
                <DrilldownPanel
                  path={drillPath}
                  drilldown={drilldown}
                  drillProcess={drillProcess}
                  drillShift={drillShift}
                  onPush={push}
                  onPopTo={popTo}
                  onClose={closeDrill}
                  onProcessFilter={setDrillProcess}
                  onShiftFilter={setDrillShift}
                />
              )}
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              {data.namespace.shift_number > 1 && (
                <Card
                  title={t("dashboard.cards.byShift")}
                  hint={t("dashboard.cards.clickHint")}
                >
                  <DowntimeRows
                    rows={data.by_shift}
                    activeId={activeId("shift")}
                    onSelect={open}
                  />
                </Card>
              )}
              <Card
                title={t(locationTitleKey)}
                hint={t("dashboard.cards.clickHint")}
              >
                <DowntimeRows
                  rows={data.by_location}
                  activeId={activeId(locationKind)}
                  onSelect={open}
                />
              </Card>
              <Card
                title={t("dashboard.cards.pareto")}
                hint={t("dashboard.cards.paretoHint")}
              >
                <ParetoRows
                  rows={data.pareto_by_process}
                  activeId={activeId("process")}
                  onSelect={(row) =>
                    openDrill({ kind: "process", id: row.id, label: row.id })
                  }
                />
              </Card>
              <Card
                title={t("dashboard.cards.repair")}
                hint={t("dashboard.cards.repairHint")}
              >
                <HBars
                  bars={data.repair_by_process}
                  ramp={RAMP_REPAIR}
                  format={formatDuration}
                  labelOf={(b) => t(`dashboard.process.${b.id}`)}
                />
              </Card>
              <Card
                title={t("dashboard.cards.byType")}
                hint={t("dashboard.cards.clickHint")}
              >
                <DowntimeRows
                  rows={data.by_type}
                  activeId={activeId("type")}
                  onSelect={open}
                />
              </Card>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default DashboardPage;
