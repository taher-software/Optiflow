import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { BrandLogo } from "../components/BrandLogo";
import { CtaButton } from "../components/CtaButton";
import { FeatureCard } from "../components/FeatureCard";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { CALENDLY_URL, FEATURE_ICONS } from "../constants/features";
import { ROUTES } from "../constants/routes";

/**
 * Public prospect / landing page. Marketing surface that highlights the
 * core OptiFlow value propositions. Static — no data fetching.
 */
export function ProspectPage() {
  const { t } = useTranslation();

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Nav */}
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <BrandLogo />
        <div className="flex items-center gap-4">
          <LanguageSwitcher />
          <Link
            to={ROUTES.login}
            className="text-sm font-medium text-slate-300 transition-colors hover:text-white"
          >
            {t("login.title")}
          </Link>
          <CtaButton variant="ghost" href={CALENDLY_URL} external>
            {t("prospect.hero.primaryCta")}
          </CtaButton>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-3xl px-6 pb-16 pt-16 text-center sm:pt-24">
        <span className="inline-block rounded-full border border-slate-800 bg-slate-900/60 px-4 py-1 text-xs font-medium text-teal-400">
          {t("prospect.badge")}
        </span>
        <h1 className="mt-6 text-4xl font-bold tracking-tight sm:text-5xl">
          {t("prospect.hero.headline")}
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-base leading-relaxed text-slate-400">
          {t("prospect.hero.subhead")}
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <CtaButton variant="primary" href={CALENDLY_URL} external>
            {t("prospect.hero.primaryCta")}
          </CtaButton>
          <CtaButton variant="ghost">
            {t("prospect.hero.secondaryCta")}
          </CtaButton>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-6 pb-24">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURE_ICONS.map((icon) => (
            <FeatureCard
              key={icon}
              icon={icon}
              title={t(`prospect.features.${icon}.title`)}
              description={t(`prospect.features.${icon}.description`)}
            />
          ))}
        </div>
      </section>

      {/* Closing CTA */}
      <section className="border-t border-slate-900 bg-slate-900/30">
        <div className="mx-auto flex max-w-3xl flex-col items-center px-6 py-16 text-center">
          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
            {t("prospect.closing.title")}
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-slate-400">
            {t("prospect.closing.subtitle")}
          </p>
          <div className="mt-7">
            <CtaButton variant="primary" href={CALENDLY_URL} external>
              {t("prospect.hero.primaryCta")}
            </CtaButton>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="mx-auto max-w-6xl px-6 py-8 text-center text-xs text-slate-600">
        {t("prospect.footer", { year: new Date().getFullYear() })}
      </footer>
    </div>
  );
}

export default ProspectPage;
