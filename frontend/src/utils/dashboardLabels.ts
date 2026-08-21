import type { DimensionKind, ShiftWindow } from "../constants/dashboard";
import { formatShiftWindow } from "./dashboardFormat";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** Libellé affichable d'une entité de dimension : les endroits gardent leur
 * nom propre ; shift / process / type sont traduits depuis leur id. Pure.
 *
 * Les horaires d'une équipe viennent des fenêtres réelles du tenant
 * (`namespace.shifts` — spec §3), jamais d'une table codée en dur. Quand la
 * fenêtre est absente ou illisible, le libellé retombe sur « Équipe N » seul,
 * sans parenthèses. */
export function dimensionLabel(
  t: Translate,
  kind: DimensionKind,
  id: string,
  label: string,
  shifts?: readonly ShiftWindow[],
): string {
  if (kind === "shift") {
    const window = shifts?.find((s) => s.id === id);
    const hours = window ? formatShiftWindow(window) : null;
    return t("dashboard.shiftN", { n: id }) + (hours ? ` (${hours})` : "");
  }
  if (kind === "process") return t(`dashboard.process.${id}`);
  if (kind === "type") return t(`dashboard.types.${id}`);
  return label;
}
