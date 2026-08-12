import { create } from "zustand";

import type {
  NamespaceSettings,
  SaveSettingsPayload,
} from "../constants/settings";
import { request, type Result } from "./apiClient";

interface SettingsState {
  /** The current namespace's settings, or null when none exist yet. */
  settings: NamespaceSettings | null;
  /** Whether a settings document exists (drives POST-create vs PATCH-update). */
  exists: boolean;
  loading: boolean;
  error: string | null;
  /** Load the settings of `namespaceId`. A 404 (no settings yet) is not an
   * error: `settings` stays null and `exists` is false so the UI falls back to
   * defaults. */
  fetchSettings: (namespaceId: string) => Promise<void>;
  createSettings: (
    payload: SaveSettingsPayload,
  ) => Promise<Result<NamespaceSettings>>;
  updateSettings: (
    payload: SaveSettingsPayload,
  ) => Promise<Result<NamespaceSettings>>;
}

/** Owns the current namespace's plant settings (shift schedule + escalation
 * delay) and the create/update command actions. */
export const useSettingsStore = create<SettingsState>((set) => ({
  settings: null,
  exists: false,
  loading: false,
  error: null,

  fetchSettings: async (namespaceId) => {
    set({ loading: true, error: null });
    const res = await request<NamespaceSettings>(
      `/settings/${namespaceId}`,
      "GET",
    );
    if (res.ok) {
      set({ settings: res.data ?? null, exists: true, loading: false });
    } else {
      // No settings yet (or unreadable) -> fall back to defaults in the UI.
      set({ settings: null, exists: false, loading: false });
    }
  },

  createSettings: async (payload) => {
    const res = await request<NamespaceSettings>("/settings", "POST", payload);
    if (res.ok) set({ settings: res.data ?? null, exists: true });
    return res;
  },

  updateSettings: async (payload) => {
    const res = await request<NamespaceSettings>("/settings", "PATCH", payload);
    if (res.ok) set({ settings: res.data ?? null, exists: true });
    return res;
  },
}));
