import { BrowserRouter, Routes, Route } from "react-router-dom";

import { AppLayout } from "../components/AppLayout";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { ROUTES } from "../constants/routes";
import ConfirmAccountPage from "../pages/ConfirmAccountPage";
import DashboardPage from "../pages/DashboardPage";
import DownTimesPage from "../pages/DownTimesPage";
import LoginPage from "../pages/LoginPage";
import ProspectPage from "../pages/ProspectPage";
import RegisterPage from "../pages/RegisterPage";
import SettingsPage from "../pages/SettingsPage";
import StatsPage from "../pages/StatsPage";
import PrivacyPolicyPage from "../pages/PrivacyPolicyPage";
import ProductionLineFormPage from "../pages/ProductionLineFormPage";
import ProductionLinesPage from "../pages/ProductionLinesPage";
import TermsPage from "../pages/TermsPage";
import UapFormPage from "../pages/UapFormPage";
import UapsPage from "../pages/UapsPage";
import UserFormPage from "../pages/UserFormPage";
import UsersPage from "../pages/UsersPage";
import WorkstationFormPage from "../pages/WorkstationFormPage";
import WorkstationsPage from "../pages/WorkstationsPage";

/**
 * App routes:
 *   /       public prospect page
 *   /login  sign in
 *   /app    protected operations area (guarded -> splash -> dashboard)
 *   /privacy, /terms  public legal documents
 */
export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path={ROUTES.prospect} element={<ProspectPage />} />
        <Route path={ROUTES.login} element={<LoginPage />} />
        <Route path={ROUTES.register} element={<RegisterPage />} />
        <Route path={ROUTES.confirmAccount} element={<ConfirmAccountPage />} />
        <Route path={ROUTES.privacy} element={<PrivacyPolicyPage />} />
        <Route path={ROUTES.terms} element={<TermsPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path={ROUTES.app} element={<DashboardPage />} />
            <Route path={ROUTES.downTimes} element={<DownTimesPage />} />
            <Route path={ROUTES.users} element={<UsersPage />} />
            <Route path={ROUTES.newUser} element={<UserFormPage />} />
            <Route path={`${ROUTES.users}/:id`} element={<UserFormPage />} />
            <Route path={ROUTES.uaps} element={<UapsPage />} />
            <Route path={ROUTES.newUap} element={<UapFormPage />} />
            <Route path={`${ROUTES.uaps}/:id`} element={<UapFormPage />} />
            <Route path={ROUTES.lines} element={<ProductionLinesPage />} />
            <Route path={ROUTES.newLine} element={<ProductionLineFormPage />} />
            <Route
              path={`${ROUTES.lines}/:id`}
              element={<ProductionLineFormPage />}
            />
            <Route path={ROUTES.stations} element={<WorkstationsPage />} />
            <Route path={ROUTES.newStation} element={<WorkstationFormPage />} />
            <Route
              path={`${ROUTES.stations}/:id`}
              element={<WorkstationFormPage />}
            />
            <Route path={ROUTES.settings} element={<SettingsPage />} />
            <Route path={ROUTES.stats} element={<StatsPage />} />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default AppRouter;
