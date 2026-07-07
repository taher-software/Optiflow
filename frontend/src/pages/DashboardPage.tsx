import { useNavigate } from "react-router-dom";

import { BrandLogo } from "../components/BrandLogo";
import { ROUTES } from "../constants/routes";
import { useAuthStore } from "../stores/useAuthStore";

/**
 * Placeholder for the operations app landing (post-login).
 * The real dashboard (tickets, KPIs, …) will be built here.
 */
export function DashboardPage() {
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
        <button
          type="button"
          onClick={onSignOut}
          className="rounded-xl border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:border-slate-500 hover:text-white"
        >
          Se déconnecter
        </button>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-16">
        <h1 className="text-2xl font-bold tracking-tight">
          Bienvenue{user ? `, ${user.displayName}` : ""}.
        </h1>
        <p className="mt-2 text-sm text-slate-400">
          Votre tableau de bord de production arrive bientôt — tickets d'arrêt,
          intervenants et KPIs de l'usine.
        </p>
      </main>
    </div>
  );
}

export default DashboardPage;
