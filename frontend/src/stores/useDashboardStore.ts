import { create } from "zustand";

import {
  type DashboardData,
  type DrilldownData,
  type DrillStep,
  type PeriodPreset,
} from "../constants/dashboard";
import { isoToday, periodRange } from "../utils/dashboardFormat";
import { request } from "./apiClient";

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
  /** Chargement du seul panneau drill-down (distinct de `loading`, qui porte
   * sur le dashboard). */
  drillLoading: boolean;
  error: string | null;
  /** Vrai quand le dernier échec vient d'un serveur injoignable (et non d'une
   * erreur renvoyée par le backend) : la page affiche alors son propre message
   * traduit au lieu du texte brut de `error`. */
  offline: boolean;
  /** (Re)charge le dashboard (`GET /kpi/dashboard`) pour la période courante.
   * Ne touche jamais au drill-down. */
  fetchDashboard: () => Promise<void>;
  /** (Re)charge le seul panneau drill-down (`GET /kpi/drilldown`) pour le
   * chemin, les filtres et la période courants. */
  fetchDrilldown: () => Promise<void>;
  setPeriod: (period: PeriodPreset) => void;
  setCustomRange: (from: string, to: string) => void;
  openDrill: (step: DrillStep) => void;
  pushDrill: (step: DrillStep) => void;
  popTo: (index: number) => void;
  closeDrill: () => void;
  setDrillProcess: (process: string) => void;
  setDrillShift: (shift: string) => void;
}

/** Compteurs de requête : une réponse est ignorée si un appel plus récent est
 * parti entre-temps (deux clics rapprochés ne doivent pas laisser la réponse
 * la plus lente écraser l'affichage). */
let dashboardRequestId = 0;
let drilldownRequestId = 0;

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
  drillLoading: false,
  error: null,
  offline: false,

  fetchDashboard: async () => {
    const { period, customFrom, customTo } = get();
    const requestId = ++dashboardRequestId;
    set({ loading: true, error: null, offline: false });
    const { from, to } = periodRange(period, customFrom, customTo);

    const dashRes = await request<DashboardData>(
      `/kpi/dashboard?${new URLSearchParams({ from, to })}`,
      "GET",
    );
    if (requestId !== dashboardRequestId) return; // réponse périmée

    if (!dashRes.ok) {
      set({
        error: dashRes.error ?? "error",
        offline: dashRes.offline ?? false,
        loading: false,
      });
      return;
    }
    set({ data: dashRes.data ?? null, loading: false });
  },

  fetchDrilldown: async () => {
    const {
      period,
      customFrom,
      customTo,
      drillPath,
      drillProcess,
      drillShift,
    } = get();
    if (!drillPath.length) return;

    const requestId = ++drilldownRequestId;
    set({ drillLoading: true });
    const { from, to } = periodRange(period, customFrom, customTo);
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
    if (requestId !== drilldownRequestId) return; // réponse périmée

    set({
      drilldown: drillRes.ok ? (drillRes.data ?? null) : null,
      drillLoading: false,
    });
  },

  setPeriod: (period) => {
    set({ period });
    void Promise.all([get().fetchDashboard(), get().fetchDrilldown()]);
  },

  setCustomRange: (customFrom, customTo) => {
    set({ period: "custom", customFrom, customTo });
    void Promise.all([get().fetchDashboard(), get().fetchDrilldown()]);
  },

  openDrill: (step) => {
    set({ drillPath: [step], drillProcess: "", drillShift: "" });
    void get().fetchDrilldown();
  },

  pushDrill: (step) => {
    set({ drillPath: [...get().drillPath, step] });
    void get().fetchDrilldown();
  },

  popTo: (index) => {
    set({ drillPath: get().drillPath.slice(0, index + 1) });
    void get().fetchDrilldown();
  },

  closeDrill: () => {
    drilldownRequestId += 1; // toute réponse en vol devient périmée
    set({
      drillPath: [],
      drilldown: null,
      drillProcess: "",
      drillShift: "",
      drillLoading: false,
    });
  },

  setDrillProcess: (drillProcess) => {
    set({ drillProcess });
    void get().fetchDrilldown();
  },

  setDrillShift: (drillShift) => {
    set({ drillShift });
    void get().fetchDrilldown();
  },
}));
