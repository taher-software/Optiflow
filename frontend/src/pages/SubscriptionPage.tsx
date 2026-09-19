import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { BankTransferCard } from "../components/BankTransferCard";
import { ErrorState } from "../components/ErrorState";
import { PlanCard } from "../components/PlanCard";
import { useAuthStore } from "../stores/useAuthStore";
import { useSubscriptionPlansStore } from "../stores/useSubscriptionPlansStore";
import { selectPlanOffers } from "../utils/subscriptionAmount";

/** Subscription paywall: why access is limited, the plans the namespace can
 * buy (every catalog plan when it never subscribed, only its own plan for a
 * renewal) with their TTC amounts, and the bank transfer instructions. */
export function SubscriptionPage() {
  const { t, i18n } = useTranslation();
  const blocked = useAuthStore((s) => s.blocked);
  const planId = useAuthStore((s) => s.planId);

  const plans = useSubscriptionPlansStore((s) => s.plans);
  const loading = useSubscriptionPlansStore((s) => s.loading);
  const error = useSubscriptionPlansStore((s) => s.error);
  const fetchPlans = useSubscriptionPlansStore((s) => s.fetchPlans);

  useEffect(() => {
    void fetchPlans();
  }, [fetchPlans]);

  const offers = selectPlanOffers(plans, planId);
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const status =
    blocked === true
      ? planId === null
        ? "neverSubscribed"
        : "blocked"
      : "expired";

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-bold tracking-tight">
        {t("subscription.title")}
      </h1>
      <p className="mt-2 max-w-3xl text-sm text-slate-400">
        {t(`subscription.status.${status}`)}
      </p>

      {error ? (
        <ErrorState
          title={t("subscription.loadError")}
          detail={error}
          retryLabel={t("common.errors.retry")}
          onRetry={() => void fetchPlans()}
        />
      ) : loading ? (
        <p className="mt-8 text-sm text-slate-400">
          {t("subscription.loading")}
        </p>
      ) : offers.length === 0 ? (
        <p className="mt-8 text-sm text-slate-400">{t("subscription.empty")}</p>
      ) : (
        <div className="mt-8 grid gap-6 lg:grid-cols-3">
          {offers.map((o) => (
            <PlanCard key={o.plan.id} offer={o} locale={locale} />
          ))}
        </div>
      )}

      <div className="mt-8">
        <BankTransferCard />
      </div>
    </div>
  );
}

export default SubscriptionPage;
