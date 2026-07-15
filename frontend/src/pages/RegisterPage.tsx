import { useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { BrandLogo } from "../components/BrandLogo";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { TextField } from "../components/TextField";
import {
  EMPTY_COMPANY,
  EMPTY_OWNER,
  type CompanyForm,
  type OwnerForm,
} from "../constants/registration";
import { ROUTES } from "../constants/routes";
import { useRegistrationStore } from "../stores/useRegistrationStore";

/** Two-step account registration (company → owner). Creates a new namespace. */
export function RegisterPage() {
  const { t } = useTranslation();
  const register = useRegistrationStore((s) => s.register);
  const resend = useRegistrationStore((s) => s.resend);

  const [step, setStep] = useState<1 | 2>(1);
  const [company, setCompany] = useState<CompanyForm>(EMPTY_COMPANY);
  const [owner, setOwner] = useState<OwnerForm>(EMPTY_OWNER);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [resent, setResent] = useState(false);
  const [resendError, setResendError] = useState<string | null>(null);

  const setC = (k: keyof CompanyForm) => (v: string) =>
    setCompany((c) => ({ ...c, [k]: v }));
  const setO = (k: keyof OwnerForm) => (v: string) =>
    setOwner((o) => ({ ...o, [k]: v }));

  const companyValid = Object.values(company).every((v) => v.trim() !== "");
  const ownerValid =
    owner.firstname.trim() !== "" &&
    owner.lastname.trim() !== "" &&
    owner.email.trim() !== "";

  const goToStep2 = (e: FormEvent) => {
    e.preventDefault();
    if (companyValid) setStep(2);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ownerValid) return;
    setSubmitting(true);
    setError(null);
    const res = await register({ company, owner });
    setSubmitting(false);
    if (res.ok) setDone(true);
    else setError(res.error ?? t("register.errors.createFailed"));
  };

  if (done) {
    return (
      <Shell>
        <h1 className="mt-8 text-center text-xl font-semibold text-white">
          {t("register.success.title")}
        </h1>
        <p className="mt-3 text-center text-sm text-slate-400">
          {t("register.success.message", { email: owner.email })}
        </p>
        <div className="mt-6 text-center text-sm text-slate-400">
          {resent ? (
            <span className="text-teal-400">
              {t("register.success.resent")}
            </span>
          ) : (
            <>
              <button
                type="button"
                onClick={async () => {
                  setResendError(null);
                  const r = await resend(owner.email);
                  if (r.ok) setResent(true);
                  else
                    setResendError(r.error ?? t("register.errors.sendFailed"));
                }}
                className="font-medium text-teal-400 hover:text-teal-300"
              >
                {t("register.success.resendPrompt")}
              </button>
              {resendError && (
                <p className="mt-2 text-red-400">{resendError}</p>
              )}
            </>
          )}
        </div>
        <p className="mt-8 text-center text-sm text-slate-400">
          <Link to={ROUTES.login} className="text-teal-400 hover:text-teal-300">
            {t("confirm.backToLogin")}
          </Link>
        </p>
      </Shell>
    );
  }

  return (
    <Shell>
      <h1 className="mt-8 text-center text-xl font-semibold text-white">
        {t("register.title")}
      </h1>
      <p className="mt-1 text-center text-sm text-slate-400">
        {t("register.stepLabel", {
          step,
          part:
            step === 1 ? t("register.partCompany") : t("register.partOwner"),
        })}
      </p>

      {step === 1 ? (
        <form onSubmit={goToStep2} className="mt-8 space-y-4">
          <TextField
            id="company_name"
            label={t("register.fields.companyName")}
            required
            value={company.company_name}
            onChange={setC("company_name")}
          />
          <TextField
            id="adress"
            label={t("register.fields.address")}
            required
            value={company.adress}
            onChange={setC("adress")}
          />
          <div className="grid grid-cols-2 gap-4">
            <TextField
              id="code_postal"
              label={t("register.fields.postalCode")}
              required
              value={company.code_postal}
              onChange={setC("code_postal")}
            />
            <TextField
              id="city"
              label={t("register.fields.city")}
              required
              value={company.city}
              onChange={setC("city")}
            />
          </div>
          <TextField
            id="country"
            label={t("register.fields.country")}
            required
            value={company.country}
            onChange={setC("country")}
          />
          <TextField
            id="phone_number"
            label={t("register.fields.phone")}
            type="tel"
            required
            value={company.phone_number}
            onChange={setC("phone_number")}
          />
          <TextField
            id="tax_identification_number"
            label={t("register.fields.taxId")}
            required
            value={company.tax_identification_number}
            onChange={setC("tax_identification_number")}
          />
          <button
            type="submit"
            disabled={!companyValid}
            className={buttonClass}
          >
            {t("register.next")}
          </button>
        </form>
      ) : (
        <form onSubmit={submit} className="mt-8 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <TextField
              id="firstname"
              label={t("register.fields.firstName")}
              required
              value={owner.firstname}
              onChange={setO("firstname")}
              autoComplete="given-name"
            />
            <TextField
              id="lastname"
              label={t("register.fields.lastName")}
              required
              value={owner.lastname}
              onChange={setO("lastname")}
              autoComplete="family-name"
            />
          </div>
          <TextField
            id="email"
            label={t("register.fields.email")}
            type="email"
            required
            value={owner.email}
            onChange={setO("email")}
            autoComplete="email"
            placeholder="vous@entreprise.com"
          />
          <TextField
            id="avatar_url"
            label={t("register.fields.avatar")}
            value={owner.avatar_url ?? ""}
            onChange={setO("avatar_url")}
            placeholder="https://…"
          />

          {error && <p className="text-sm text-red-400">{error}</p>}

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setStep(1)}
              className={secondaryButtonClass}
            >
              {t("register.back")}
            </button>
            <button
              type="submit"
              disabled={submitting || !ownerValid}
              className={buttonClass}
            >
              {submitting ? t("register.submitting") : t("register.submit")}
            </button>
          </div>
        </form>
      )}

      <p className="mt-8 text-center text-sm text-slate-400">
        {t("register.alreadyAccount")}{" "}
        <Link to={ROUTES.login} className="text-teal-400 hover:text-teal-300">
          {t("register.signIn")}
        </Link>
      </p>
    </Shell>
  );
}

const buttonClass =
  "w-full rounded-xl bg-teal-400 px-4 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300 disabled:opacity-60";
const secondaryButtonClass =
  "rounded-xl border border-slate-700 px-4 py-3 text-sm font-medium text-slate-200 transition-colors hover:border-slate-500 hover:text-white";

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-screen items-center justify-center bg-slate-950 px-6 py-12">
      <div className="absolute right-4 top-4">
        <LanguageSwitcher />
      </div>
      <div className="w-full max-w-md">
        <div className="flex justify-center">
          <BrandLogo />
        </div>
        {children}
      </div>
    </div>
  );
}

export default RegisterPage;
