/** The clock window of a single work shift ("HH:MM" 24h). */
export interface ShiftTime {
  start_time: string;
  end_time: string;
}

/** Plant settings of a namespace as returned by the API (mirrors
 * NamespaceSettingsOut). */
export interface NamespaceSettings {
  namespace_id: string;
  shift_number: number;
  shift_1: ShiftTime | null;
  shift_2: ShiftTime | null;
  shift_3: ShiftTime | null;
  time_to_escalate: number;
}

/** Payload for POST /settings (create) — the full settings document. */
export interface SaveSettingsPayload {
  shift_number: number;
  shift_1: ShiftTime | null;
  shift_2: ShiftTime | null;
  shift_3: ShiftTime | null;
  time_to_escalate: number;
}

/** Default escalation delay: 30 minutes, in seconds (matches the backend). */
export const DEFAULT_TIME_TO_ESCALATE = 1800;

/** Only shift_1 / shift_2 / shift_3 exist. */
export const MAX_SHIFTS = 3;

/** Shift-count options for the picker. */
export const SHIFT_NUMBERS = [1, 2, 3] as const;
