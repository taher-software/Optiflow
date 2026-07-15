import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { BrandLogo } from "../components/BrandLogo";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { Spinner } from "../components/Spinner";
import { TextField } from "../components/TextField";
import { ROUTES } from "../constants/routes";
import { useRegistrationStore } from "../stores/useRegistrationStore";

type Phase = "confirming" | "success" | "error";

/** Confirms an account from the emailed ?token=, with a resend option on failure. */
export function ConfirmAccountPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get("token");
  const confirm = useRegistrationStore((s) => s.confirm);
  const resend = useRegistrationStore((s) => s.resend);

  const [phase, setPhase] = useState<Phase>("confirming");
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // guard StrictMode double-invoke
    started.current = true;
    if (!token) {
      setPhase("error");
      setError(t("confirm.error.invalidLink"));
      return;
    }
    void confirm(token).then((res) => {
      if (res.ok) {
        setPhase("success");
      } else {
        setPhase("error");
        setError(res.error ?? t("confirm.error.default"));
      }
    });
  }, [token, confirm, t]);

  // Resend sub-flow (shown on failure / expiry).
  const [email, setEmail] = useState("");
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);
  const [resendError, setResendError] = useState<string | null>(null);

  const onResend = async (e: FormEvent) => {
    e.preventDefault();
    if (email.trim() === "") return;
    setResending(true);
    setResendError(null);
    const res = await resend(email);
    setResending(false);
    if (res.ok) setResent(true);
    else setResendError(res.error ?? t("confirm.resend.failed"));
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-slate-950 px-6 py-12">
      <div className="absolute right-4 top-4">
        <LanguageSwitcher />
      </div>
      <div className="w-full max-w-sm text-center">
        <div className="flex justify-center">
          <BrandLogo />
        </div>

        {phase === "confirming" && (
          <div className="mt-10 flex flex-col items-center">
            <Spinner />
            <p className="mt-4 text-sm text-slate-400">
              {t("confirm.confirming")}
            </p>
          </div>
        )}

        {phase === "success" && (
          <>
            <h1 className="mt-8 text-xl font-semibold text-white">
              {t("confirm.success.title")}
            </h1>
            <p className="mt-3 text-sm text-slate-400">
              {t("confirm.success.message")}
            </p>
            <Link
              to={ROUTES.login}
              className="mt-8 inline-block rounded-xl bg-teal-400 px-6 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300"
            >
              {t("confirm.success.signIn")}
            </Link>
          </>
        )}

        {phase === "error" && (
          <>
            <h1 className="mt-8 text-xl font-semibold text-white">
              {t("confirm.error.title")}
            </h1>
            <p className="mt-3 text-sm text-red-400">{error}</p>

            {resent ? (
              <p className="mt-8 text-sm text-teal-400">
                {t("confirm.resend.sent")}
              </p>
            ) : (
              <form onSubmit={onResend} className="mt-8 space-y-3 text-left">
                <p className="text-sm text-slate-400">
                  {t("confirm.resend.prompt")}
                </p>
                <TextField
                  id="resend-email"
                  label={t("register.fields.email")}
                  type="email"
                  required
                  value={email}
                  onChange={setEmail}
                  autoComplete="email"
                  placeholder="vous@entreprise.com"
                />
                <button
                  type="submit"
                  disabled={resending || email.trim() === ""}
                  className="w-full rounded-xl bg-teal-400 px-4 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300 disabled:opacity-60"
                >
                  {resending
                    ? t("confirm.resend.submitting")
                    : t("confirm.resend.submit")}
                </button>
                {resendError && (
                  <p className="text-sm text-red-400">{resendError}</p>
                )}
              </form>
            )}

            <p className="mt-8 text-sm text-slate-400">
              <Link
                to={ROUTES.login}
                className="text-teal-400 hover:text-teal-300"
              >
                {t("confirm.backToLogin")}
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}

export default ConfirmAccountPage;
