import { create } from "zustand";

import type {
  CreateWorkstationPayload,
  UpdateWorkstationPayload,
  Workstation,
} from "../constants/workstations";
import { request, type Result } from "./apiClient";

interface WorkstationsState {
  workstations: Workstation[];
  loading: boolean;
  error: string | null;
  fetchWorkstations: () => Promise<void>;
  createWorkstation: (
    payload: CreateWorkstationPayload,
  ) => Promise<Result<Workstation>>;
  getWorkstation: (id: string) => Promise<Result<Workstation>>;
  updateWorkstation: (
    id: string,
    payload: UpdateWorkstationPayload,
  ) => Promise<Result<Workstation>>;
  deleteWorkstation: (id: string) => Promise<Result<Workstation>>;
}

/** Workstation state. The list (data/loading/error) is owned here;
 * create/get/update/delete are command actions returning a Result. */
export const useWorkstationsStore = create<WorkstationsState>((set) => ({
  workstations: [],
  loading: false,
  error: null,

  fetchWorkstations: async () => {
    set({ loading: true, error: null });
    const res = await request<Workstation[]>("/workstations", "GET");
    if (res.ok) set({ workstations: res.data ?? [], loading: false });
    else set({ error: res.error ?? "Erreur", loading: false });
  },

  createWorkstation: (payload) =>
    request<Workstation>("/workstations", "POST", payload),
  getWorkstation: (id) => request<Workstation>(`/workstations/${id}`, "GET"),
  updateWorkstation: (id, payload) =>
    request<Workstation>(`/workstations/${id}`, "PUT", payload),
  deleteWorkstation: (id) =>
    request<Workstation>(`/workstations/${id}`, "DELETE"),
}));
