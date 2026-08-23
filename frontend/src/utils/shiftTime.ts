import type { ShiftTime } from "../constants/settings";

/** One shift as edited in the Settings form. Empty string = not filled in.
 * Break times are a all-or-nothing pair: both filled, or both empty. */
export interface ShiftDraft {
  start_time: string;
  end_time: string;
  break_start_time: string;
  break_end_time: string;
}

/** Why a shift draft is not submittable. `null` means it is valid. */
export type ShiftDraftError =
  | "missingWindow"
  | "zeroLengthWindow"
  | "breakIncomplete"
  | "breakOutsideWindow"
  | "breakLength";

const MINUTES_PER_DAY = 1440;

/** Minutes since midnight for a `"HH:MM"` clock string, or `null` if unparsable. */
function toMinutes(value: string): number | null {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) return null;
  return hours * 60 + minutes;
}

/** Forward distance in minutes from `from` to `to`, wrapping over midnight. */
function forwardSpan(from: number, to: number): number {
  return (to - from + MINUTES_PER_DAY) % MINUTES_PER_DAY;
}

/** Validates a shift draft the way the backend does: the clock window is
 * mandatory and of non-zero length, the break pair is all-or-nothing, and the
 * break must fall inside
 * the window (bounds included, midnight-crossing windows supported) with a
 * non-zero length strictly shorter than the window. */
export function validateShiftDraft(draft: ShiftDraft): ShiftDraftError | null {
  const start = toMinutes(draft.start_time);
  const end = toMinutes(draft.end_time);
  if (start === null || end === null) return "missingWindow";
  // The backend rejects a window whose ends coincide (`_reject_zero_length`);
  // never read it as a full day here, or the form would submit a payload the
  // server answers with a 422 the user cannot act on.
  if (start === end) return "zeroLengthWindow";

  const hasBreakStart = draft.break_start_time !== "";
  const hasBreakEnd = draft.break_end_time !== "";
  if (!hasBreakStart && !hasBreakEnd) return null;
  if (!hasBreakStart || !hasBreakEnd) return "breakIncomplete";

  const breakStart = toMinutes(draft.break_start_time);
  const breakEnd = toMinutes(draft.break_end_time);
  if (breakStart === null || breakEnd === null) return "breakIncomplete";

  const windowSpan = forwardSpan(start, end);
  const breakSpan = forwardSpan(breakStart, breakEnd);
  if (breakSpan === 0 || breakSpan >= windowSpan) return "breakLength";

  const offset = forwardSpan(start, breakStart);
  if (offset + breakSpan > windowSpan) return "breakOutsideWindow";
  return null;
}

/** The `ShiftTime` to send for a draft, or `null` when the shift is not
 * declared. The break pair is never half-sent: both times or two `null`s. */
export function toShiftTime(draft: ShiftDraft): ShiftTime | null {
  if (draft.start_time === "" || draft.end_time === "") return null;
  const hasBreak = draft.break_start_time !== "" && draft.break_end_time !== "";
  return {
    start_time: draft.start_time,
    end_time: draft.end_time,
    break_start_time: hasBreak ? draft.break_start_time : null,
    break_end_time: hasBreak ? draft.break_end_time : null,
  };
}
