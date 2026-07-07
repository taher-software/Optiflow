export type FeatureIconName =
  "automate" | "empower" | "transparent" | "rootcause";

export interface Feature {
  icon: FeatureIconName;
  title: string;
  description: string;
}

/** Prospect-page value propositions. */
export const FEATURES: Feature[] = [
  {
    icon: "automate",
    title: "Automatiser la gestion des arrêts",
    description:
      "Dès qu'un poste s'arrête, OptiFlow ouvre un ticket, notifie le bon intervenant et le suit jusqu'à la prise en charge, la réparation et la reprise validée — sans relance manuelle.",
  },
  {
    icon: "empower",
    title: "Donner du pouvoir à vos équipes",
    description:
      "Offrez aux opérateurs et techniciens un flux de travail clair sur tout appareil : voir l'incident, le prendre en charge et mettre à jour le ticket, de l'atelier jusqu'à la clôture.",
  },
  {
    icon: "transparent",
    title: "Une planification transparente",
    description:
      "Chaque arrêt, horodatage et action est visible en temps réel. Les plans reposent sur ce qui se passe réellement sur la ligne — pas sur des suppositions.",
  },
  {
    icon: "rootcause",
    title: "Identifier et éradiquer les causes racines",
    description:
      "Transformez l'historique des arrêts en analyse des causes racines, puis éliminez les pannes récurrentes pour qu'une même machine ne vous coûte jamais deux fois la même heure.",
  },
];

/** Calendly booking link for the "Demander une démo" call-to-action. */
export const CALENDLY_URL = "https://calendly.com/ttaherhagui/demo-optiflow";

/** Marketing hero copy. */
export const HERO = {
  headline: "Ne perdez plus d'heures à cause des arrêts machine.",
  subhead:
    "OptiFlow est la plateforme multi-tenant qui détecte chaque arrêt, le pilote jusqu'à sa résolution et aide votre usine à éliminer durablement les temps d'arrêt.",
  primaryCta: "Demander une démo",
  secondaryCta: "Découvrir le fonctionnement",
} as const;
