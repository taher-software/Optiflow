import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { ROUTES } from "../constants/routes";
import { useAuthStore } from "../stores/useAuthStore";
import { BrandLogo } from "./BrandLogo";
import { LanguageSwitcher } from "./LanguageSwitcher";

/** Shared header for the protected app area. */
export function AppHeader() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const signOut = useAuthStore((s) => s.signOut);

  const canManageUsers = user?.role === "owner" || user?.role === "admin";
  const canManageUaps =
    canManageUsers || user?.role === "production supervisor";

  const onSignOut = () => {
    signOut();
    navigate(ROUTES.prospect);
  };

  return (
    <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
      <div className="flex items-center gap-6">
        <BrandLogo />
        <nav className="flex items-center gap-4 text-sm">
          <Link
            to={ROUTES.app}
            className="font-medium text-slate-300 transition-colors hover:text-white"
          >
            {t("nav.dashboard")}
          </Link>
          {canManageUaps && (
            <Link
              to={ROUTES.uaps}
              className="font-medium text-slate-300 transition-colors hover:text-white"
            >
              {t("nav.uaps")}
            </Link>
          )}
          {canManageUsers && (
            <Link
              to={ROUTES.users}
              className="font-medium text-slate-300 transition-colors hover:text-white"
            >
              {t("nav.users")}
            </Link>
          )}
        </nav>
      </div>
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
  );
}
