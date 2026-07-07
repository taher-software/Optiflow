import { Navigate, Outlet } from "react-router-dom";

import { ROUTES } from "../constants/routes";
import { SplashPage } from "../pages/SplashPage";
import { useAuthStore } from "../stores/useAuthStore";

/**
 * Guards the protected /app area.
 * - while the session is resolving  -> show the splash (bootstrapping)
 * - if not authenticated            -> redirect to /login
 * - otherwise                       -> render the nested route
 */
export function ProtectedRoute() {
  const status = useAuthStore((s) => s.status);

  if (status === "idle" || status === "loading") {
    return <SplashPage />;
  }

  if (status !== "authenticated") {
    return <Navigate to={ROUTES.login} replace />;
  }

  return <Outlet />;
}
