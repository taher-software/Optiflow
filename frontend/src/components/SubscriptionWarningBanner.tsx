import { Link } from "react-router-dom";

interface SubscriptionWarningBannerProps {
  message: string;
  linkLabel: string;
  to: string;
}

/** Persistent "subscription expired" banner with a link to renew.
 * Presentational, no state. */
export function SubscriptionWarningBanner({
  message,
  linkLabel,
  to,
}: SubscriptionWarningBannerProps) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 border-b border-amber-400/30 bg-amber-400/10 px-6 py-3"
    >
      <p className="text-sm text-amber-200">{message}</p>
      <Link
        to={to}
        className="shrink-0 rounded-lg bg-amber-400 px-3 py-1.5 text-sm font-semibold text-slate-900 transition-colors hover:bg-amber-300"
      >
        {linkLabel}
      </Link>
    </div>
  );
}

export default SubscriptionWarningBanner;
