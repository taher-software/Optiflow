import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, useNavigate } from "react-router-dom";

import { ROUTES } from "../constants/routes";
import { useAuthStore } from "../stores/useAuthStore";
import { canSeeSubscription } from "../utils/subscriptionAccess";
import { BrandLogo } from "./BrandLogo";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  show: boolean;
}

function icon(path: string) {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-5 w-5"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={path} />
    </svg>
  );
}

/** Left navigation sidebar for the protected app area. Distinguished panel
 * color, active-route highlighting, language switcher + sign out at the base. */
export function Sidebar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const signOut = useAuthStore((s) => s.signOut);
  const warning = useAuthStore((s) => s.warning);
  const blocked = useAuthStore((s) => s.blocked);
  // Blocked subscription: the subscription page is the only reachable page,
  // so every other entry is hidden (sign-out + language stay available).
  const locked = blocked === true;

  const canManageUsers = user?.role === "owner" || user?.role === "admin";
  const canManageUaps =
    canManageUsers || user?.role === "production supervisor";
  const canManageSettings = canManageUaps || user?.role === "manager";
  // Same role set as the endpoint's `_gantt_scope` (owner/admin/manager/
  // production supervisor): showing the entry to anyone else would only lead
  // to a 403.
  const canReadGantt = canManageSettings;

  const items: NavItem[] = [
    {
      to: ROUTES.app,
      label: t("nav.dashboard"),
      icon: icon("M3 12l9-9 9 9M5 10v10h14V10"),
      show: true,
    },
    {
      to: ROUTES.downTimes,
      label: t("nav.downTimes"),
      icon: icon("M4 6h10M4 12h6M4 18h13M3 3v18"),
      show: canReadGantt,
    },
    {
      to: ROUTES.users,
      label: t("nav.users"),
      icon: icon(
        "M17 20v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 8a4 4 0 1 0 0-.001M23 20v-2a4 4 0 0 0-3-3.87",
      ),
      show: canManageUsers,
    },
    {
      to: ROUTES.uaps,
      label: t("nav.uaps"),
      icon: icon("M3 21V7l6-4 6 4v14M3 21h18M15 21V11l6 4v6"),
      show: canManageUaps,
    },
    {
      to: ROUTES.lines,
      label: t("nav.lines"),
      icon: icon("M4 7h16M4 12h16M4 17h16M7 4v16"),
      show: canManageUaps,
    },
    {
      to: ROUTES.stations,
      label: t("nav.stations"),
      icon: icon("M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"),
      show: canManageUaps,
    },
    {
      to: ROUTES.settings,
      label: t("nav.settings"),
      icon: icon(
        "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z",
      ),
      show: canManageSettings,
    },
    {
      to: ROUTES.stats,
      label: t("nav.stats"),
      icon: icon("M3 21h18M6 17V9m6 8V5m6 12v-6"),
      show: true,
    },
    {
      to: ROUTES.subscription,
      label: t("nav.subscription"),
      icon: icon("M3 7h18v10H3zM3 11h18M7 15h3"),
      show: canSeeSubscription({ warning, blocked }),
    },
  ];

  const onSignOut = () => {
    signOut();
    navigate(ROUTES.prospect);
  };

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-slate-800 bg-slate-900">
      <div className="px-5 py-6">
        <BrandLogo />
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {items
          .filter((i) => i.show && (!locked || i.to === ROUTES.subscription))
          .map((i) => (
            <NavLink
              key={i.to}
              to={i.to}
              end={i.to === ROUTES.app}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-teal-400/15 text-teal-300 ring-1 ring-inset ring-teal-400/30"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white"
                }`
              }
            >
              {i.icon}
              {i.label}
            </NavLink>
          ))}
      </nav>

      <div className="space-y-4 border-t border-slate-800 px-5 py-5">
        <LanguageSwitcher />
        <button
          type="button"
          onClick={onSignOut}
          className="flex w-full items-center justify-center rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition-colors hover:border-slate-500 hover:text-white"
        >
          {t("dashboard.signOut")}
        </button>
      </div>
    </aside>
  );
}
