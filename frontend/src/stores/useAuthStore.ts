import { create } from "zustand";
import { persist } from "zustand/middleware";

import { API_URL } from "../constants/api";

export interface AuthUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  namespace_id: string;
  avatar_url?: string | null;
}

export type AuthStatus =
  "idle" | "loading" | "authenticated" | "unauthenticated";

interface AuthState {
  status: AuthStatus;
  /** Bearer access token, sent as Authorization on authenticated requests. */
  token: string | null;
  user: AuthUser | null;
  /** The tenant (plant/organization) the signed-in user belongs to. */
  tenantId: string | null;
  error: string | null;
  /** Base subscription expired less than 30 days ago (grace period). `null`
   * (or absent from an older persisted session) = not warned. */
  warning: boolean | null;
  /** Never subscribed, or expired 30+ days ago: the app is locked to the
   * subscription page. `null` (or absent) = not blocked. */
  blocked: boolean | null;
  /** The namespace's base plan id, `null` when it never subscribed. */
  planId: string | null;
  /** The namespace's base plan name, when known. */
  planName: string | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => void;
}

interface LoginResponse {
  data: {
    access_token: string;
    token_type: string;
    user: AuthUser;
    /** Base subscription state, at the root of `LoginOut`. */
    warning?: boolean | null;
    blocked?: boolean | null;
    plan_id?: string | null;
    plan_name?: string | null;
  };
}

/** Subscription fields of a signed-out session. */
const NO_SUBSCRIPTION = {
  warning: null,
  blocked: null,
  planId: null,
  planName: null,
} as const;

/**
 * Authentication state. The access token is persisted to localStorage so the
 * session survives reloads and can authorize subsequent API calls (see
 * `authHeader` below). `error` holds an i18n key that the component translates.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      status: "unauthenticated",
      token: null,
      user: null,
      tenantId: null,
      error: null,
      ...NO_SUBSCRIPTION,

      signIn: async (username, password) => {
        set({ status: "loading", error: null });

        if (!username || !password) {
          set({ status: "unauthenticated", error: "login.errors.required" });
          return;
        }

        try {
          const res = await fetch(`${API_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password }),
          });

          if (!res.ok) {
            const error =
              res.status === 403
                ? "login.errors.notConfirmed"
                : res.status === 401
                  ? "login.errors.invalidCredentials"
                  : "login.errors.failed";
            set({ status: "unauthenticated", error });
            return;
          }

          const body = (await res.json()) as LoginResponse;
          set({
            status: "authenticated",
            token: body.data.access_token,
            user: body.data.user,
            tenantId: body.data.user.namespace_id,
            error: null,
            warning: body.data.warning ?? null,
            blocked: body.data.blocked ?? null,
            planId: body.data.plan_id ?? null,
            planName: body.data.plan_name ?? null,
          });
        } catch {
          set({ status: "unauthenticated", error: "login.errors.failed" });
        }
      },

      signOut: () => {
        set({
          status: "unauthenticated",
          token: null,
          user: null,
          tenantId: null,
          error: null,
          ...NO_SUBSCRIPTION,
        });
      },
    }),
    {
      name: "optiflow-auth",
      partialize: (s) => ({
        status: s.status,
        token: s.token,
        user: s.user,
        tenantId: s.tenantId,
        warning: s.warning,
        blocked: s.blocked,
        planId: s.planId,
        planName: s.planName,
      }),
    },
  ),
);

/** Authorization header for authenticated API calls (used by other stores). */
export function authHeader(): Record<string, string> {
  const { token } = useAuthStore.getState();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
