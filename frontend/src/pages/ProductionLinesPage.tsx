import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { FiltersBar } from "../components/FiltersBar";
import { SelectField } from "../components/SelectField";
import { TextField } from "../components/TextField";
import { ROUTES } from "../constants/routes";
import { useProductionLinesStore } from "../stores/useProductionLinesStore";
import { useUapsStore } from "../stores/useUapsStore";
import { matchesQuery } from "../utils/textSearch";

/** Zone-area-filter value selecting the lines that belong to no zone area. */
const INDEPENDENT = "__independent__";

/** Lists the namespace's production lines. Owner/admin/production-supervisor. */
export function ProductionLinesPage() {
  const { t } = useTranslation();
  const lines = useProductionLinesStore((s) => s.lines);
  const loading = useProductionLinesStore((s) => s.loading);
  const error = useProductionLinesStore((s) => s.error);
  const fetchLines = useProductionLinesStore((s) => s.fetchLines);
  const uaps = useUapsStore((s) => s.uaps);
  const fetchUaps = useUapsStore((s) => s.fetchUaps);
  const [search, setSearch] = useState("");
  const [uapId, setUapId] = useState("");

  useEffect(() => {
    void fetchLines();
    void fetchUaps();
  }, [fetchLines, fetchUaps]);

  const uapName = useMemo(() => {
    const map = new Map(uaps.map((u) => [u.id, u.name]));
    // `null` marks an intentionally independent line; "—" marks a dangling
    // uap_id whose zone area no longer exists. They are not the same state.
    return (id: string | null) => (id === null ? null : (map.get(id) ?? "—"));
  }, [uaps]);

  const uapOptions = useMemo(
    () => [
      ...uaps.map((u) => ({ value: u.id, label: u.name })),
      { value: INDEPENDENT, label: t("lines.independent") },
    ],
    [uaps, t],
  );

  const visibleLines = useMemo(
    () =>
      lines.filter((l) => {
        if (!matchesQuery(search, l.name)) return false;
        if (uapId === "") return true;
        if (uapId === INDEPENDENT) return l.uap_id === null;
        return l.uap_id === uapId;
      }),
    [lines, search, uapId],
  );

  const hasLines = !loading && !error && lines.length > 0;

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

      {hasLines && (
        <FiltersBar>
          <TextField
            id="lines-search"
            label={t("lines.filters.search")}
            value={search}
            onChange={setSearch}
            placeholder={t("lines.filters.searchPlaceholder")}
          />
          <SelectField
            id="lines-uap"
            label={t("lines.filters.zoneArea")}
            value={uapId}
            onChange={setUapId}
            options={uapOptions}
            placeholder={t("lines.filters.allZoneAreas")}
          />
        </FiltersBar>
      )}

      {hasLines && visibleLines.length === 0 && (
        <p className="mt-8 text-sm text-slate-400">{t("lines.noResults")}</p>
      )}

      {hasLines && visibleLines.length > 0 && (
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
              {visibleLines.map((l) => {
                const uap = uapName(l.uap_id);
                return (
                  <tr key={l.id} className="hover:bg-slate-900/40">
                    <td className="px-4 py-3 font-medium text-white">
                      {l.name}
                    </td>
                    <td className="px-4 py-3 text-teal-300">
                      {uap ?? (
                        <span className="text-slate-500">
                          {t("lines.independent")}
                        </span>
                      )}
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
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default ProductionLinesPage;
