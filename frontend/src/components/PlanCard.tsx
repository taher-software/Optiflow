import { useTranslation } from "react-i18next";

import {
  ANNUAL_DURATION_DAYS,
  COMPLEMENTARY_PLANS,
  PLAN_FEATURES,
} from "../constants/subscription";
import {
  amountBreakdown,
  formatTnd,
  htMillimes,
  toMillimes,
  type PlanOffer,
} from "../utils/subscriptionAmount";
import { AmountBreakdownList, type AmountLine } from "./AmountBreakdownList";

interface PlanCardProps {
  offer: PlanOffer;
  /** Locale used to format amounts (e.g. "fr", "en"). */
  locale: string;
}

/** One offered plan: name, duration, features, and the full HT → TTC amount
 * breakdown. Amounts come from the pure `subscriptionAmount` utils. */
export function PlanCard({ offer, locale }: PlanCardProps) {
  const { t } = useTranslation();
  const { plan, key, kind } = offer;
  const base = `subscription.plans.${key}`;
  const money = (millimes: number) => formatTnd(millimes, locale);

  const breakdown = amountBreakdown(htMillimes(plan, key, kind));
  const complementary = COMPLEMENTARY_PLANS.includes(key);
  const duration =
    plan.duration === ANNUAL_DURATION_DAYS
      ? t("subscription.duration.annual")
      : t("subscription.duration.days", { count: plan.duration });

  // Operio Private: acquisition and yearly maintenance & hosting shown apart.
  const componentLines: AmountLine[] =
    key === "dedicated"
      ? [
          ...(kind === "first"
            ? [
                {
                  label: t("subscription.amounts.acquisition"),
                  value: money(toMillimes(plan.price)),
                },
              ]
            : []),
          {
            label: t("subscription.amounts.maintenance"),
            value: money(toMillimes(plan.maintenance_price)),
          },
        ]
      : [];

  const lines: AmountLine[] = [
    { label: t("subscription.amounts.ht"), value: money(breakdown.ht) },
    { label: t("subscription.amounts.vat"), value: money(breakdown.vat) },
    { label: t("subscription.amounts.stamp"), value: money(breakdown.stamp) },
  ];

  return (
    <article className="flex flex-col rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold text-white">
          {t(`${base}.name`)}
        </h2>
        <span className="rounded-full bg-teal-400/10 px-2 py-0.5 text-xs font-medium text-teal-300">
          {t(`subscription.kind.${kind}`)}
        </span>
      </div>
      <p className="mt-1 text-sm text-slate-400">{t(`${base}.tagline`)}</p>
      {complementary && (
        <p className="mt-2 text-xs font-medium text-amber-300">
          {t("subscription.complementaryNote")}
        </p>
      )}

      <p className="mt-4 text-sm text-slate-300">
        {t("subscription.durationLabel")}{" "}
        <span className="font-medium text-white">{duration}</span>
      </p>
      {key === "intelligence" && plan.quota !== null && (
        <p className="mt-1 text-sm text-slate-300">
          {t("subscription.quotaLabel")}{" "}
          <span className="font-medium text-white">
            {t("subscription.quotaValue", { count: plan.quota })}
          </span>
        </p>
      )}

      <ul className="mt-4 space-y-1.5 text-sm text-slate-300">
        {PLAN_FEATURES[key].map((f) => (
          <li key={f} className="flex gap-2">
            <span aria-hidden="true" className="text-teal-400">
              ✓
            </span>
            {t(`${base}.features.${f}`)}
          </li>
        ))}
      </ul>

      <div className="mt-auto space-y-3 pt-6">
        {componentLines.length > 0 && (
          <dl className="space-y-1.5 rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-sm">
            {componentLines.map((l) => (
              <div key={l.label} className="flex justify-between gap-4">
                <dt className="text-slate-400">{l.label}</dt>
                <dd className="tabular-nums text-slate-200">{l.value}</dd>
              </div>
            ))}
          </dl>
        )}
        <AmountBreakdownList
          lines={lines}
          totalLabel={t("subscription.amounts.total")}
          totalValue={money(breakdown.total)}
        />
      </div>
    </article>
  );
}

export default PlanCard;
