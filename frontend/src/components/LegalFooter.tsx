import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { LEGAL } from "../constants/legal";
import { ROUTES } from "../constants/routes";

/** Publisher identity, contact details and links to the legal documents. */
export function LegalFooter() {
  const { t } = useTranslation();

  return (
    <footer className="w-full text-xs leading-relaxed text-slate-500">
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-2 px-6 text-center">
        <p>
          <span className="font-medium text-slate-400">
            {LEGAL.tradeName} {LEGAL.legalForm}
          </span>
          {" — "}
          {LEGAL.registeredOffice}
        </p>
        <p>
          {t("legal.taxId")} {LEGAL.taxId}
        </p>
        <p className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
          <a
            href={`mailto:${LEGAL.contactEmail}`}
            className="transition-colors hover:text-teal-400"
          >
            {LEGAL.contactEmail}
          </a>
          <span aria-hidden="true">·</span>
          <a
            href={`tel:${LEGAL.contactPhoneE164}`}
            className="transition-colors hover:text-teal-400"
          >
            {LEGAL.contactPhone}
          </a>
        </p>
        <p className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
          <Link
            to={ROUTES.privacy}
            className="transition-colors hover:text-teal-400"
          >
            {t("legal.privacy.title")}
          </Link>
          <span aria-hidden="true">·</span>
          <Link
            to={ROUTES.terms}
            className="transition-colors hover:text-teal-400"
          >
            {t("legal.terms.title")}
          </Link>
        </p>
      </div>
    </footer>
  );
}

export default LegalFooter;
