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
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => void;
}

interface LoginResponse {
  data: { access_token: string; token_type: string; user: AuthUser };
}

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
      }),
    },
  ),
);

/** Authorization header for authenticated API calls (used by other stores). */
export function authHeader(): Record<string, string> {
  const { token } = useAuthStore.getState();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
