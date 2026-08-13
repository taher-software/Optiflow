import type { DimensionKind } from "../constants/dashboard";
import { SHIFT_HOURS } from "../constants/dashboard";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** Libellé affichable d'une entité de dimension : les endroits gardent leur
 * nom propre ; shift / process / type sont traduits depuis leur id. Pure. */
export function dimensionLabel(
  t: Translate,
  kind: DimensionKind,
  id: string,
  label: string,
): string {
  if (kind === "shift") {
    const hours = SHIFT_HOURS[id];
    return t("dashboard.shiftN", { n: id }) + (hours ? ` (${hours})` : "");
  }
  if (kind === "process") return t(`dashboard.process.${id}`);
  if (kind === "type") return t(`dashboard.types.${id}`);
  return label;
}
