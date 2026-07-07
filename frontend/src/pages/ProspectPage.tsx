import { Link } from "react-router-dom";

import { BrandLogo } from "../components/BrandLogo";
import { CtaButton } from "../components/CtaButton";
import { FeatureCard } from "../components/FeatureCard";
import { CALENDLY_URL, FEATURES, HERO } from "../constants/features";
import { ROUTES } from "../constants/routes";

/**
 * Public prospect / landing page. Marketing surface that highlights the
 * core OptiFlow value propositions. Static — no data fetching.
 */
export function ProspectPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Nav */}
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <BrandLogo />
        <div className="flex items-center gap-4">
          <Link
            to={ROUTES.login}
            className="text-sm font-medium text-slate-300 transition-colors hover:text-white"
          >
            Se connecter
          </Link>
          <CtaButton variant="ghost" href={CALENDLY_URL} external>
            {HERO.primaryCta}
          </CtaButton>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-3xl px-6 pb-16 pt-16 text-center sm:pt-24">
        <span className="inline-block rounded-full border border-slate-800 bg-slate-900/60 px-4 py-1 text-xs font-medium text-teal-400">
          La gestion des arrêts pour les usines modernes
        </span>
        <h1 className="mt-6 text-4xl font-bold tracking-tight sm:text-5xl">
          {HERO.headline}
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-base leading-relaxed text-slate-400">
          {HERO.subhead}
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <CtaButton variant="primary" href={CALENDLY_URL} external>
            {HERO.primaryCta}
          </CtaButton>
          <CtaButton variant="ghost">{HERO.secondaryCta}</CtaButton>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-6 pb-24">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((feature) => (
            <FeatureCard key={feature.icon} feature={feature} />
          ))}
        </div>
      </section>

      {/* Closing CTA */}
      <section className="border-t border-slate-900 bg-slate-900/30">
        <div className="mx-auto flex max-w-3xl flex-col items-center px-6 py-16 text-center">
          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
            Transformez les arrêts en temps de production.
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-slate-400">
            Découvrez comment OptiFlow maintient votre production en flux — de
            la première alerte d'arrêt à une cause racine que vous n'aurez plus
            jamais à affronter.
          </p>
          <div className="mt-7">
            <CtaButton variant="primary" href={CALENDLY_URL} external>
              {HERO.primaryCta}
            </CtaButton>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="mx-auto max-w-6xl px-6 py-8 text-center text-xs text-slate-600">
        © {new Date().getFullYear()} OptiFlow. Gardez votre production en flux.
      </footer>
    </div>
  );
}

export default ProspectPage;
