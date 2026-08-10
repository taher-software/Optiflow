/** A downtime issue as returned by the backend (mirrors DownTimeOut). */
export interface DownTime {
  id: string;
  namespace_id: string;
  created_at: string;
  updated_at: string;
  down_time_scope: string;
  uap_id: string | null;
  production_line_id: string | null;
  workstation_id: string | null;
  down_time_type: string;
  department: string | null;
  process: string;
  status: DownTimeStatus;
  created_by: string;
  created_by_name: string | null;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  acknowledged_by_name: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  resolved_by_name: string | null;
  closed_at: string | null;
  closed_by: string | null;
  closed_by_name: string | null;
  can_acknowledge: boolean;
  can_resolve: boolean;
  can_close: boolean;
  can_delete: boolean;
  time_in_status_seconds: number | null;
}

export type DownTimeStatus = "pending" | "ongoing" | "resolved" | "closed";

/** Display metadata (icon + accent color) per status. */
export const STATUS_META: Record<
  DownTimeStatus,
  { emoji: string; color: string }
> = {
  pending: { emoji: "⏳", color: "#fbbf24" },
  ongoing: { emoji: "🔧", color: "#38bdf8" },
  resolved: { emoji: "✅", color: "#34d399" },
  closed: { emoji: "🔒", color: "#94a3b8" },
};

export const DOWN_TIME_STATUSES: DownTimeStatus[] = [
  "pending",
  "ongoing",
  "resolved",
  "closed",
];

/** Per-status card metrics (mirrors DownTimeSummaryOut). */
export interface DownTimeStatusSummary {
  count: number;
  average_seconds: number | null;
}

export interface DownTimeSummary {
  pending: DownTimeStatusSummary;
  ongoing: DownTimeStatusSummary;
  resolved: DownTimeStatusSummary;
  closed: DownTimeStatusSummary;
}

/** A page of downtime issues (mirrors the backend DownTimePageOut). */
export interface DownTimePage {
  items: DownTime[];
  total: number;
  limit: number;
  offset: number;
}

/** Production scope of a downtime declaration. */
export const PRODUCTION_SCOPES = [
  "plant",
  "uap",
  "production line",
  "work station",
] as const;
export type ProductionScope = (typeof PRODUCTION_SCOPES)[number];

/** Downtime root-cause types (mirror the backend DownTimeType enum). */
export const DOWN_TIME_TYPES = [
  "break down",
  "quality issue",
  "Absenteeism",
  "Work-in-Process (WIP) Shortage",
  "Material / Component Shortage",
  "Setup / Changeover",
  "others",
] as const;
export type DownTimeType = (typeof DOWN_TIME_TYPES)[number];

export const SETUP_CHANGEOVER: DownTimeType = "Setup / Changeover";

/**
 * Types whose ticket skips acknowledge/resolve: they go straight from
 * `pending` to `closed`, and only a production agent may close them (mirrors
 * the backend `CLOSE_ONLY_DOWNTIME_TYPES`).
 */
export const CLOSE_ONLY_TYPES: readonly DownTimeType[] = [
  "Work-in-Process (WIP) Shortage",
  "others",
];

export function isCloseOnly(downTimeType: string): boolean {
  return (CLOSE_ONLY_TYPES as readonly string[]).includes(downTimeType);
}

/** Departments a Setup / Changeover can be routed to. */
export const SETUP_DEPARTMENTS = ["production", "maintenance"] as const;
export type SetupDepartment = (typeof SETUP_DEPARTMENTS)[number];

/** Payload for POST /down-times. */
export interface CreateDownTimePayload {
  production_scope: ProductionScope;
  uap_id?: string | null;
  production_line_id?: string | null;
  workstation_id?: string | null;
  down_time_type: DownTimeType;
  department?: SetupDepartment | null;
}

/** i18n-safe key slug for an enum value ("break down" -> "break_down"). */
export function slug(value: string): string {
  return value.replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

/** Human string for a duration in seconds, or "-" when null. */
export function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds < 0) return "-";
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}
