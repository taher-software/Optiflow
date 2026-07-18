import { useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { ROUTES } from "../constants/routes";
import { useProductionLinesStore } from "../stores/useProductionLinesStore";
import { useWorkstationsStore } from "../stores/useWorkstationsStore";

const TYPE_STYLES: Record<string, string> = {
  standard: "bg-slate-800 text-slate-300",
  bottleneck: "bg-amber-400/15 text-amber-300",
  critical: "bg-red-500/15 text-red-300",
};

/** Lists the namespace's workstations. Owner/admin/production-supervisor. */
export function WorkstationsPage() {
  const { t } = useTranslation();
  const workstations = useWorkstationsStore((s) => s.workstations);
  const loading = useWorkstationsStore((s) => s.loading);
  const error = useWorkstationsStore((s) => s.error);
  const fetchWorkstations = useWorkstationsStore((s) => s.fetchWorkstations);
  const lines = useProductionLinesStore((s) => s.lines);
  const fetchLines = useProductionLinesStore((s) => s.fetchLines);

  useEffect(() => {
    void fetchWorkstations();
    void fetchLines();
  }, [fetchWorkstations, fetchLines]);

  const lineName = useMemo(() => {
    const map = new Map(lines.map((l) => [l.id, l.name]));
    return (id: string | null) => (id ? (map.get(id) ?? "—") : null);
  }, [lines]);

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

      {!loading && workstations.length > 0 && (
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
              {workstations.map((w) => {
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
