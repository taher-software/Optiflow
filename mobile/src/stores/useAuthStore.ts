import { create } from "zustand";

import i18n from "i18next";

import type { AuthUser, LoginData, SetOnlineData } from "../constants/types";
import { apiRequest, postJson, type ApiResult } from "./apiClient";
import { useDeviceStore } from "./useDeviceStore";
import { useToastStore } from "./useToastStore";

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  /** True while `PATCH /users/me/online` is in flight (guards double-taps). */
  settingOnline: boolean;
  /** Silent device login using the cached device id. */
  mobileLogin: () => Promise<ApiResult<LoginData>>;
  /** Pair this device using the user's security code. */
  checkUserCode: (securityCode: string) => Promise<ApiResult<LoginData>>;
  /** Declare the current user reachable (or not) for team notifications.
   * Flips `user.online` optimistically and rolls back on failure. */
  setOnline: (online: boolean) => Promise<ApiResult<SetOnlineData>>;
  signOut: () => void;
}

/** Owns the authenticated session (token + user) for the mobile app. */
export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  user: null,
  settingOnline: false,

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

  setOnline: async (online) => {
    const current = get().user;
    const previous = current?.online ?? true;
    // Optimistic: shop-floor phones lose the network routinely, so the switch
    // must move at once — and must not keep lying if the call never lands.
    if (current) set({ user: { ...current, online } });
    set({ settingOnline: true });
    const res = await apiRequest<SetOnlineData>("/users/me/online", "PATCH", {
      online,
    });
    if (res.ok) {
      const confirmed = res.data?.online ?? online;
      const latest = get().user;
      if (latest) set({ user: { ...latest, online: confirmed } });
    } else {
      const latest = get().user;
      if (latest) set({ user: { ...latest, online: previous } });
      useToastStore.getState().show(i18n.t("home.online.error"), "error");
    }
    set({ settingOnline: false });
    return res;
  },

  signOut: () => set({ token: null, user: null, settingOnline: false }),
}));
