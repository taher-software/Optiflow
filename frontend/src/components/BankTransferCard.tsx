import { useTranslation } from "react-i18next";

import { BANK_TRANSFER } from "../constants/subscription";

/** Bank transfer instructions: account details + how activation works.
 * Presentational, no state. */
export function BankTransferCard() {
  const { t } = useTranslation();

  const rows = [
    {
      label: t("subscription.payment.accountHolder"),
      value: BANK_TRANSFER.accountHolder,
    },
    { label: t("subscription.payment.rib"), value: BANK_TRANSFER.rib },
    { label: t("subscription.payment.bank"), value: BANK_TRANSFER.bank },
  ];

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
      <h2 className="text-lg font-semibold text-white">
        {t("subscription.payment.title")}
      </h2>
      <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-slate-300">
        <li>{t("subscription.payment.steps.choose")}</li>
        <li>{t("subscription.payment.steps.transfer")}</li>
        <li>{t("subscription.payment.steps.activation")}</li>
      </ol>
      <dl className="mt-5 grid gap-3 sm:grid-cols-3">
        {rows.map((r) => (
          <div
            key={r.label}
            className="rounded-xl border border-slate-800 bg-slate-950/60 p-3"
          >
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              {r.label}
            </dt>
            <dd className="mt-1 font-mono text-sm break-all text-white select-all">
              {r.value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export default BankTransferCard;
