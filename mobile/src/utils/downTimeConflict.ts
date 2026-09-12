import { PRODUCTION_SCOPES, type ProductionScope } from "../constants/downtime";

/**
 * The production level the blocking ticket was declared at. `"unknown"` is the
 * fallback for a 409 body that doesn't carry a recognised `blocking_scope`
 * (an older backend, or a proxy that rewrote the error).
 */
export type ConflictLevel = ProductionScope | "unknown";

/** A declaration refused with 409 because that level is already down. */
export interface DownTimeConflict {
  /** Level the blocking ticket lives at (plant / uap / line / workstation). */
  level: ConflictLevel;
  /** Id of the ticket that is already open, when the body carried one. */
  ticketId: string | null;
}

/** Stable `code` token the backend puts on this 409 (spec §4). */
export const DOWNTIME_ALREADY_OPEN = "downtime_already_open";

/**
 * The structured 409 `detail` of `POST /down-times`
 * (`down_time/services.py::_conflict_detail`, spec §4). `message` is the
 * backend's English sentence, kept for API explorers — the app localises
 * `blocking_scope` itself and never reads it.
 */
interface ConflictDetailBody {
  code?: unknown;
  blocking_scope?: unknown;
  blocking_ticket_id?: unknown;
}

const SCOPES: readonly string[] = PRODUCTION_SCOPES;

function toLevel(scope: unknown): ConflictLevel {
  return typeof scope === "string" && SCOPES.includes(scope)
    ? (scope as ProductionScope)
    : "unknown";
}

function toTicketId(id: unknown): string | null {
  if (typeof id !== "string") return null;
  const trimmed = id.trim();
  return trimmed === "" ? null : trimmed;
}

/**
 * Read the backend's structured 409 `detail` into the conflict the UI
 * localises itself. `detail` is whatever the error body carried, so it is
 * typed `unknown` on purpose: an unexpected shape (older backend, proxy
 * rewriting the error to a plain string) still yields a conflict — at the
 * `"unknown"` level and without a ticket link — rather than a generic error.
 */
export function readDownTimeConflict(detail: unknown): DownTimeConflict {
  if (typeof detail !== "object" || detail === null) {
    return { level: "unknown", ticketId: null };
  }
  const body = detail as ConflictDetailBody;
  return {
    level: toLevel(body.blocking_scope),
    ticketId: toTicketId(body.blocking_ticket_id),
  };
}
