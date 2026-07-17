import { BrowserRouter, Routes, Route } from "react-router-dom";

import { ProtectedRoute } from "../components/ProtectedRoute";
import { ROUTES } from "../constants/routes";
import ConfirmAccountPage from "../pages/ConfirmAccountPage";
import DashboardPage from "../pages/DashboardPage";
import LoginPage from "../pages/LoginPage";
import ProspectPage from "../pages/ProspectPage";
import RegisterPage from "../pages/RegisterPage";
import UapFormPage from "../pages/UapFormPage";
import UapsPage from "../pages/UapsPage";
import UserFormPage from "../pages/UserFormPage";
import UsersPage from "../pages/UsersPage";

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
          <Route path={ROUTES.users} element={<UsersPage />} />
          <Route path={ROUTES.newUser} element={<UserFormPage />} />
          <Route path={`${ROUTES.users}/:id`} element={<UserFormPage />} />
          <Route path={ROUTES.uaps} element={<UapsPage />} />
          <Route path={ROUTES.newUap} element={<UapFormPage />} />
          <Route path={`${ROUTES.uaps}/:id`} element={<UapFormPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default AppRouter;
