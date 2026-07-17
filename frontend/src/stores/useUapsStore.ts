import { create } from "zustand";

import type {
  CreateUapPayload,
  Uap,
  UpdateUapPayload,
} from "../constants/uaps";
import { request, type Result } from "./apiClient";

interface UapsState {
  uaps: Uap[];
  loading: boolean;
  error: string | null;
  fetchUaps: () => Promise<void>;
  createUap: (payload: CreateUapPayload) => Promise<Result<Uap>>;
  getUap: (id: string) => Promise<Result<Uap>>;
  updateUap: (id: string, payload: UpdateUapPayload) => Promise<Result<Uap>>;
  deleteUap: (id: string) => Promise<Result<Uap>>;
}

/** Production-area (UAP) state. The list (data/loading/error) is owned here;
 * create/get/update/delete are command actions returning a Result. */
export const useUapsStore = create<UapsState>((set) => ({
  uaps: [],
  loading: false,
  error: null,

  fetchUaps: async () => {
    set({ loading: true, error: null });
    const res = await request<Uap[]>("/uaps", "GET");
    if (res.ok) set({ uaps: res.data ?? [], loading: false });
    else set({ error: res.error ?? "Erreur", loading: false });
  },

  createUap: (payload) => request<Uap>("/uaps", "POST", payload),
  getUap: (id) => request<Uap>(`/uaps/${id}`, "GET"),
  updateUap: (id, payload) => request<Uap>(`/uaps/${id}`, "PUT", payload),
  deleteUap: (id) => request<Uap>(`/uaps/${id}`, "DELETE"),
}));
