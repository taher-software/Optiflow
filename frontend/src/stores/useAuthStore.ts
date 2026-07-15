import { create } from "zustand";

export interface AuthUser {
  id: string;
  email: string;
  displayName: string;
}

export type AuthStatus =
  "idle" | "loading" | "authenticated" | "unauthenticated";

interface AuthState {
  status: AuthStatus;
  user: AuthUser | null;
  /** The tenant (plant/organization) the signed-in user belongs to. */
  tenantId: string | null;
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
}

/**
 * Authentication state for the app.
 *
 * NOTE: `signIn`/`signOut` are STUBBED for now so the entry flow is
 * demonstrable without external config. Replace the marked sections with
 * Firebase Authentication when the Firebase project is ready:
 *   - signIn  -> signInWithEmailAndPassword(auth, email, password),
 *               then resolve the tenant from the user's custom claims
 *               (or a Firestore users/{uid} mapping).
 *   - signOut -> firebaseSignOut(auth)
 *   - add onAuthStateChanged(...) on app start to restore the session.
 */
export const useAuthStore = create<AuthState>((set) => ({
  status: "unauthenticated",
  user: null,
  tenantId: null,
  error: null,

  signIn: async (email, password) => {
    set({ status: "loading", error: null });

    if (!email || !password) {
      // `error` holds an i18n key; the component translates it.
      set({
        status: "unauthenticated",
        error: "login.errors.required",
      });
      return;
    }

    try {
      // TODO(auth): replace this stub with Firebase Authentication + tenant resolution.
      await new Promise((resolve) => setTimeout(resolve, 600));
      set({
        status: "authenticated",
        user: {
          id: "stub-user",
          email,
          displayName: email.split("@")[0],
        },
        tenantId: "stub-tenant",
      });
    } catch {
      set({ status: "unauthenticated", error: "login.errors.failed" });
    }
  },

  signOut: () => {
    // TODO(auth): call Firebase signOut(auth).
    set({ status: "unauthenticated", user: null, tenantId: null, error: null });
  },
}));
