import { create } from "zustand";

import { apiRequest } from "./apiClient";

export interface Uap {
  id: string;
  name: string;
}

export interface ProductionLine {
  id: string;
  name: string;
  uap_id: string | null;
}

export interface Workstation {
  id: string;
  name: string;
  production_line_id: string | null;
}

interface ResourcesState {
  uaps: Uap[];
  lines: ProductionLine[];
  workstations: Workstation[];
  loading: boolean;
  /** Load the plant structure needed to declare a downtime. */
  loadStructure: () => Promise<void>;
}

/** Read-only plant structure (UAPs / production lines / workstations) used to
 * drive the declare-downtime cascading pickers. Production agents can list
 * these (backend read scope was widened for them). */
export const useResourcesStore = create<ResourcesState>((set) => ({
  uaps: [],
  lines: [],
  workstations: [],
  loading: false,

  loadStructure: async () => {
    set({ loading: true });
    const [uaps, lines, workstations] = await Promise.all([
      apiRequest<Uap[]>("/uaps"),
      apiRequest<ProductionLine[]>("/production-lines"),
      apiRequest<Workstation[]>("/workstations"),
    ]);
    set({
      uaps: uaps.data ?? [],
      lines: lines.data ?? [],
      workstations: workstations.data ?? [],
      loading: false,
    });
  },
}));
