import { create } from "zustand";

import type {
  DailyPoint,
  StatsFilters,
  StatsMetric,
  StatsMode,
} from "../constants/dashboard";
import { isoDayAfter, isoToday } from "../utils/dashboardFormat";
import { mockDaily } from "../utils/dashboardMock";

function defaultFilters(): StatsFilters {
  return {
    scope_kind: "plant",
    scope_id: "",
    process: "",
    shift: "",
    from: isoDayAfter(isoToday(), -22),
    to: isoToday(),
  };
}

/** Préréglages de la comparaison (exemple du spec : même scope/processus,
 * deux périodes différentes). */
function defaultEpisode1(): StatsFilters {
  return {
    scope_kind: "uap",
    scope_id: "uap-1",
    process: "maintenance",
    shift: "",
    from: "2026-01-01",
    to: "2026-01-31",
  };
}
function defaultEpisode2(): StatsFilters {
  return {
    scope_kind: "uap",
    scope_id: "uap-1",
    process: "maintenance",
    shift: "",
    from: "2025-02-01",
    to: "2025-02-28",
  };
}

interface StatsState {
  metric: StatsMetric;
  mode: StatsMode;
  filters: StatsFilters;
  episode1: StatsFilters;
  episode2: StatsFilters;
  daily: DailyPoint[];
  daily1: DailyPoint[];
  daily2: DailyPoint[];
  loading: boolean;
  error: string | null;
  /** (Re)charge les séries du mode courant. MOCK : à remplacer par
   * `GET /kpi/daily` (la comparaison = 2 appels) — spec §5. */
  fetchSeries: () => Promise<void>;
  setMetric: (metric: StatsMetric) => void;
  setMode: (mode: StatsMode) => void;
  setFilters: (patch: Partial<StatsFilters>) => void;
  setEpisode1: (patch: Partial<StatsFilters>) => void;
  setEpisode2: (patch: Partial<StatsFilters>) => void;
}

/** Possède l'explorateur Stats : métrique, mode (suivi | comparaison),
 * filtres et séries journalières. */
export const useStatsStore = create<StatsState>((set, get) => ({
  metric: "duration",
  mode: "follow",
  filters: defaultFilters(),
  episode1: defaultEpisode1(),
  episode2: defaultEpisode2(),
  daily: [],
  daily1: [],
  daily2: [],
  loading: false,
  error: null,

  fetchSeries: async () => {
    const { metric, filters, episode1, episode2 } = get();
    set({ loading: true, error: null });
    await Promise.resolve(); // frontière du futur fetch réseau
    set({
      daily: mockDaily(metric, filters),
      daily1: mockDaily(metric, episode1),
      daily2: mockDaily(metric, episode2),
      loading: false,
    });
  },

  setMetric: (metric) => {
    set({ metric });
    void get().fetchSeries();
  },

  setMode: (mode) => set({ mode }),

  setFilters: (patch) => {
    set({ filters: { ...get().filters, ...patch } });
    void get().fetchSeries();
  },

  setEpisode1: (patch) => {
    set({ episode1: { ...get().episode1, ...patch } });
    void get().fetchSeries();
  },

  setEpisode2: (patch) => {
    set({ episode2: { ...get().episode2, ...patch } });
    void get().fetchSeries();
  },
}));
