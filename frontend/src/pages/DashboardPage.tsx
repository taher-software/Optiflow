import { useTranslation } from "react-i18next";

import { useAuthStore } from "../stores/useAuthStore";

/**
 * Operations app landing (post-login). The real dashboard (tickets, KPIs, …)
 * will be built here.
 */
export function DashboardPage() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);

  return (
    <div className="mx-auto max-w-6xl px-6 py-16">
      <h1 className="text-2xl font-bold tracking-tight">
        {t("dashboard.greeting")}
        {user ? `, ${user.first_name}` : ""}.
      </h1>
      <p className="mt-2 text-sm text-slate-400">{t("dashboard.subtitle")}</p>
    </div>
  );
}

export default DashboardPage;
