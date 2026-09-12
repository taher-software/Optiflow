import {
  PERIOD_DAYS,
  type DailyPoint,
  type PeriodPreset,
  type ShiftWindow,
  type StatsMetric,
} from "../constants/dashboard";

/** Heure « HH:MM » du backend → libellé lisible : "14:00" → "14h",
 * "06:30" → "06h30". `null` si l'entrée n'est pas une heure valide. Pure. */
export function formatClockTime(time: string): string | null {
  const match = /^(\d{2}):(\d{2})$/.exec(time);
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) return null;
  return minutes === 0 ? `${match[1]}h` : `${match[1]}h${match[2]}`;
}

/** Fenêtre d'équipe → plage lisible : "06h–14h", "22h30–06h30" (tiret
 * demi-cadratin). `null` dès qu'une borne est illisible. Pure. */
export function formatShiftWindow(shift: ShiftWindow): string | null {
  const start = formatClockTime(shift.start_time);
  const end = formatClockTime(shift.end_time);
  if (start === null || end === null) return null;
  return `${start}–${end}`;
}

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

/** Bornes ISO [from..to] de la période courante. Un préréglage se termine
 * toujours aujourd'hui ; seule la période « custom » peut ne pas contenir le
 * jour courant. */
export function periodRange(
  period: PeriodPreset,
  from: string,
  to: string,
): { from: string; to: string } {
  if (period === "custom") return { from, to };
  const days = PERIOD_DAYS[period];
  const today = isoToday();
  return { from: isoDayAfter(today, -(days - 1)), to: today };
}

/** Jour à passer au gantt (`?day=`) depuis la période du dashboard, ou `null`
 * quand la période contient aujourd'hui.
 *
 * Le gantt est un écran d'UN jour, par conception : il ne peut pas porter une
 * plage. Atterrir sur aujourd'hui alors que le lecteur regarde le mois dernier
 * serait un mensonge silencieux, donc on emmène la BORNE DE FIN de la période —
 * le jour le plus récent qu'il regardait. Si la période contient aujourd'hui,
 * `null` : le gantt résout alors lui-même le jour de production courant dans le
 * fuseau du site (jamais celui du navigateur). Pure hors horloge. */
export function ganttDayParam(
  period: PeriodPreset,
  customFrom: string,
  customTo: string,
): string | null {
  const { from, to } = periodRange(period, customFrom, customTo);
  const today = isoToday();
  return from <= today && today <= to ? null : to;
}

/** Agrégat d'un épisode pour la métrique choisie. Pur.
 *
 * `duration` et `count` se cumulent. `mttr` ne se cumule PAS : c'est déjà une
 * moyenne, donc l'épisode vaut la moyenne de ses jours. Le backend renvoie un
 * point par jour du calendrier et pose `0` les jours sans arrêt clôturé
 * (`_mttr_seconds` → `0.0` sans ticket) : moyenner ces zéros ferait chuter le
 * MTTR à mesure que la période s'allonge et comparerait des durées d'épisode
 * plutôt que des délais de réparation. Seuls les jours effectivement réparés
 * (valeur > 0) entrent donc dans la moyenne. */
export function episodeAggregate(
  points: readonly DailyPoint[],
  metric: StatsMetric,
): number {
  if (metric !== "mttr") return points.reduce((sum, p) => sum + p.value, 0);
  const repaired = points.filter((p) => p.value > 0);
  if (repaired.length === 0) return 0;
  return repaired.reduce((sum, p) => sum + p.value, 0) / repaired.length;
}

/** Comparaison de deux épisodes : lequel est le plus récent, leurs agrégats,
 * et l'écart relatif du plus récent par rapport à l'autre. Pure.
 *
 * L'épisode le plus récent est celui dont la période se termine le plus tard
 * (`to` seul ; à `to` égal, l'épisode 1). L'écart vaut
 * `(récent − référence) / référence` — la référence (l'épisode le plus ancien)
 * est toujours le dénominateur, quel que soit l'ordre d'affichage des cartes.
 * `null` quand la référence est nulle : l'écart est alors indéfini, jamais
 * « 0 % ». */
export function compareEpisodes(
  episode1: { points: readonly DailyPoint[]; to: string },
  episode2: { points: readonly DailyPoint[]; to: string },
  metric: StatsMetric,
): {
  total1: number;
  total2: number;
  latestIsEp1: boolean;
  latest: number;
  reference: number;
  gapPct: number | null;
} {
  const total1 = episodeAggregate(episode1.points, metric);
  const total2 = episodeAggregate(episode2.points, metric);

  const latestIsEp1 = episode1.to >= episode2.to;

  const latest = latestIsEp1 ? total1 : total2;
  const reference = latestIsEp1 ? total2 : total1;

  return {
    total1,
    total2,
    latestIsEp1,
    latest,
    reference,
    gapPct: reference === 0 ? null : ((latest - reference) / reference) * 100,
  };
}

/** Part d'une tranche dans son total, 0..1. `null` quand le total est nul ou
 * illisible : la part est alors indéfinie, jamais « 0 % ». Pure. */
export function shareOf(part: number, total: number): number | null {
  if (!Number.isFinite(part) || !Number.isFinite(total) || total <= 0) {
    return null;
  }
  return part / total;
}

/** Part 0..1 → pourcentage lisible et borné : "45 %". "–" si indéfinie. Pure. */
export function formatShare(share: number | null): string {
  if (share === null) return "–";
  return `${Math.round(Math.min(1, Math.max(0, share)) * 100)} %`;
}
