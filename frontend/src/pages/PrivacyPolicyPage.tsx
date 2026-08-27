import { useTranslation } from "react-i18next";

import { LegalDocument } from "../components/LegalDocument";
import { LEGAL, PRIVACY_SECTIONS } from "../constants/legal";

/** Privacy policy. Public, static — no data fetching. */
export function PrivacyPolicyPage() {
  const { t } = useTranslation();

  const sections = PRIVACY_SECTIONS.map((id) => ({
    id,
    heading: t(`legal.privacy.sections.${id}.heading`),
    body: t(`legal.privacy.sections.${id}.body`, LEGAL),
  }));

  return (
    <LegalDocument
      title={t("legal.privacy.title")}
      updated={t("legal.privacy.updated")}
      sections={sections}
    />
  );
}

export default PrivacyPolicyPage;
