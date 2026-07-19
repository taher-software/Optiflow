import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";

import { DEVICE_ID_KEY } from "../constants/routes";
import { generateDeviceId } from "../utils/uuid";
import { getPushToken } from "../utils/pushToken";

interface DeviceState {
  /** Current device id — either the cached one or a freshly generated one. */
  deviceId: string | null;
  /** This device's push token (may be null when unavailable). */
  pushToken: string | null;
  /** Whether `deviceId` is already persisted in the device cache. */
  isCached: boolean;
  /** Load the cached device id + resolve the push token. Returns the cached id
   * (or null when this device has never been paired). */
  bootstrap: () => Promise<string | null>;
  /** Generate a new (uncached) device id for the pairing flow. */
  generate: () => string;
  /** Persist the current device id to the cache (after successful pairing). */
  persist: () => Promise<void>;
}

/** Owns the device identity (id + push token) and its persistence. */
export const useDeviceStore = create<DeviceState>((set, get) => ({
  deviceId: null,
  pushToken: null,
  isCached: false,

  bootstrap: async () => {
    const [cached, pushToken] = await Promise.all([
      AsyncStorage.getItem(DEVICE_ID_KEY),
      getPushToken(),
    ]);
    set({
      pushToken,
      deviceId: cached ?? null,
      isCached: cached !== null,
    });
    return cached;
  },

  generate: () => {
    const deviceId = generateDeviceId();
    set({ deviceId, isCached: false });
    return deviceId;
  },

  persist: async () => {
    const { deviceId } = get();
    if (!deviceId) return;
    await AsyncStorage.setItem(DEVICE_ID_KEY, deviceId);
    set({ isCached: true });
  },
}));
