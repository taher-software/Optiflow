import { useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { ROUTES } from "../constants/routes";
import { useProductionLinesStore } from "../stores/useProductionLinesStore";
import { useUapsStore } from "../stores/useUapsStore";

/** Lists the namespace's production lines. Owner/admin/production-supervisor. */
export function ProductionLinesPage() {
  const { t } = useTranslation();
  const lines = useProductionLinesStore((s) => s.lines);
  const loading = useProductionLinesStore((s) => s.loading);
  const error = useProductionLinesStore((s) => s.error);
  const fetchLines = useProductionLinesStore((s) => s.fetchLines);
  const uaps = useUapsStore((s) => s.uaps);
  const fetchUaps = useUapsStore((s) => s.fetchUaps);

  useEffect(() => {
    void fetchLines();
    void fetchUaps();
  }, [fetchLines, fetchUaps]);

  const uapName = useMemo(() => {
    const map = new Map(uaps.map((u) => [u.id, u.name]));
    return (id: string) => map.get(id) ?? "—";
  }, [uaps]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">
          {t("lines.title")}
        </h1>
        <Link
          to={ROUTES.newLine}
          className="rounded-xl bg-teal-400 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300"
        >
          {t("lines.add")}
        </Link>
      </div>

      {loading && (
        <p className="mt-8 text-sm text-slate-400">{t("lines.loading")}</p>
      )}
      {error && <p className="mt-8 text-sm text-red-400">{error}</p>}
      {!loading && !error && lines.length === 0 && (
        <p className="mt-8 text-sm text-slate-400">{t("lines.empty")}</p>
      )}

      {!loading && lines.length > 0 && (
        <div className="mt-8 overflow-x-auto rounded-2xl border border-slate-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-900/60 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">{t("lines.table.name")}</th>
                <th className="px-4 py-3">{t("lines.table.zoneArea")}</th>
                <th className="px-4 py-3">{t("lines.table.description")}</th>
                <th className="px-4 py-3 text-right">
                  {t("lines.table.actions")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {lines.map((l) => (
                <tr key={l.id} className="hover:bg-slate-900/40">
                  <td className="px-4 py-3 font-medium text-white">{l.name}</td>
                  <td className="px-4 py-3 text-teal-300">
                    {uapName(l.uap_id)}
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {l.description || "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      to={`${ROUTES.lines}/${l.id}`}
                      className="text-sm font-medium text-teal-400 hover:text-teal-300"
                    >
                      {t("lines.edit")}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default ProductionLinesPage;
