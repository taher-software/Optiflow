import type { ProductionLine } from "../constants/productionLines";
import type { Workstation } from "../constants/workstations";

/** The resources a deletion takes down with the one being deleted.
 * Derived entirely from the lists the production-line and workstation stores
 * already hold — the API exposes no "what would this delete" endpoint. */
export interface DeletionImpact {
  lines: ProductionLine[];
  workstations: Workstation[];
}

/** An impact with nothing in it — a deletion that affects only its own target. */
export const NO_IMPACT: DeletionImpact = { lines: [], workstations: [] };

/** True when the deletion reaches beyond the resource itself. */
export function hasImpact(impact: DeletionImpact): boolean {
  return impact.lines.length > 0 || impact.workstations.length > 0;
}

/** Deleting a production area also deletes the lines attached to it and the
 * stations on those lines. A line belonging to no area, and a station on no
 * line, are never reached. */
export function uapDeletionImpact(
  uapId: string,
  lines: ProductionLine[],
  workstations: Workstation[],
): DeletionImpact {
  const ownLines = lines.filter((l) => l.uap_id === uapId);
  const ownLineIds = new Set(ownLines.map((l) => l.id));
  return {
    lines: ownLines,
    workstations: workstations.filter(
      (w) =>
        w.production_line_id !== null && ownLineIds.has(w.production_line_id),
    ),
  };
}

/** Deleting a production line also deletes the stations on it. */
export function lineDeletionImpact(
  lineId: string,
  workstations: Workstation[],
): DeletionImpact {
  return {
    lines: [],
    workstations: workstations.filter((w) => w.production_line_id === lineId),
  };
}
