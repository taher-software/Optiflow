import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { BrandLogo } from "../components/BrandLogo";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { PasswordField } from "../components/PasswordField";
import { ROUTES } from "../constants/routes";
import { useAuthStore } from "../stores/useAuthStore";

/** Sign-in page. Entry point into the protected operations app. */
export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const signIn = useAuthStore((s) => s.signIn);
  const status = useAuthStore((s) => s.status);
  const error = useAuthStore((s) => s.error);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const loading = status === "loading";

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    await signIn(email, password);
    if (useAuthStore.getState().status === "authenticated") {
      navigate(ROUTES.app);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-slate-950 px-6">
      <div className="absolute right-4 top-4">
        <LanguageSwitcher />
      </div>
      <div className="w-full max-w-sm">
        <div className="flex justify-center">
          <BrandLogo />
        </div>
        <h1 className="mt-8 text-center text-xl font-semibold text-white">
          {t("login.title")}
        </h1>
        <p className="mt-1 text-center text-sm text-slate-400">
          {t("login.subtitle")}
        </p>

        <form onSubmit={onSubmit} className="mt-8 space-y-4">
          <div>
            <label
              htmlFor="email"
              className="mb-1 block text-sm font-medium text-slate-300"
            >
              {t("login.emailLabel")}
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white placeholder-slate-500 focus:border-teal-400 focus:outline-none"
              placeholder="vous@usine.com"
            />
          </div>

          <PasswordField
            id="password"
            label={t("login.passwordLabel")}
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
            placeholder="••••••••"
          />

          {error && <p className="text-sm text-red-400">{t(error)}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-teal-400 px-4 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300 disabled:opacity-60"
          >
            {loading ? t("login.submitting") : t("login.submit")}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-400">
          {t("login.noAccount")}{" "}
          <Link
            to={ROUTES.register}
            className="font-medium text-teal-400 hover:text-teal-300"
          >
            {t("login.createAccount")}
          </Link>
        </p>
      </div>
    </div>
  );
}

export default LoginPage;
