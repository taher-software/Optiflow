import { create } from "zustand";

import type {
  DownTimeGantt,
  GanttTypeFilter,
} from "../constants/downTimesGantt";
import { request } from "./apiClient";

/** Query path for `GET /down-times/gantt`.
 *
 * `day` is omitted while it is still unknown: the production day is resolved in
 * the NAMESPACE timezone by the backend, and guessing it from the browser's
 * clock would silently ask for the wrong day for a visitor in another country.
 * The first answer echoes the resolved `day`, which then drives the picker. */
function ganttPath(day: string, type: GanttTypeFilter): string {
  const params = new URLSearchParams();
  if (day) params.set("day", day);
  if (type) params.set("type", type);
  const query = params.toString();
  return query ? `/down-times/gantt?${query}` : "/down-times/gantt";
}

interface DownTimesGanttState {
  data: DownTimeGantt | null;
  /** Selected production day, ISO "YYYY-MM-DD". `""` until the first response
   * resolves it (see `ganttPath`). */
  day: string;
  /** Workstation-type filter; `""` = none. Mirrors the `?type=` query param. */
  type: GanttTypeFilter;
  loading: boolean;
  error: string | null;
  /** True when the last failure was an unreachable server (rather than an error
   * the backend returned): the page then shows its own translated message. */
  offline: boolean;
  /** (Re)loads the gantt for the current day + type filter. */
  fetchGantt: () => Promise<void>;
  setDay: (day: string) => void;
  setType: (type: GanttTypeFilter) => void;
  /** Opens the day + type carried by the URL, in ONE request.
   *
   * Both are set unconditionally — the store outlives the page (a visit leaves
   * the last resolved day behind), so the URL a visitor arrives with must win
   * over that leftover, in both directions: `""` means "no day" and hands the
   * resolution back to the backend, which answers the plant's current
   * production day in the namespace timezone. */
  openFromUrl: (day: string, type: GanttTypeFilter) => void;
}

/** Request counter: a response is dropped once a newer call has left, so two
 * quick clicks never let the slower answer overwrite the display. */
let requestCounter = 0;

/** Owns the day-scoped downtime Gantt (`GET /down-times/gantt`): the selected
 * day, the workstation-type filter, and the loaded payload. */
export const useDownTimesGanttStore = create<DownTimesGanttState>(
  (set, get) => ({
    data: null,
    day: "",
    type: "",
    loading: false,
    error: null,
    offline: false,

    fetchGantt: async () => {
      const { day, type } = get();
      const requestId = ++requestCounter;
      set({ loading: true, error: null, offline: false });

      const res = await request<DownTimeGantt>(ganttPath(day, type), "GET");
      if (requestId !== requestCounter) return; // stale response

      if (!res.ok) {
        set({
          data: null,
          error: res.error ?? "error",
          offline: res.offline ?? false,
          loading: false,
        });
        return;
      }
      // The response carries the day the backend actually resolved: adopt it,
      // so the picker shows the plant's day rather than the browser's.
      set({
        data: res.data ?? null,
        day: res.data?.day ?? day,
        loading: false,
      });
    },

    setDay: (day) => {
      set({ day });
      void get().fetchGantt();
    },

    setType: (type) => {
      set({ type });
      void get().fetchGantt();
    },

    openFromUrl: (day, type) => {
      set({ day, type });
      void get().fetchGantt();
    },
  }),
);
