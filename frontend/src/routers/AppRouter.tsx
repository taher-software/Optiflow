import { BrowserRouter, Routes, Route } from "react-router-dom";

import { ProtectedRoute } from "../components/ProtectedRoute";
import { ROUTES } from "../constants/routes";
import ConfirmAccountPage from "../pages/ConfirmAccountPage";
import DashboardPage from "../pages/DashboardPage";
import LoginPage from "../pages/LoginPage";
import ProspectPage from "../pages/ProspectPage";
import RegisterPage from "../pages/RegisterPage";

/**
 * App routes:
 *   /       public prospect page
 *   /login  sign in
 *   /app    protected operations area (guarded -> splash -> dashboard)
 */
export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path={ROUTES.prospect} element={<ProspectPage />} />
        <Route path={ROUTES.login} element={<LoginPage />} />
        <Route path={ROUTES.register} element={<RegisterPage />} />
        <Route path={ROUTES.confirmAccount} element={<ConfirmAccountPage />} />
        <Route element={<ProtectedRoute />}>
          <Route path={ROUTES.app} element={<DashboardPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default AppRouter;
