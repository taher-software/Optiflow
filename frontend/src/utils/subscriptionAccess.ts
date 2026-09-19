import { ROUTES } from "../constants/routes";

/** Subscription state from the login response. `null` (or a session persisted
 * before these fields existed) means neither warned nor blocked. */
export interface SubscriptionFlags {
  warning: boolean | null;
  blocked: boolean | null;
}

/** Whether the subscription page and its sidebar entry are available. */
export function canSeeSubscription(flags: SubscriptionFlags): boolean {
  return flags.blocked === true || flags.warning === true;
}

/** Where a protected `/app/*` path must redirect to under the given
 * subscription state, or `null` to render it. Blocked → everything but the
 * subscription page goes to the subscription page; neither blocked nor warned
 * → the subscription page goes back to `/app`. Pure. */
export function subscriptionRedirect(
  pathname: string,
  flags: SubscriptionFlags,
): string | null {
  const onSubscription = pathname === ROUTES.subscription;
  if (flags.blocked === true) {
    return onSubscription ? null : ROUTES.subscription;
  }
  if (onSubscription && !canSeeSubscription(flags)) return ROUTES.app;
  return null;
}
