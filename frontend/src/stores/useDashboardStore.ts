import { create } from "zustand";

import {
  PERIOD_DAYS,
  type DashboardData,
  type DrilldownData,
  type DrillStep,
  type PeriodPreset,
} from "../constants/dashboard";
import { isoDayAfter, isoToday } from "../utils/dashboardFormat";
import { request } from "./apiClient";

/** Bornes ISO [from..to] de la période courante. */
function periodRange(
  period: PeriodPreset,
  from: string,
  to: string,
): { from: string; to: string } {
  if (period === "custom") return { from, to };
  const days = PERIOD_DAYS[period];
  const today = isoToday();
  return { from: isoDayAfter(today, -(days - 1)), to: today };
}

interface DashboardState {
  data: DashboardData | null;
  drilldown: DrilldownData | null;
  period: PeriodPreset;
  customFrom: string;
  customTo: string;
  /** Chemin du drill-down (fil d'Ariane) ; vide = pas de panneau. */
  drillPath: DrillStep[];
  /** Filtres locaux du panneau ("" = tous/toutes). */
  drillProcess: string;
  drillShift: string;
  loading: boolean;
  error: string | null;
  /** Vrai quand le dernier échec vient d'un serveur injoignable (et non d'une
   * erreur renvoyée par le backend) : la page affiche alors son propre message
   * traduit au lieu du texte brut de `error`. */
  offline: boolean;
  /** (Re)charge le dashboard pour la période courante. MOCK : à remplacer par
   * `GET /kpi/dashboard` (spec §5) — seul ce store change au branchement. */
  fetchDashboard: () => Promise<void>;
  setPeriod: (period: PeriodPreset) => void;
  setCustomRange: (from: string, to: string) => void;
  openDrill: (step: DrillStep) => void;
  pushDrill: (step: DrillStep) => void;
  popTo: (index: number) => void;
  closeDrill: () => void;
  setDrillProcess: (process: string) => void;
  setDrillShift: (shift: string) => void;
}

/** Possède les données du dashboard, la période et l'état du drill-down.
 * Règle contractuelle (spec §3) : le drill n'affiche jamais sa propre
 * dimension — le producteur (mock aujourd'hui, backend demain) l'applique. */
export const useDashboardStore = create<DashboardState>((set, get) => ({
  data: null,
  drilldown: null,
  period: "today",
  customFrom: isoToday(),
  customTo: isoToday(),
  drillPath: [],
  drillProcess: "",
  drillShift: "",
  loading: false,
  error: null,
  offline: false,

  fetchDashboard: async () => {
    const {
      period,
      customFrom,
      customTo,
      drillPath,
      drillProcess,
      drillShift,
    } = get();
    set({ loading: true, error: null, offline: false });
    const { from, to } = periodRange(period, customFrom, customTo);

    const dashRes = await request<DashboardData>(
      `/kpi/dashboard?${new URLSearchParams({ from, to })}`,
      "GET",
    );
    if (!dashRes.ok) {
      set({
        error: dashRes.error ?? "error",
        offline: dashRes.offline ?? false,
        loading: false,
      });
      return;
    }

    let drilldown: DrilldownData | null = null;
    if (drillPath.length) {
      const params = new URLSearchParams({
        path: drillPath.map((s) => `${s.kind}:${s.id}`).join(">"),
        from,
        to,
      });
      if (drillProcess) params.set("process", drillProcess);
      if (drillShift) params.set("shift", drillShift);
      const drillRes = await request<DrilldownData>(
        `/kpi/drilldown?${params}`,
        "GET",
      );
      if (drillRes.ok) drilldown = drillRes.data ?? null;
    }

    set({ data: dashRes.data ?? null, drilldown, loading: false });
  },

  setPeriod: (period) => {
    set({ period });
    void get().fetchDashboard();
  },

  setCustomRange: (customFrom, customTo) => {
    set({ period: "custom", customFrom, customTo });
    void get().fetchDashboard();
  },

  openDrill: (step) => {
    set({ drillPath: [step], drillProcess: "", drillShift: "" });
    void get().fetchDashboard();
  },

  pushDrill: (step) => {
    set({ drillPath: [...get().drillPath, step] });
    void get().fetchDashboard();
  },

  popTo: (index) => {
    set({ drillPath: get().drillPath.slice(0, index + 1) });
    void get().fetchDashboard();
  },

  closeDrill: () => {
    set({ drillPath: [], drilldown: null, drillProcess: "", drillShift: "" });
  },

  setDrillProcess: (drillProcess) => {
    set({ drillProcess });
    void get().fetchDashboard();
  },

  setDrillShift: (drillShift) => {
    set({ drillShift });
    void get().fetchDashboard();
  },
}));
