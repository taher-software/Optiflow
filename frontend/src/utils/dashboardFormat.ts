import type { StatsMetric } from "../constants/dashboard";

/** Durée humaine : "45 min", "2 h 05", "1 j 3 h". Pure. */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "–";
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ${String(m % 60).padStart(2, "0")}`;
  const d = Math.floor(h / 24);
  return `${d} j ${h % 24} h`;
}

/** Ratio 0..1 → "97,3 %". Pure. */
export function formatPercent(ratio: number): string {
  if (!Number.isFinite(ratio)) return "–";
  return `${(ratio * 100).toFixed(1).replace(".", ",")} %`;
}

/** Valeur d'une métrique stats pour l'affichage. */
export function formatMetric(value: number, metric: StatsMetric): string {
  return metric === "count" ? String(value) : formatDuration(value);
}

/** Nuance d'une rampe séquentielle : intensité ∝ ratio valeur/max
 * (seuils du spec : 0.8 / 0.55 / 0.3). Pure. */
export function shade(ramp: readonly string[], ratio: number): string {
  if (ratio > 0.8) return ramp[0];
  if (ratio > 0.55) return ramp[1];
  if (ratio > 0.3) return ramp[2];
  return ramp[3];
}

/** Jours couverts par [from..to] inclus (1 min ; bornes invalides → 1). */
export function daysBetween(from: string, to: string): number {
  const a = new Date(from).getTime();
  const b = new Date(to).getTime();
  if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return 1;
  return Math.floor((b - a) / 86_400_000) + 1;
}

/** ISO (YYYY-MM-DD) du jour `offset` après `from`. */
export function isoDayAfter(from: string, offset: number): string {
  const d = new Date(new Date(from).getTime() + offset * 86_400_000);
  return d.toISOString().slice(0, 10);
}

/** Aujourd'hui en ISO (YYYY-MM-DD). */
export function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}
