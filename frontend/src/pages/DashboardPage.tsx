import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { BrandLogo } from "../components/BrandLogo";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { ROUTES } from "../constants/routes";
import { useAuthStore } from "../stores/useAuthStore";

/**
 * Placeholder for the operations app landing (post-login).
 * The real dashboard (tickets, KPIs, …) will be built here.
 */
export function DashboardPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const signOut = useAuthStore((s) => s.signOut);

  const onSignOut = () => {
    signOut();
    navigate(ROUTES.prospect);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <BrandLogo />
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          <button
            type="button"
            onClick={onSignOut}
            className="rounded-xl border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:border-slate-500 hover:text-white"
          >
            {t("dashboard.signOut")}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-16">
        <h1 className="text-2xl font-bold tracking-tight">
          {t("dashboard.greeting")}
          {user ? `, ${user.firstname}` : ""}.
        </h1>
        <p className="mt-2 text-sm text-slate-400">{t("dashboard.subtitle")}</p>
      </main>
    </div>
  );
}

export default DashboardPage;
