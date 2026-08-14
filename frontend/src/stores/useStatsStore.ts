import { create } from "zustand";

import type {
  DailyPoint,
  StatsFilters,
  StatsMetric,
  StatsMode,
} from "../constants/dashboard";
import { isoDayAfter, isoToday } from "../utils/dashboardFormat";
import { request } from "./apiClient";

/** Chemin `/kpi/daily` pour une métrique + un jeu de filtres. */
function dailyPath(metric: StatsMetric, f: StatsFilters): string {
  const params = new URLSearchParams({
    metric,
    scope_kind: f.scope_kind,
    from: f.from,
    to: f.to,
  });
  if (f.scope_kind !== "plant" && f.scope_id)
    params.set("scope_id", f.scope_id);
  if (f.process) params.set("process", f.process);
  if (f.shift) params.set("shift", f.shift);
  return `/kpi/daily?${params}`;
}

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

/** Préréglages de la comparaison : usine entière (les ids d'endroits
 * dépendent du tenant), 30 derniers jours vs les 31 précédents. */
function defaultEpisode1(): StatsFilters {
  return {
    scope_kind: "plant",
    scope_id: "",
    process: "",
    shift: "",
    from: isoDayAfter(isoToday(), -30),
    to: isoToday(),
  };
}
function defaultEpisode2(): StatsFilters {
  return {
    scope_kind: "plant",
    scope_id: "",
    process: "",
    shift: "",
    from: isoDayAfter(isoToday(), -61),
    to: isoDayAfter(isoToday(), -31),
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
    const [res, res1, res2] = await Promise.all([
      request<{ points: DailyPoint[] }>(dailyPath(metric, filters), "GET"),
      request<{ points: DailyPoint[] }>(dailyPath(metric, episode1), "GET"),
      request<{ points: DailyPoint[] }>(dailyPath(metric, episode2), "GET"),
    ]);
    if (!res.ok) {
      set({ error: res.error ?? "error", loading: false });
      return;
    }
    set({
      daily: res.data?.points ?? [],
      daily1: res1.ok ? (res1.data?.points ?? []) : [],
      daily2: res2.ok ? (res2.data?.points ?? []) : [],
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
