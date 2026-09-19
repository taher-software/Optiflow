import { create } from "zustand";

import type { CatalogPlan } from "../constants/subscription";
import { request } from "./apiClient";

interface SubscriptionPlansState {
  /** Catalog plans, in the backend's catalog order. */
  plans: CatalogPlan[];
  loading: boolean;
  error: string | null;
  /** Load the tenant-facing plan catalog (`GET /subscriptions/plans`). */
  fetchPlans: () => Promise<void>;
}

/** Owns the subscription plan catalog shown on the subscription page. */
export const useSubscriptionPlansStore = create<SubscriptionPlansState>(
  (set) => ({
    plans: [],
    loading: false,
    error: null,

    fetchPlans: async () => {
      set({ loading: true, error: null });
      const res = await request<CatalogPlan[]>("/subscriptions/plans", "GET");
      if (res.ok) set({ plans: res.data ?? [], loading: false });
      else set({ error: res.error ?? null, loading: false });
    },
  }),
);
