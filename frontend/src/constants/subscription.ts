/** A plan of the tenant-facing catalog, as returned by
 * `GET /subscriptions/plans` (mirrors the backend `CatalogPlanOut`). `price`
 * and `maintenance_price` are HT amounts in TND; `duration` is in days. */
export interface CatalogPlan {
  id: string;
  name: string;
  price: number;
  duration: number;
  quota: number | null;
  maintenance_price: number | null;
}

/** Stable key of a catalog plan, used for i18n copy and pricing rules. */
export type PlanKey = "standard" | "dedicated" | "intelligence";

/** Backend plan name → plan key. Matched trimmed and case-insensitive (same
 * rule as the backend catalog filter). The customer-facing names live in the
 * locale files (`subscription.plans.<key>.name`) — "Operio Dedicated" is
 * displayed as "Operio Private". */
export const CATALOG_PLAN_KEYS: Readonly<Record<string, PlanKey>> = {
  "operio standard": "standard",
  "operio dedicated": "dedicated",
  "operio intelligence": "intelligence",
};

/** Complementary plans: sold on top of a base plan, never on their own. */
export const COMPLEMENTARY_PLANS: readonly PlanKey[] = ["intelligence"];

/** Ordered feature ids per plan; each resolves to
 * `subscription.plans.<key>.features.<id>` in the locale files. */
export const PLAN_FEATURES: Readonly<Record<PlanKey, readonly string[]>> = {
  standard: ["infrastructure", "application", "updates", "hosting", "support"],
  dedicated: [
    "infrastructure",
    "deployment",
    "branding",
    "configuration",
    "development",
  ],
  intelligence: ["query", "quota"],
};

/** First purchase (never subscribed) or renewal of the namespace's plan. */
export type PurchaseKind = "first" | "renewal";

/** VAT (TVA) rate applied to every HT amount, in percent. */
export const VAT_RATE_PERCENT = 19;

/** Fiscal stamp (timbre fiscal) charged once per transfer, in millimes
 * (1.000 TND). */
export const FISCAL_STAMP_MILLIMES = 1000;

/** Millimes per dinar. */
export const MILLIMES_PER_TND = 1000;

/** Currency of every plan amount. */
export const PLAN_CURRENCY = "TND";

/** A `duration` of this many days is displayed as "annual". */
export const ANNUAL_DURATION_DAYS = 365;

/** Bank account receiving subscription transfers. Legal/banking identifiers:
 * deliberately NOT translated. */
export const BANK_TRANSFER = {
  accountHolder: "AZIBODIN",
  rib: "08032012041002057880",
  bank: "Biat Agence El Bouhaira C4",
} as const;
