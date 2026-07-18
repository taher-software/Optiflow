import { create } from "zustand";

import type {
  CreateProductionLinePayload,
  ProductionLine,
  UpdateProductionLinePayload,
} from "../constants/productionLines";
import { request, type Result } from "./apiClient";

interface ProductionLinesState {
  lines: ProductionLine[];
  loading: boolean;
  error: string | null;
  fetchLines: () => Promise<void>;
  createLine: (
    payload: CreateProductionLinePayload,
  ) => Promise<Result<ProductionLine>>;
  getLine: (id: string) => Promise<Result<ProductionLine>>;
  updateLine: (
    id: string,
    payload: UpdateProductionLinePayload,
  ) => Promise<Result<ProductionLine>>;
  deleteLine: (id: string) => Promise<Result<ProductionLine>>;
}

/** Production-line state. The list (data/loading/error) is owned here;
 * create/get/update/delete are command actions returning a Result. */
export const useProductionLinesStore = create<ProductionLinesState>((set) => ({
  lines: [],
  loading: false,
  error: null,

  fetchLines: async () => {
    set({ loading: true, error: null });
    const res = await request<ProductionLine[]>("/production-lines", "GET");
    if (res.ok) set({ lines: res.data ?? [], loading: false });
    else set({ error: res.error ?? "Erreur", loading: false });
  },

  createLine: (payload) =>
    request<ProductionLine>("/production-lines", "POST", payload),
  getLine: (id) => request<ProductionLine>(`/production-lines/${id}`, "GET"),
  updateLine: (id, payload) =>
    request<ProductionLine>(`/production-lines/${id}`, "PUT", payload),
  deleteLine: (id) =>
    request<ProductionLine>(`/production-lines/${id}`, "DELETE"),
}));
