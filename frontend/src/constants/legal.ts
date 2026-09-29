/**
 * Publisher identity, contact details, and the section lists of the two legal
 * documents. The company facts are deliberately NOT translated: a trade name, a
 * registered office and a tax identification number are legal identifiers and
 * must read identically in every language.
 */
export const LEGAL = {
  /** Trade name of the publisher. */
  tradeName: "azibodin",
  /** Legal form of the entity. */
  legalForm: "SUARL",
  /** Registered office, as filed. */
  registeredOffice:
    "Compile Business Centre, Cité Ettaamir, Cité Boukhzar, Sousse Médina, Sousse 4000, Tunisie",
  /** Tax identification number ("matricule fiscal"). */
  taxId: "1941754F",
  /** Contact address for support, privacy requests and legal notices. */
  contactEmail: "azibodin@azibodin.tn",
  /** Contact phone, formatted for display. */
  contactPhone: "+216 92 152 219",
  /** Same number in E.164, for the `tel:` href. */
  contactPhoneE164: "+21692152219",
} as const;

/**
 * Ordered section ids of the privacy policy. Each id resolves to
 * `legal.privacy.sections.<id>.{heading,body}` in the locale files.
 */
export const PRIVACY_SECTIONS = [
  "controller",
  "data",
  "purposes",
  "basis",
  "retention",
  "sharing",
  "security",
  "rights",
  "cookies",
  "children",
  "changes",
] as const;

/**
 * Ordered section ids of the terms of sale. Each id resolves to
 * `legal.terms.sections.<id>.{heading,body}` in the locale files.
 */
export const TERMS_SECTIONS = [
  "purpose",
  "service",
  "account",
  "subscription",
  "pricing",
  "payment",
  "duration",
  "obligations",
  "availability",
  "liability",
  "intellectualProperty",
  "dataProtection",
  "law",
] as const;

export type PrivacySection = (typeof PRIVACY_SECTIONS)[number];
export type TermsSection = (typeof TERMS_SECTIONS)[number];
