import { Navigate, Outlet, useLocation } from "react-router-dom";

import { ROUTES } from "../constants/routes";
import { SplashPage } from "../pages/SplashPage";
import { useAuthStore } from "../stores/useAuthStore";
import { subscriptionRedirect } from "../utils/subscriptionAccess";

/**
 * Guards the protected /app area.
 * - while the session is resolving  -> show the splash (bootstrapping)
 * - if not authenticated            -> redirect to /login
 * - subscription blocked            -> every page but /app/subscription
 *                                      redirects there
 * - subscription page, not warned/blocked -> redirect to /app
 * - otherwise                       -> render the nested route
 */
export function ProtectedRoute() {
  const status = useAuthStore((s) => s.status);
  const warning = useAuthStore((s) => s.warning);
  const blocked = useAuthStore((s) => s.blocked);
  const { pathname } = useLocation();

  if (status === "idle" || status === "loading") {
    return <SplashPage />;
  }

  if (status !== "authenticated") {
    return <Navigate to={ROUTES.login} replace />;
  }

  const redirect = subscriptionRedirect(pathname, { warning, blocked });
  if (redirect !== null) {
    return <Navigate to={redirect} replace />;
  }

  return <Outlet />;
}
