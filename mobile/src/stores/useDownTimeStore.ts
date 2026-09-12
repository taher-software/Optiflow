import { create } from "zustand";

import type {
  CreateDownTimePayload,
  DownTime,
  DownTimePage,
  DownTimeStatus,
  DownTimeSummary,
} from "../constants/downtime";
import {
  readDownTimeConflict,
  type DownTimeConflict,
} from "../utils/downTimeConflict";
import { apiRequest, type ApiResult } from "./apiClient";

const PAGE_SIZE = 10;

interface DownTimeState {
  summary: DownTimeSummary | null;
  issues: DownTime[];
  /** Total number of issues across all pages for the current filter. */
  issuesTotal: number;
  /** The status filter the loaded issues belong to (undefined = all). */
  issuesStatus?: DownTimeStatus;
  loadingSummary: boolean;
  /** First-page (reset) load. */
  loadingIssues: boolean;
  /** Appending the next page. */
  loadingMore: boolean;
  error: string | null;
  /** Set when the last declaration was refused with 409 (§4: the resource or
   * one of its ancestors already has an open ticket). */
  conflict: DownTimeConflict | null;
  fetchSummary: () => Promise<void>;
  /** Load the first page for `status` (replaces the list). */
  fetchIssues: (status?: DownTimeStatus) => Promise<void>;
  /** Append the next page (no-op when all issues are loaded). */
  fetchMoreIssues: () => Promise<void>;
  getIssue: (id: string) => Promise<ApiResult<DownTime>>;
  createDownTime: (
    payload: CreateDownTimePayload,
  ) => Promise<ApiResult<{ job_id: string }>>;
  /** Drop the pending conflict (the user changed their selection). */
  clearConflict: () => void;
  acknowledge: (id: string) => Promise<ApiResult<DownTime>>;
  resolve: (id: string) => Promise<ApiResult<DownTime>>;
  close: (id: string) => Promise<ApiResult<DownTime>>;
  reject: (id: string) => Promise<ApiResult<DownTime>>;
  remove: (id: string) => Promise<ApiResult<DownTime>>;
}

function pagePath(status: DownTimeStatus | undefined, offset: number): string {
  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offset),
  });
  if (status) params.set("status", status);
  return `/down-times?${params.toString()}`;
}

/** Owns downtime data: the home summary, the paginated issue list (by status),
 * and the create + lifecycle command actions. */
export const useDownTimeStore = create<DownTimeState>((set, get) => ({
  summary: null,
  issues: [],
  issuesTotal: 0,
  issuesStatus: undefined,
  loadingSummary: false,
  loadingIssues: false,
  loadingMore: false,
  error: null,
  conflict: null,

  fetchSummary: async () => {
    set({ loadingSummary: true, error: null });
    const res = await apiRequest<DownTimeSummary>("/down-times/summary");
    if (res.ok) set({ summary: res.data ?? null, loadingSummary: false });
    else set({ error: res.detail ?? "error", loadingSummary: false });
  },

  fetchIssues: async (status) => {
    set({
      loadingIssues: true,
      error: null,
      issuesStatus: status,
      issues: [],
      issuesTotal: 0,
    });
    const res = await apiRequest<DownTimePage>(pagePath(status, 0));
    if (res.ok) {
      set({
        issues: res.data?.items ?? [],
        issuesTotal: res.data?.total ?? 0,
        loadingIssues: false,
      });
    } else {
      set({ error: res.detail ?? "error", loadingIssues: false });
    }
  },

  fetchMoreIssues: async () => {
    const { issues, issuesTotal, issuesStatus, loadingIssues, loadingMore } =
      get();
    if (loadingIssues || loadingMore) return;
    if (issues.length >= issuesTotal) return; // everything loaded

    set({ loadingMore: true });
    const res = await apiRequest<DownTimePage>(
      pagePath(issuesStatus, issues.length),
    );
    if (res.ok) {
      set({
        issues: [...issues, ...(res.data?.items ?? [])],
        issuesTotal: res.data?.total ?? issuesTotal,
        loadingMore: false,
      });
    } else {
      set({ loadingMore: false });
    }
  },

  getIssue: (id) => apiRequest<DownTime>(`/down-times/${id}`),
  createDownTime: async (payload) => {
    set({ conflict: null });
    const res = await apiRequest<{ job_id: string }>(
      "/down-times",
      "POST",
      payload,
    );
    // 409 = a downtime is already open on the target or one of its ancestors.
    // The backend `detail` is a structured object (spec §4) — read its fields,
    // never the English sentence it also carries.
    if (!res.ok && res.status === 409) {
      set({ conflict: readDownTimeConflict(res.detailBody) });
    }
    return res;
  },
  clearConflict: () => set({ conflict: null }),
  acknowledge: (id) =>
    apiRequest<DownTime>(`/down-times/${id}/acknowledge`, "POST"),
  resolve: (id) => apiRequest<DownTime>(`/down-times/${id}/resolve`, "POST"),
  close: (id) => apiRequest<DownTime>(`/down-times/${id}/close`, "POST"),
  reject: (id) =>
    apiRequest<DownTime>(`/down-times/${id}/reject-resolution`, "POST"),
  remove: (id) => apiRequest<DownTime>(`/down-times/${id}`, "DELETE"),
}));
