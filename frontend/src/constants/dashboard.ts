/** KPI dashboard domain — types, dimensions et système de couleurs.
 *
 * Réfs contractuelles : `.claude/specs/kpi-dashboard.md` (règles + contrat
 * des endpoints `/kpi/*` que ces types miroitent exactement). */

/** Les 4 KPIs de tête, calculés pour n'importe quelle tranche.
 * La disponibilité a été supprimée en révision 2 (spec §5bis.3). */
export interface Kpis {
  /** Somme pondérée par poste de travail (spec §5bis.1bis). */
  downtime_seconds: number;
  count: number;
  mttr_seconds: number;
  /** `null` quand le temps planifié est inconnu (pas de dénominateur). */
  mtbf_seconds: number | null;
}

/** Dimensions d'analyse. Une sélection n'est jamais décortiquée par la sienne. */
export type DimensionKind =
  "shift" | "uap" | "line" | "station" | "process" | "type";

/** Un cran du chemin de drill-down (fil d'Ariane). */
export interface DrillStep {
  kind: DimensionKind;
  id: string;
  /** Libellé affichable (noms propres pour les endroits ; les dimensions
   * énumérées — shift/process/type — sont traduites via i18n depuis `id`). */
  label: string;
}

/** Une rangée de décorticage, cliquable, temps d'arrêt en valeur principale. */
export interface BreakdownRow {
  kind: DimensionKind;
  id: string;
  label: string;
  kpis: Kpis;
}

/** Rangée du Pareto processus : part du volume + cumul. */
export interface ParetoRow {
  id: string;
  label: string;
  /** Part 0..1 du volume total. */
  share: number;
  /** Cumul 0..1 (les rangées sont triées décroissantes). */
  cumulative: number;
}

/** Barre compacte d'une section analytique (valeur en secondes ou en nombre). */
export interface Bar {
  id: string;
  label: string;
  value: number;
}

/** Méta tenant qui pilote les décorticages conditionnels. */
export interface NamespaceMeta {
  name: string;
  shift_number: number;
  uap_count: number;
  line_count: number;
  station_count: number;
}

/** Payload plein écran du dashboard (mirror du futur GET /kpi/dashboard). */
export interface DashboardData {
  namespace: NamespaceMeta;
  overall: Kpis;
  by_shift: BreakdownRow[];
  by_location: BreakdownRow[];
  pareto_by_process: ParetoRow[];
  repair_by_process: Bar[];
  by_type: BreakdownRow[];
}

/** Payload du drill-down (mirror du futur GET /kpi/drilldown). Le producteur
 * applique « jamais sa propre dimension » : les sections absentes sont omises. */
export interface DrilldownData {
  kpis: Kpis;
  /** Endroits du niveau hiérarchique suivant (UAP→lignes→postes). */
  children: BreakdownRow[] | null;
  /** Sous-titre expliquant le niveau des enfants (ex. « cette UAP n'a pas de
   * lignes — postes directement »), clé i18n. */
  children_hint_key: string | null;
  pareto_by_process?: ParetoRow[];
  repair_by_process?: Bar[];
  downtime_by_shift?: Bar[];
  downtime_by_type?: Bar[];
  mttr_by_agent?: Bar[];
  count_by_agent?: Bar[];
}

/** Point du suivi journalier (mirror du futur GET /kpi/daily). */
export interface DailyPoint {
  /** ISO date (YYYY-MM-DD). */
  date: string;
  value: number;
}

export type StatsMetric = "duration" | "count" | "mttr";
export type StatsMode = "follow" | "compare";

/** Filtres d'un suivi ou d'un épisode de comparaison. */
export interface StatsFilters {
  /** id de scope ("" = usine entière). */
  scope_kind: "plant" | "uap" | "line" | "station";
  scope_id: string;
  /** "" = tous les processus. */
  process: string;
  /** "" = toutes les équipes, sinon "1" | "2" | "3". */
  shift: string;
  from: string;
  to: string;
}

export type PeriodPreset = "today" | "7d" | "30d" | "custom";
export const PERIOD_PRESETS: PeriodPreset[] = ["today", "7d", "30d", "custom"];
export const PERIOD_DAYS: Record<Exclude<PeriodPreset, "custom">, number> = {
  today: 1,
  "7d": 7,
  "30d": 30,
};

/* ---------------- Système de couleurs (spec §1 — NE PAS improviser) -------- */
/** La couleur encode la MÉTRIQUE. Rampes « intensité ∝ volume » (forte→faible). */
export const RAMP_DOWNTIME = [
  "#dc2626",
  "#ef4444",
  "#f87171",
  "#fca5a5",
] as const;
export const RAMP_COUNT = ["#6d28d9", "#7c3aed", "#8b5cf6", "#a78bfa"] as const;
export const RAMP_REPAIR = [
  "#059669",
  "#10b981",
  "#34d399",
  "#6ee7b9",
] as const;
/** Comparaison d'épisodes — paire validée CVD ; ne pas remplacer le bleu. */
export const COLOR_EP1 = "#dc2626";
export const COLOR_EP2 = "#2563eb";

export const METRIC_COLOR: Record<StatsMetric, string> = {
  duration: RAMP_DOWNTIME[0],
  count: RAMP_COUNT[1],
  mttr: RAMP_REPAIR[0],
};

/* ---------------- Dimensions énumérées ------------------------------------ */
export const PROCESS_IDS = [
  "maintenance",
  "production",
  "quality",
  "logistic",
] as const;

export const TYPE_IDS = [
  "break_down",
  "quality_issue",
  "absenteeism",
  "wip_shortage",
  "material_shortage",
  "setup_changeover",
  "others",
] as const;

/** Processus *habituel* d'un type d'arrêt — miroir exact de `DOWNTIME_TYPE_PROCESS`
 * (`backend/src/app/globals/enum/process.py`). Depuis la révision 2 (§5bis.7) le
 * processus est lu sur le ticket lui-même ; cette table n'est plus qu'un repli pour
 * les documents hérités, donc une tranche « type » peut couvrir plusieurs processus.
 * `setup_changeover` en est volontairement absent : son processus est choisi à la
 * déclaration et varie d'un ticket à l'autre. */
export const TYPE_PROCESS: Record<string, string> = {
  break_down: "maintenance",
  quality_issue: "quality",
  absenteeism: "production",
  wip_shortage: "production",
  material_shortage: "logistic",
  others: "production",
};

export const SHIFT_IDS = ["1", "2", "3"] as const;
/** Fenêtres horaires d'affichage des équipes (mock — viendra des settings). */
export const SHIFT_HOURS: Record<string, string> = {
  "1": "06h–14h",
  "2": "14h–22h",
  "3": "22h–06h",
};
