/** Mock déterministe du contrat `/kpi/*` (spec §5) — à remplacer par les
 * vrais fetchs dans les stores quand le backend existera. Les nombres sont
 * seedés par clé pour rester stables entre rendus. La hiérarchie contient
 * volontairement une UAP SANS lignes (règle du saut direct aux postes). */

import type {
  Bar,
  BreakdownRow,
  DailyPoint,
  DashboardData,
  DimensionKind,
  DrilldownData,
  DrillStep,
  Kpis,
  ParetoRow,
  StatsFilters,
  StatsMetric,
} from "../constants/dashboard";
import { PROCESS_IDS, SHIFT_IDS, TYPE_IDS } from "../constants/dashboard";
import { daysBetween, isoDayAfter } from "./dashboardFormat";

/* ---------------- PRNG seedé ---------------- */
function hashSeed(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
function rng(seed: string): () => number {
  let a = hashSeed(seed);
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ---------------- Hiérarchie fictive ---------------- */
interface MockLine {
  id: string;
  name: string;
  stations: { id: string; name: string }[];
}
interface MockUap {
  id: string;
  name: string;
  lines: MockLine[];
  /** Postes directs quand l'UAP n'a pas de lignes. */
  stations: { id: string; name: string }[];
}

function st(id: string): { id: string; name: string } {
  return { id, name: `Poste ${id}` };
}

const UAPS: MockUap[] = [
  {
    id: "uap-1",
    name: "UAP 1 — Câblage",
    lines: [
      {
        id: "c1",
        name: "Ligne C1",
        stations: ["C1-01", "C1-02", "C1-03", "C1-04"].map(st),
      },
      {
        id: "c2",
        name: "Ligne C2",
        stations: ["C2-01", "C2-02", "C2-03"].map(st),
      },
    ],
    stations: [],
  },
  {
    id: "uap-2",
    name: "UAP 2 — Assemblage",
    lines: [
      { id: "a1", name: "Ligne A1", stations: ["A1-01", "A1-02"].map(st) },
      {
        id: "a2",
        name: "Ligne A2",
        stations: ["A2-01", "A2-02", "A2-03"].map(st),
      },
      { id: "a3", name: "Ligne A3", stations: ["A3-01", "A3-02"].map(st) },
    ],
    stations: [],
  },
  {
    id: "uap-3",
    name: "UAP 3 — Injection",
    lines: [], // pas de lignes : le drill saute directement aux postes
    stations: ["F-01", "F-02", "F-03"].map(st),
  },
];

const AGENTS = [
  { id: "ag-1", name: "Y. Bennani" },
  { id: "ag-2", name: "S. Alaoui" },
  { id: "ag-3", name: "M. Idrissi" },
  { id: "ag-4", name: "K. Fassi" },
  { id: "ag-5", name: "R. Tazi" },
];

/* ---------------- Générateurs ---------------- */
function kpisFor(key: string, days: number): Kpis {
  const r = rng(key);
  const downtime = Math.round((3600 * 1.5 + r() * 3600 * 5) * days);
  const count = Math.max(1, Math.round((2 + r() * 7) * days));
  return {
    downtime_seconds: downtime,
    count,
    mttr_seconds: Math.round(downtime / count),
    mtbf_seconds: Math.round(3600 * 6 + r() * 3600 * 18),
    availability: 0.9 + r() * 0.099,
  };
}

function rowsFor(
  kind: DimensionKind,
  items: { id: string; label: string }[],
  seed: string,
  days: number,
): BreakdownRow[] {
  return items.map((i) => ({
    kind,
    id: i.id,
    label: i.label,
    kpis: kpisFor(`${seed}:${kind}:${i.id}`, days),
  }));
}

function paretoFor(seed: string): ParetoRow[] {
  const r = rng(`${seed}:pareto`);
  const raw = PROCESS_IDS.map((id) => ({ id, v: 0.1 + r() }));
  const total = raw.reduce((s, i) => s + i.v, 0);
  const sorted = raw
    .map((i) => ({ id: i.id, share: i.v / total }))
    .sort((a, b) => b.share - a.share);
  let cumul = 0;
  return sorted.map((i) => {
    cumul += i.share;
    return { id: i.id, label: i.id, share: i.share, cumulative: cumul };
  });
}

function barsFor(
  items: { id: string; label: string }[],
  seed: string,
  base: number,
  spread: number,
): Bar[] {
  const r = rng(seed);
  return items
    .map((i) => ({
      id: i.id,
      label: i.label,
      value: Math.round(base + r() * spread),
    }))
    .sort((a, b) => b.value - a.value);
}

const shiftItems = SHIFT_IDS.map((id) => ({ id, label: id }));
const processItems = PROCESS_IDS.map((id) => ({ id, label: id }));
const typeItems = TYPE_IDS.map((id) => ({ id, label: id }));

/* ---------------- API mock : dashboard ---------------- */
export function mockDashboard(from: string, to: string): DashboardData {
  const days = daysBetween(from, to);
  const seed = `dash:${from}:${to}`;
  return {
    namespace: {
      name: "Usine de Casablanca",
      shift_number: 3,
      uap_count: UAPS.length,
      line_count: UAPS.reduce((s, u) => s + u.lines.length, 0),
      station_count: UAPS.reduce(
        (s, u) =>
          s +
          (u.lines.length
            ? u.lines.reduce((x, l) => x + l.stations.length, 0)
            : u.stations.length),
        0,
      ),
    },
    overall: kpisFor(`${seed}:overall`, days),
    by_shift: rowsFor("shift", shiftItems, seed, days),
    by_location: rowsFor(
      "uap",
      UAPS.map((u) => ({ id: u.id, label: u.name })),
      seed,
      days,
    ),
    pareto_by_process: paretoFor(seed),
    repair_by_process: barsFor(
      processItems,
      `${seed}:repair`,
      3600 * 20,
      3600 * 130,
    ),
    by_type: rowsFor("type", typeItems, seed, days),
  };
}

/* ---------------- API mock : drill-down ---------------- */
function childrenOf(step: DrillStep): {
  rows: { id: string; label: string }[];
  kind: DimensionKind;
  hintKey: string;
} | null {
  if (step.kind === "uap") {
    const uap = UAPS.find((u) => u.id === step.id);
    if (!uap) return null;
    return uap.lines.length
      ? {
          kind: "line",
          rows: uap.lines.map((l) => ({ id: l.id, label: l.name })),
          hintKey: "dashboard.drill.linesHint",
        }
      : {
          kind: "station",
          rows: uap.stations.map((s) => ({ id: s.id, label: s.name })),
          hintKey: "dashboard.drill.noLinesHint",
        };
  }
  if (step.kind === "line") {
    const line = UAPS.flatMap((u) => u.lines).find((l) => l.id === step.id);
    if (!line) return null;
    return {
      kind: "station",
      rows: line.stations.map((s) => ({ id: s.id, label: s.name })),
      hintKey: "dashboard.drill.stationsHint",
    };
  }
  if (
    step.kind === "shift" ||
    step.kind === "type" ||
    step.kind === "process"
  ) {
    // Premier niveau de localisation applicable (l'usine mock a des UAP).
    return {
      kind: "uap",
      rows: UAPS.map((u) => ({ id: u.id, label: u.name })),
      hintKey: "dashboard.drill.locationsHint",
    };
  }
  return null; // station : feuille
}

/** Le producteur applique « jamais sa propre dimension » : toute dimension
 * du chemin (ou fixée par un filtre) est absente des sections retournées. */
export function mockDrilldown(
  path: DrillStep[],
  procFilter: string,
  shiftFilter: string,
  from: string,
  to: string,
): DrilldownData {
  const days = daysBetween(from, to);
  const seed = `drill:${path.map((s) => `${s.kind}=${s.id}`).join(">")}:${procFilter}:${shiftFilter}:${from}:${to}`;
  const current = path[path.length - 1];
  const inPath = (k: DimensionKind) => path.some((s) => s.kind === k);

  const ch = childrenOf(current);
  const data: DrilldownData = {
    kpis: kpisFor(`${seed}:kpis`, days),
    children: ch ? rowsFor(ch.kind, ch.rows, seed, days) : null,
    children_hint_key: ch ? ch.hintKey : null,
  };

  if (current.kind === "process") {
    data.mttr_by_agent = barsFor(
      AGENTS.map((a) => ({ id: a.id, label: a.name })),
      `${seed}:ag-mttr`,
      900,
      4800,
    );
    data.count_by_agent = barsFor(
      AGENTS.map((a) => ({ id: a.id, label: a.name })),
      `${seed}:ag-count`,
      1,
      9 * days,
    );
    return data;
  }

  const typeFixesProcess = inPath("type"); // un type est toujours lié à un processus
  if (!inPath("process") && !typeFixesProcess && procFilter === "") {
    data.pareto_by_process = paretoFor(seed);
    data.repair_by_process = barsFor(
      processItems,
      `${seed}:repair`,
      3600 * 4,
      3600 * 30,
    );
  }
  if (!inPath("shift") && shiftFilter === "") {
    data.downtime_by_shift = barsFor(
      shiftItems,
      `${seed}:shift`,
      1800,
      3600 * 2,
    );
  }
  if (!inPath("type")) {
    data.downtime_by_type = barsFor(
      typeItems.slice(0, 5),
      `${seed}:type`,
      900,
      3600 * 2,
    );
  }
  return data;
}

/* ---------------- API mock : suivi journalier ---------------- */
export function mockDaily(
  metric: StatsMetric,
  filters: StatsFilters,
): DailyPoint[] {
  const n = Math.min(62, daysBetween(filters.from, filters.to));
  const key = `daily:${metric}:${filters.scope_kind}:${filters.scope_id}:${filters.process}:${filters.shift}:${filters.from}`;
  const r = rng(key);
  return Array.from({ length: n }, (_, i) => ({
    date: isoDayAfter(filters.from, i),
    value: Math.round(
      metric === "count"
        ? 2 + r() * 8
        : metric === "mttr"
          ? 1200 + r() * 3600
          : 3600 * 1.5 + r() * 3600 * 5,
    ),
  }));
}

/** Options de scope proposées par l'explorateur (usine + endroits). */
export function mockScopeOptions(): {
  kind: "plant" | "uap" | "line" | "station";
  id: string;
  label: string;
}[] {
  return [
    { kind: "plant" as const, id: "", label: "" },
    ...UAPS.map((u) => ({ kind: "uap" as const, id: u.id, label: u.name })),
    ...UAPS.flatMap((u) => u.lines).map((l) => ({
      kind: "line" as const,
      id: l.id,
      label: l.name,
    })),
    ...UAPS.flatMap((u) =>
      u.lines.length ? u.lines.flatMap((l) => l.stations) : u.stations,
    )
      .slice(0, 8)
      .map((s) => ({ kind: "station" as const, id: s.id, label: s.name })),
  ];
}
