import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { BarChart } from "../components/BarChart";
import { EpisodeCard } from "../components/EpisodeCard";
import { HBars } from "../components/HBars";
import {
  COLOR_EP1,
  COLOR_EP2,
  METRIC_COLOR,
  PROCESS_IDS,
  RAMP_DOWNTIME,
  SHIFT_IDS,
  type StatsMetric,
  type StatsMode,
} from "../constants/dashboard";
import { useStatsStore } from "../stores/useStatsStore";
import { formatDuration, formatMetric } from "../utils/dashboardFormat";
import { mockScopeOptions } from "../utils/dashboardMock";

const METRICS: StatsMetric[] = ["duration", "count", "mttr"];

const selectCls =
  "rounded-lg border border-[#d1d5db] bg-white px-2.5 py-1.5 text-[13px] font-normal normal-case tracking-normal text-[#16181d] focus:border-[#0d9488] focus:outline-none";
const filterLabelCls =
  "flex flex-col gap-1 text-[11px] font-bold uppercase tracking-wider text-[#9ca3af]";

/** Explorateur Stats (icône « Stats ») : suivi journalier d'une métrique
 * (temps d'arrêt / nb d'arrêts / MTTR) avec scope, processus, équipe et
 * période — et comparaison de deux épisodes à filtres indépendants (spec §4).
 * Données MOCK via le store. */
export function StatsPage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();

  const metric = useStatsStore((s) => s.metric);
  const mode = useStatsStore((s) => s.mode);
  const filters = useStatsStore((s) => s.filters);
  const episode1 = useStatsStore((s) => s.episode1);
  const episode2 = useStatsStore((s) => s.episode2);
  const daily = useStatsStore((s) => s.daily);
  const daily1 = useStatsStore((s) => s.daily1);
  const daily2 = useStatsStore((s) => s.daily2);
  const fetchSeries = useStatsStore((s) => s.fetchSeries);
  const setMetric = useStatsStore((s) => s.setMetric);
  const setMode = useStatsStore((s) => s.setMode);
  const setFilters = useStatsStore((s) => s.setFilters);
  const setEpisode1 = useStatsStore((s) => s.setEpisode1);
  const setEpisode2 = useStatsStore((s) => s.setEpisode2);

  useEffect(() => {
    if (searchParams.get("mode") === "compare") setMode("compare");
    void fetchSeries();
  }, [searchParams, setMode, fetchSeries]);

  const scopeOptions = mockScopeOptions();
  const scopeLabel =
    filters.scope_kind === "plant"
      ? t("stats.filters.wholePlant")
      : (scopeOptions.find(
          (o) => o.kind === filters.scope_kind && o.id === filters.scope_id,
        )?.label ?? "");

  const fmt = (v: number) => formatMetric(v, metric);

  /* Comparaison : alignement par index de jour (J1 → Jn). */
  const len = Math.max(daily1.length, daily2.length);
  const pad = (arr: number[]) =>
    arr.length >= len
      ? arr
      : [...arr, ...Array.from({ length: len - arr.length }, () => 0)];
  const total1 = daily1.reduce((s, p) => s + p.value, 0);
  const total2 = daily2.reduce((s, p) => s + p.value, 0);
  const gap = total2 > 0 ? ((total1 - total2) / total2) * 100 : 0;

  return (
    <div className="min-h-full bg-[#fafafa] px-8 py-8 text-[#16181d]">
      <div className="mx-auto max-w-6xl">
        {/* En-tête */}
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-widest text-[#0d9488]">
              {t("stats.eyebrow")}
            </p>
            <h1 className="mt-0.5 text-[22px] font-bold tracking-tight">
              {t("stats.title")}
            </h1>
            <p className="mt-1 text-[13px] text-[#4b5563]">
              {t("stats.subtitle")}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="inline-flex gap-0.5 rounded-xl border border-[#d1d5db] bg-white p-[3px]">
              {(["follow", "compare"] as StatsMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  className={`rounded-[9px] px-3.5 py-1.5 text-[13px] font-medium ${
                    mode === m
                      ? "bg-[#16181d] font-semibold text-white"
                      : "text-[#4b5563] hover:text-[#16181d]"
                  }`}
                >
                  {t(`stats.mode.${m}`)}
                </button>
              ))}
            </div>
            <div className="inline-flex gap-0.5 rounded-xl border border-[#d1d5db] bg-white p-[3px]">
              {METRICS.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMetric(m)}
                  className={`rounded-[9px] px-3.5 py-1.5 text-[13px] font-medium ${
                    metric === m
                      ? "bg-[#0d9488] font-semibold text-white"
                      : "text-[#4b5563] hover:text-[#16181d]"
                  }`}
                >
                  {t(`stats.metric.${m}`)}
                </button>
              ))}
            </div>
          </div>
        </div>

        {mode === "follow" ? (
          <>
            {/* Filtres du suivi */}
            <div className="mb-4 flex flex-wrap items-end gap-3">
              <label className={filterLabelCls}>
                {t("stats.filters.scope")}
                <select
                  value={`${filters.scope_kind}:${filters.scope_id}`}
                  onChange={(e) => {
                    const [kind, id] = e.target.value.split(":");
                    setFilters({
                      scope_kind: kind as typeof filters.scope_kind,
                      scope_id: id ?? "",
                    });
                  }}
                  className={selectCls}
                >
                  {scopeOptions.map((o) => (
                    <option
                      key={`${o.kind}:${o.id}`}
                      value={`${o.kind}:${o.id}`}
                    >
                      {o.kind === "plant"
                        ? t("stats.filters.wholePlant")
                        : o.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className={filterLabelCls}>
                {t("dashboard.filters.process")}
                <select
                  value={filters.process}
                  onChange={(e) => setFilters({ process: e.target.value })}
                  className={selectCls}
                >
                  <option value="">
                    {t("dashboard.filters.allProcesses")}
                  </option>
                  {PROCESS_IDS.map((p) => (
                    <option key={p} value={p}>
                      {t(`dashboard.process.${p}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className={filterLabelCls}>
                {t("dashboard.filters.shift")}
                <select
                  value={filters.shift}
                  onChange={(e) => setFilters({ shift: e.target.value })}
                  className={selectCls}
                >
                  <option value="">{t("dashboard.filters.allShifts")}</option>
                  {SHIFT_IDS.map((s) => (
                    <option key={s} value={s}>
                      {t("dashboard.shiftN", { n: s })}
                    </option>
                  ))}
                </select>
              </label>
              <label className={filterLabelCls}>
                {t("dashboard.period.from")}
                <input
                  type="date"
                  value={filters.from}
                  max={filters.to}
                  onChange={(e) => setFilters({ from: e.target.value })}
                  className={selectCls}
                />
              </label>
              <label className={filterLabelCls}>
                {t("dashboard.period.to")}
                <input
                  type="date"
                  value={filters.to}
                  min={filters.from}
                  onChange={(e) => setFilters({ to: e.target.value })}
                  className={selectCls}
                />
              </label>
            </div>

            {/* Graphe journalier */}
            <section className="rounded-2xl border border-[#e8e8ec] bg-white p-5 pb-2 shadow-sm">
              <div className="mb-1 flex items-baseline justify-between gap-3">
                <h3 className="text-[14px] font-semibold">
                  {t(`stats.metricTitle.${metric}`)}
                </h3>
                <div className="flex items-center gap-1.5 text-[12px] text-[#4b5563]">
                  <span
                    className="h-2.5 w-2.5 rounded-[3px]"
                    style={{ background: METRIC_COLOR[metric] }}
                  />
                  {scopeLabel} ·{" "}
                  {filters.process
                    ? t(`dashboard.process.${filters.process}`)
                    : t("dashboard.filters.allProcesses")}{" "}
                  ·{" "}
                  {filters.shift
                    ? t("dashboard.shiftN", { n: filters.shift })
                    : t("dashboard.filters.allShifts")}
                </div>
              </div>
              <BarChart
                series={[
                  {
                    name: scopeLabel,
                    color: METRIC_COLOR[metric],
                    values: daily.map((p) => p.value),
                  },
                ]}
                labelOf={(i) => {
                  const d = daily[i];
                  return d
                    ? `${d.date.slice(8, 10)}/${d.date.slice(5, 7)}`
                    : "";
                }}
                format={fmt}
              />
            </section>
          </>
        ) : (
          <>
            {/* Comparaison de deux épisodes */}
            <div className="mb-4 grid gap-4 lg:grid-cols-2">
              <EpisodeCard
                color={COLOR_EP1}
                title={t("stats.compare.ep1")}
                filters={episode1}
                scopeOptions={scopeOptions}
                onChange={setEpisode1}
              />
              <EpisodeCard
                color={COLOR_EP2}
                title={t("stats.compare.ep2")}
                filters={episode2}
                scopeOptions={scopeOptions}
                onChange={setEpisode2}
              />
            </div>

            <div className="mb-4 flex flex-wrap gap-3">
              {[
                { label: t("stats.compare.total1"), value: fmt(total1) },
                { label: t("stats.compare.total2"), value: fmt(total2) },
              ].map((d) => (
                <div
                  key={d.label}
                  className="rounded-xl border border-[#e8e8ec] bg-white px-4 py-2.5 text-[12px] text-[#4b5563]"
                >
                  {d.label}
                  <b className="block text-[16px] tabular-nums text-[#16181d]">
                    {d.value}
                  </b>
                </div>
              ))}
              <div className="rounded-xl border border-[#e8e8ec] bg-white px-4 py-2.5 text-[12px] text-[#4b5563]">
                {t("stats.compare.gap")}
                <b
                  className="block text-[16px] tabular-nums"
                  style={{ color: gap >= 0 ? COLOR_EP1 : "#059669" }}
                >
                  {gap >= 0 ? "+" : ""}
                  {gap.toFixed(1).replace(".", ",")} %
                </b>
              </div>
            </div>

            <section className="rounded-2xl border border-[#e8e8ec] bg-white p-5 pb-3 shadow-sm">
              <div className="mb-1 flex items-baseline justify-between gap-3">
                <h3 className="text-[14px] font-semibold">
                  {t(`stats.metricTitle.${metric}`)} —{" "}
                  {t("stats.compare.title")}
                </h3>
                <div className="flex gap-4 text-[12px] text-[#4b5563]">
                  <span className="flex items-center gap-1.5">
                    <span
                      className="h-2.5 w-2.5 rounded-[3px]"
                      style={{ background: COLOR_EP1 }}
                    />
                    {t("stats.compare.ep1")}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span
                      className="h-2.5 w-2.5 rounded-[3px]"
                      style={{ background: COLOR_EP2 }}
                    />
                    {t("stats.compare.ep2")}
                  </span>
                </div>
              </div>
              <BarChart
                series={[
                  {
                    name: t("stats.compare.ep1"),
                    color: COLOR_EP1,
                    values: pad(daily1.map((p) => p.value)),
                  },
                  {
                    name: t("stats.compare.ep2"),
                    color: COLOR_EP2,
                    values: pad(daily2.map((p) => p.value)),
                  },
                ]}
                labelOf={(i) => `J${i + 1}`}
                format={fmt}
              />
              <p className="mb-1 mt-1.5 text-[11px] text-[#9ca3af]">
                {t("stats.compare.axisHint")}
              </p>
            </section>
          </>
        )}
        {/* Répartitions du suivi (sous le graphe, mode suivi uniquement) */}
        {mode === "follow" && (
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <section className="rounded-2xl border border-[#e8e8ec] bg-white p-5 shadow-sm">
              <h3 className="mb-2 text-[13.5px] font-semibold text-[#4b5563]">
                {t("stats.byShift")}
              </h3>
              <HBars
                bars={SHIFT_IDS.map((id, i) => ({
                  id,
                  label: id,
                  value: daily
                    .filter((_, idx) => idx % SHIFT_IDS.length === i)
                    .reduce((s, p) => s + p.value, 0),
                }))}
                ramp={RAMP_DOWNTIME}
                format={metric === "count" ? String : formatDuration}
                labelOf={(b) => t("dashboard.shiftN", { n: b.id })}
              />
            </section>
            <section className="rounded-2xl border border-[#e8e8ec] bg-white p-5 shadow-sm">
              <h3 className="mb-2 text-[13.5px] font-semibold text-[#4b5563]">
                {t("stats.byProcess")}
              </h3>
              <HBars
                bars={PROCESS_IDS.map((id, i) => ({
                  id,
                  label: id,
                  value: daily
                    .filter((_, idx) => idx % PROCESS_IDS.length === i)
                    .reduce((s, p) => s + p.value, 0),
                }))}
                ramp={RAMP_DOWNTIME}
                format={metric === "count" ? String : formatDuration}
                labelOf={(b) => t(`dashboard.process.${b.id}`)}
              />
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

export default StatsPage;
