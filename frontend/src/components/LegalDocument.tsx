import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { BrandLogo } from "./BrandLogo";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { LegalFooter } from "./LegalFooter";
import { ROUTES } from "../constants/routes";

interface LegalSection {
  id: string;
  heading: string;
  body: string;
}

interface LegalDocumentProps {
  title: string;
  /** Date the document was last revised, already formatted for display. */
  updated: string;
  sections: LegalSection[];
}

/**
 * Page chrome + typography for a legal document (privacy policy, terms of sale).
 * Presentational: the caller resolves the translated sections and passes them in.
 */
export function LegalDocument({
  title,
  updated,
  sections,
}: LegalDocumentProps) {
  const { t } = useTranslation();

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <header className="mx-auto flex max-w-3xl items-center justify-between px-6 py-6">
        <Link to={ROUTES.prospect} aria-label={t("legal.backToHome")}>
          <BrandLogo />
        </Link>
        <LanguageSwitcher />
      </header>

      <main className="mx-auto max-w-3xl px-6 pb-16">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          {title}
        </h1>
        <p className="mt-3 text-xs text-slate-500">
          {t("legal.lastUpdated")} {updated}
        </p>

        {sections.map((section) => (
          <section key={section.id} className="mt-10">
            <h2 className="text-lg font-semibold text-teal-400">
              {section.heading}
            </h2>
            <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-slate-300">
              {section.body}
            </p>
          </section>
        ))}
      </main>

      <div className="border-t border-slate-900 py-8">
        <LegalFooter />
      </div>
    </div>
  );
}

export default LegalDocument;
