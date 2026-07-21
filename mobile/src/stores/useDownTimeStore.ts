import { create } from "zustand";

import type {
  CreateDownTimePayload,
  DownTime,
  DownTimeStatus,
  DownTimeSummary,
} from "../constants/downtime";
import { apiRequest, type ApiResult } from "./apiClient";

interface DownTimeState {
  summary: DownTimeSummary | null;
  issues: DownTime[];
  loadingSummary: boolean;
  loadingIssues: boolean;
  error: string | null;
  fetchSummary: () => Promise<void>;
  fetchIssues: (status?: DownTimeStatus) => Promise<void>;
  getIssue: (id: string) => Promise<ApiResult<DownTime>>;
  createDownTime: (
    payload: CreateDownTimePayload,
  ) => Promise<ApiResult<{ job_id: string }>>;
  acknowledge: (id: string) => Promise<ApiResult<DownTime>>;
  resolve: (id: string) => Promise<ApiResult<DownTime>>;
  close: (id: string) => Promise<ApiResult<DownTime>>;
  remove: (id: string) => Promise<ApiResult<DownTime>>;
}

/** Owns downtime data: the home summary, the issue list (by status), and the
 * create + lifecycle command actions. */
export const useDownTimeStore = create<DownTimeState>((set) => ({
  summary: null,
  issues: [],
  loadingSummary: false,
  loadingIssues: false,
  error: null,

  fetchSummary: async () => {
    set({ loadingSummary: true, error: null });
    const res = await apiRequest<DownTimeSummary>("/down-times/summary");
    if (res.ok) set({ summary: res.data ?? null, loadingSummary: false });
    else set({ error: res.detail ?? "error", loadingSummary: false });
  },

  fetchIssues: async (status) => {
    set({ loadingIssues: true, error: null });
    const path = status
      ? `/down-times?status=${encodeURIComponent(status)}`
      : "/down-times";
    const res = await apiRequest<DownTime[]>(path);
    if (res.ok) set({ issues: res.data ?? [], loadingIssues: false });
    else set({ error: res.detail ?? "error", loadingIssues: false });
  },

  getIssue: (id) => apiRequest<DownTime>(`/down-times/${id}`),
  createDownTime: (payload) =>
    apiRequest<{ job_id: string }>("/down-times", "POST", payload),
  acknowledge: (id) =>
    apiRequest<DownTime>(`/down-times/${id}/acknowledge`, "POST"),
  resolve: (id) => apiRequest<DownTime>(`/down-times/${id}/resolve`, "POST"),
  close: (id) => apiRequest<DownTime>(`/down-times/${id}/close`, "POST"),
  remove: (id) => apiRequest<DownTime>(`/down-times/${id}`, "DELETE"),
}));
