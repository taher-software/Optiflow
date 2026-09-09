import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { FiltersBar } from "../components/FiltersBar";
import { SelectField } from "../components/SelectField";
import { TextField } from "../components/TextField";
import { ROUTES } from "../constants/routes";
import { WORKSTATION_TYPES } from "../constants/workstations";
import { useProductionLinesStore } from "../stores/useProductionLinesStore";
import { useWorkstationsStore } from "../stores/useWorkstationsStore";
import { matchesQuery } from "../utils/textSearch";

const TYPE_STYLES: Record<string, string> = {
  standard: "bg-slate-800 text-slate-300",
  bottleneck: "bg-amber-400/15 text-amber-300",
  critical: "bg-red-500/15 text-red-300",
};

/** Line-filter value selecting the stations that belong to no line. */
const INDEPENDENT = "__independent__";

/** Lists the namespace's workstations. Owner/admin/production-supervisor. */
export function WorkstationsPage() {
  const { t } = useTranslation();
  const workstations = useWorkstationsStore((s) => s.workstations);
  const loading = useWorkstationsStore((s) => s.loading);
  const error = useWorkstationsStore((s) => s.error);
  const fetchWorkstations = useWorkstationsStore((s) => s.fetchWorkstations);
  const lines = useProductionLinesStore((s) => s.lines);
  const fetchLines = useProductionLinesStore((s) => s.fetchLines);
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [lineId, setLineId] = useState("");

  useEffect(() => {
    void fetchWorkstations();
    void fetchLines();
  }, [fetchWorkstations, fetchLines]);

  const lineName = useMemo(() => {
    const map = new Map(lines.map((l) => [l.id, l.name]));
    return (id: string | null) => (id ? (map.get(id) ?? "—") : null);
  }, [lines]);

  const typeOptions = useMemo(
    () =>
      WORKSTATION_TYPES.map((value) => ({
        value,
        label: t(`stations.types.${value}`),
      })),
    [t],
  );

  const lineOptions = useMemo(
    () => [
      ...lines.map((l) => ({ value: l.id, label: l.name })),
      { value: INDEPENDENT, label: t("stations.independent") },
    ],
    [lines, t],
  );

  const visibleWorkstations = useMemo(
    () =>
      workstations.filter((w) => {
        if (!matchesQuery(search, w.name)) return false;
        if (type !== "" && w.type !== type) return false;
        if (lineId === "") return true;
        if (lineId === INDEPENDENT) return w.production_line_id === null;
        return w.production_line_id === lineId;
      }),
    [workstations, search, type, lineId],
  );

  const hasWorkstations = !loading && !error && workstations.length > 0;

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">
          {t("stations.title")}
        </h1>
        <Link
          to={ROUTES.newStation}
          className="rounded-xl bg-teal-400 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300"
        >
          {t("stations.add")}
        </Link>
      </div>

      {loading && (
        <p className="mt-8 text-sm text-slate-400">{t("stations.loading")}</p>
      )}
      {error && <p className="mt-8 text-sm text-red-400">{error}</p>}
      {!loading && !error && workstations.length === 0 && (
        <p className="mt-8 text-sm text-slate-400">{t("stations.empty")}</p>
      )}

      {hasWorkstations && (
        <FiltersBar>
          <TextField
            id="stations-search"
            label={t("stations.filters.search")}
            value={search}
            onChange={setSearch}
            placeholder={t("stations.filters.searchPlaceholder")}
          />
          <SelectField
            id="stations-type"
            label={t("stations.filters.type")}
            value={type}
            onChange={setType}
            options={typeOptions}
            placeholder={t("stations.filters.allTypes")}
          />
          <SelectField
            id="stations-line"
            label={t("stations.filters.line")}
            value={lineId}
            onChange={setLineId}
            options={lineOptions}
            placeholder={t("stations.filters.allLines")}
          />
        </FiltersBar>
      )}

      {hasWorkstations && visibleWorkstations.length === 0 && (
        <p className="mt-8 text-sm text-slate-400">{t("stations.noResults")}</p>
      )}

      {hasWorkstations && visibleWorkstations.length > 0 && (
        <div className="mt-8 overflow-x-auto rounded-2xl border border-slate-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-900/60 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">{t("stations.table.name")}</th>
                <th className="px-4 py-3">{t("stations.table.type")}</th>
                <th className="px-4 py-3">{t("stations.table.line")}</th>
                <th className="px-4 py-3 text-right">
                  {t("stations.table.actions")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {visibleWorkstations.map((w) => {
                const line = lineName(w.production_line_id);
                return (
                  <tr key={w.id} className="hover:bg-slate-900/40">
                    <td className="px-4 py-3 font-medium text-white">
                      {w.name}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                          TYPE_STYLES[w.type] ?? TYPE_STYLES.standard
                        }`}
                      >
                        {t(`stations.types.${w.type}`)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {line ?? (
                        <span className="text-slate-500">
                          {t("stations.independent")}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        to={`${ROUTES.stations}/${w.id}`}
                        className="text-sm font-medium text-teal-400 hover:text-teal-300"
                      >
                        {t("stations.edit")}
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default WorkstationsPage;
