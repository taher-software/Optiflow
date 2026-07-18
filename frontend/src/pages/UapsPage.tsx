import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { ROUTES } from "../constants/routes";
import { memberCount } from "../constants/uaps";
import { useUapsStore } from "../stores/useUapsStore";

/** Lists the namespace's production areas (UAPs). Owner/admin/production-supervisor. */
export function UapsPage() {
  const { t } = useTranslation();
  const uaps = useUapsStore((s) => s.uaps);
  const loading = useUapsStore((s) => s.loading);
  const error = useUapsStore((s) => s.error);
  const fetchUaps = useUapsStore((s) => s.fetchUaps);

  useEffect(() => {
    void fetchUaps();
  }, [fetchUaps]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">{t("uaps.title")}</h1>
        <Link
          to={ROUTES.newUap}
          className="rounded-xl bg-teal-400 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300"
        >
          {t("uaps.add")}
        </Link>
      </div>

      {loading && (
        <p className="mt-8 text-sm text-slate-400">{t("uaps.loading")}</p>
      )}
      {error && <p className="mt-8 text-sm text-red-400">{error}</p>}
      {!loading && !error && uaps.length === 0 && (
        <p className="mt-8 text-sm text-slate-400">{t("uaps.empty")}</p>
      )}

      {!loading && uaps.length > 0 && (
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          {uaps.map((u) => (
            <Link
              key={u.id}
              to={`${ROUTES.uaps}/${u.id}`}
              className="rounded-2xl border border-slate-800 p-5 transition-colors hover:border-slate-600"
            >
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-lg font-semibold text-white">{u.name}</h2>
                <span className="shrink-0 rounded-lg bg-slate-800 px-2.5 py-1 text-xs font-medium text-teal-300">
                  {t("uaps.memberCount", { count: memberCount(u) })}
                </span>
              </div>
              {u.description && (
                <p className="mt-2 line-clamp-2 text-sm text-slate-400">
                  {u.description}
                </p>
              )}
              <span className="mt-4 inline-block text-sm font-medium text-teal-400">
                {t("uaps.edit")}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default UapsPage;
