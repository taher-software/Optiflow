import {
  CATALOG_PLAN_KEYS,
  FISCAL_STAMP_MILLIMES,
  MILLIMES_PER_TND,
  PLAN_CURRENCY,
  VAT_RATE_PERCENT,
  type CatalogPlan,
  type PlanKey,
  type PurchaseKind,
} from "../constants/subscription";

/** Amount breakdown of one plan purchase, every figure in integer millimes. */
export interface AmountBreakdown {
  /** Montant HT. */
  ht: number;
  /** TVA 19 % of the HT amount. */
  vat: number;
  /** Timbre fiscal, once per transfer. */
  stamp: number;
  /** Total TTC = HT + TVA + timbre. */
  total: number;
}

/** A catalog plan offered on the subscription page, with its purchase kind. */
export interface PlanOffer {
  plan: CatalogPlan;
  key: PlanKey;
  kind: PurchaseKind;
}

/** Catalog plan key of a backend plan name (trimmed, case-insensitive), or
 * `null` when the name is not part of the catalog. Pure. */
export function planKeyOf(name: string): PlanKey | null {
  return CATALOG_PLAN_KEYS[name.trim().toLowerCase()] ?? null;
}

/** TND amount → integer millimes (rounded to the nearest millime); a missing
 * or non-finite amount counts as 0. Pure. */
export function toMillimes(amount: number | null | undefined): number {
  if (amount === null || amount === undefined || !Number.isFinite(amount)) {
    return 0;
  }
  return Math.round(amount * MILLIMES_PER_TND);
}

/** HT amount (millimes) of a plan purchase. Operio Dedicated: first purchase
 * = acquisition `price` + first year `maintenance_price`; renewal =
 * `maintenance_price` only. Every other plan: `price`. Pure. */
export function htMillimes(
  plan: CatalogPlan,
  key: PlanKey,
  kind: PurchaseKind,
): number {
  if (key !== "dedicated") return toMillimes(plan.price);
  const maintenance = toMillimes(plan.maintenance_price);
  return kind === "first" ? toMillimes(plan.price) + maintenance : maintenance;
}

/** HT → TVA (19 %, rounded to the millime) + timbre fiscal → total TTC, all
 * in integer millimes. Pure. */
export function amountBreakdown(ht: number): AmountBreakdown {
  const vat = Math.round((ht * VAT_RATE_PERCENT) / 100);
  return {
    ht,
    vat,
    stamp: FISCAL_STAMP_MILLIMES,
    total: ht + vat + FISCAL_STAMP_MILLIMES,
  };
}

/** Integer millimes → locale-formatted TND amount with 3 decimals
 * (e.g. fr: "1 191,000 TND", en: "TND 1,191.000"). Pure. */
export function formatTnd(millimes: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: PLAN_CURRENCY,
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  }).format(millimes / MILLIMES_PER_TND);
}

/** Plans the subscription page offers. Never subscribed (`planId === null`)
 * → every catalog plan, as a first purchase; otherwise → only the
 * namespace's plan, as a renewal. Plans outside the catalog are dropped. */
export function selectPlanOffers(
  plans: readonly CatalogPlan[],
  planId: string | null,
): PlanOffer[] {
  const offers: PlanOffer[] = [];
  for (const plan of plans) {
    const key = planKeyOf(plan.name);
    if (key === null) continue;
    if (planId === null) offers.push({ plan, key, kind: "first" });
    else if (plan.id === planId) offers.push({ plan, key, kind: "renewal" });
  }
  return offers;
}
