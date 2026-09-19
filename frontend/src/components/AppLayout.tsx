import { useTranslation } from "react-i18next";
import { Outlet } from "react-router-dom";

import { ROUTES } from "../constants/routes";
import { useAuthStore } from "../stores/useAuthStore";
import { Sidebar } from "./Sidebar";
import { SubscriptionWarningBanner } from "./SubscriptionWarningBanner";

/** Shell for the protected app area: fixed left sidebar + scrollable content,
 * topped by the renewal banner while the subscription is in its grace period. */
export function AppLayout() {
  const { t } = useTranslation();
  const warning = useAuthStore((s) => s.warning);

  return (
    <div className="flex min-h-screen bg-slate-950 text-white">
      <Sidebar />
      <main className="flex-1 overflow-x-hidden">
        {warning === true && (
          <SubscriptionWarningBanner
            message={t("subscription.banner.message")}
            linkLabel={t("subscription.banner.renew")}
            to={ROUTES.subscription}
          />
        )}
        <Outlet />
      </main>
    </div>
  );
}

export default AppLayout;
