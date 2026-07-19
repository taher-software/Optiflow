import { create } from "zustand";

import type { AuthUser, LoginData } from "../constants/types";
import { postJson, type ApiResult } from "./apiClient";
import { useDeviceStore } from "./useDeviceStore";

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  /** Silent device login using the cached device id. */
  mobileLogin: () => Promise<ApiResult<LoginData>>;
  /** Pair this device using the user's security code. */
  checkUserCode: (securityCode: string) => Promise<ApiResult<LoginData>>;
  signOut: () => void;
}

/** Owns the authenticated session (token + user) for the mobile app. */
export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,

  mobileLogin: async () => {
    const { deviceId, pushToken } = useDeviceStore.getState();
    const res = await postJson<LoginData>("/auth/mobile-login", {
      device_id: deviceId,
      push_token: pushToken,
    });
    if (res.ok && res.data) {
      set({ token: res.data.access_token, user: res.data.user });
    }
    return res;
  },

  checkUserCode: async (securityCode) => {
    const { deviceId, pushToken } = useDeviceStore.getState();
    const res = await postJson<LoginData>("/auth/check-user-code", {
      security_code: securityCode,
      device_id: deviceId,
      push_token: pushToken,
    });
    if (res.ok && res.data) {
      set({ token: res.data.access_token, user: res.data.user });
    }
    return res;
  },

  signOut: () => set({ token: null, user: null }),
}));
