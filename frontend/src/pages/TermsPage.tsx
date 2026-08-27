import { useTranslation } from "react-i18next";

import { LegalDocument } from "../components/LegalDocument";
import { LEGAL, TERMS_SECTIONS } from "../constants/legal";

/** Terms of sale (Conditions générales de vente). Public, static. */
export function TermsPage() {
  const { t } = useTranslation();

  const sections = TERMS_SECTIONS.map((id) => ({
    id,
    heading: t(`legal.terms.sections.${id}.heading`),
    body: t(`legal.terms.sections.${id}.body`, LEGAL),
  }));

  return (
    <LegalDocument
      title={t("legal.terms.title")}
      updated={t("legal.terms.updated")}
      sections={sections}
    />
  );
}

export default TermsPage;
