import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import {
  RAMP_COUNT,
  RAMP_DOWNTIME,
  RAMP_REPAIR,
  type BaseKpis,
  type Kpis,
} from "../constants/dashboard";
import { ROUTES } from "../constants/routes";
import { useDashboardStore } from "../stores/useDashboardStore";
import {
  formatDuration,
  formatShare,
  ganttDayParam,
  shareOf,
} from "../utils/dashboardFormat";

/** Socle commun d'une tuile : libellé, rampe de la métrique, valeur.
 *
 * `ramp` porte la rampe séquentielle de la MÉTRIQUE (la couleur encode la
 * métrique, jamais l'entité) ; `color` en est le cran de tête, celui du
 * soulignement. Les divisions puisent dans cette même rampe : la gravité se lit
 * en intensité à l'intérieur de la métrique, pas sur une échelle de couleur
 * « gravité » qui entrerait en concurrence avec le code métrique. */
interface TileBase {
  key: string;
  ramp: readonly string[];
  color: string;
  value: (k: BaseKpis) => string;
  hintKey?: string;
}

/** Métrique ADDITIVE : goulot + critique + standard = racine. La tranche est une
 * vraie partition, donc une barre ET un pourcentage de part ont un sens — d'où
 * l'accesseur `weight`, qui n'existe que sur ce variant.
 *
 * `remainderKey` y est OBLIGATOIRE : le standard n'étant pas affiché (choix
 * assumé), goulot + critique ne font pas 100 % et la tuile doit dire où est le
 * reste, sinon le lecteur cherche le tiers manquant. */
interface AdditiveTile extends TileBase {
  weight: (k: BaseKpis) => number;
  remainderKey: string;
  captionKey?: never;
}

/** Métrique NON additive : aucun `weight` n'existe sur ce variant, donc ni la
 * barre ni le pourcentage de part n'y sont exprimables (pas seulement
 * « oubliés »). En échange, `captionKey` est obligatoire : chaque métrique
 * énonce sa propre règle de lecture. */
interface NonAdditiveTile extends TileBase {
  weight?: never;
  remainderKey?: never;
  captionKey: string;
}

type Tile = AdditiveTile | NonAdditiveTile;

const TILES: Tile[] = [
  {
    key: "downtime",
    ramp: RAMP_DOWNTIME,
    color: RAMP_DOWNTIME[0],
    value: (k) => formatDuration(k.downtime_seconds),
    weight: (k) => k.downtime_seconds,
    hintKey: "dashboard.kpi.downtimeHint",
    remainderKey: "dashboard.kpi.downtimeRemainder",
  },
  {
    key: "count",
    ramp: RAMP_COUNT,
    color: RAMP_COUNT[1],
    value: (k) => String(k.count),
    captionKey: "dashboard.kpi.countSliceHint",
  },
  {
    key: "mttr",
    ramp: RAMP_REPAIR,
    color: RAMP_REPAIR[0],
    value: (k) => formatDuration(k.mttr_seconds),
    hintKey: "dashboard.kpi.mttrHint",
    captionKey: "dashboard.kpi.mttrSliceHint",
  },
  {
    key: "mtbf",
    ramp: RAMP_REPAIR,
    color: RAMP_REPAIR[0],
    value: (k) =>
      k.mtbf_seconds === null ? "–" : formatDuration(k.mtbf_seconds),
    hintKey: "dashboard.kpi.mtbfHint",
    captionKey: "dashboard.kpi.mtbfSliceHint",
  },
];

type DivisionKey = "bottleneck" | "critical";

/** Rang de gravité, 1 = le plus grave. Un goulot étrangle tout le flux ; un
 * poste « critique » est le plus souvent doublé ou contournable. Le mot
 * « critique » suggère l'inverse de ce classement : l'ordre ne peut donc PAS
 * reposer sur les étiquettes, il est porté par le rang — ordre de rendu,
 * intensité dans la rampe, graisse, et jauge de gravité explicite. */
const SEVERITY_RANK: Record<DivisionKey, 1 | 2> = {
  bottleneck: 1,
  critical: 2,
};

/** Nombre de crans de la jauge de gravité (= nombre de divisions classées). */
const SEVERITY_STEPS = 2;

/** Une division secondaire d'une tuile (goulot ou critique). */
interface Division {
  key: DivisionKey;
  kpis: BaseKpis;
}

/** Les divisions secondaires effectivement présentes, PAR GRAVITÉ DÉCROISSANTE.
 * Une tranche `null` / absente n'est pas rendue ; une tranche à zéro l'est. */
function secondaryDivisions(kpis: Kpis): Division[] {
  const divisions: Division[] = [];
  if (kpis.bottleneck)
    divisions.push({ key: "bottleneck", kpis: kpis.bottleneck });
  if (kpis.critical) divisions.push({ key: "critical", kpis: kpis.critical });
  return divisions.sort((a, b) => SEVERITY_RANK[a.key] - SEVERITY_RANK[b.key]);
}

/** Cran de la rampe métrique attribué à un rang de gravité : le plus grave
 * prend le cran le plus dense. Pas de nouvelle échelle de couleur. */
function severityShade(ramp: readonly string[], rank: 1 | 2): string {
  return rank === 1 ? ramp[0] : ramp[2];
}

/** Jauge de gravité : deux crans, remplis jusqu'au rang. Deux pleins = le plus
 * grave. Canal purement graphique (intensité + remplissage), doublé d'un texte
 * lisible aux lecteurs d'écran — l'ordre reste ainsi explicite sans introduire
 * de code couleur « gravité ». */
function SeverityMeter({
  rank,
  ramp,
}: {
  rank: 1 | 2;
  ramp: readonly string[];
}) {
  const filled = SEVERITY_STEPS - rank + 1;
  return (
    <span className="flex shrink-0 items-center gap-[2px]" aria-hidden="true">
      {Array.from({ length: SEVERITY_STEPS }, (_, i) => (
        <span
          key={i}
          className="h-[7px] w-[3px] rounded-[1px]"
          style={{
            background: i < filled ? severityShade(ramp, rank) : "#e8e8ec",
          }}
        />
      ))}
    </span>
  );
}

/** Cible du gantt pour une division : le filtre de type, et le JOUR quand la
 * période affichée ne contient pas aujourd'hui (`ganttDayParam`). Sans cela un
 * lecteur du mois dernier atterrirait sur le gantt d'aujourd'hui sans rien
 * pour le lui dire. Le store du dashboard est la seule source de la période. */
function useGanttHref(division: DivisionKey): string {
  const period = useDashboardStore((s) => s.period);
  const customFrom = useDashboardStore((s) => s.customFrom);
  const customTo = useDashboardStore((s) => s.customTo);

  const params = new URLSearchParams({ type: division });
  const day = ganttDayParam(period, customFrom, customTo);
  if (day) params.set("day", day);
  return `${ROUTES.downTimes}?${params}`;
}

/** Libellé d'une division : jauge de gravité, nom de la division, et le rang
 * en clair pour les lecteurs d'écran.
 *
 * C'est aussi le point d'entrée vers le gantt du jour filtré sur ce type de
 * poste. Un vrai lien (et non un `onClick` sur un `div`) : il se tabule,
 * s'ouvre dans un nouvel onglet et s'annonce comme un lien. La jauge de
 * gravité, elle, ne bouge pas — même balisage, même gabarit. */
function DivisionLabel({
  division,
  ramp,
}: {
  division: Division;
  ramp: readonly string[];
}) {
  const { t } = useTranslation();
  const rank = SEVERITY_RANK[division.key];
  const label = t(`dashboard.kpi.division.${division.key}`);
  const href = useGanttHref(division.key);
  return (
    <Link
      to={href}
      title={t("dashboard.kpi.division.openGantt", { division: label })}
      className="flex min-w-0 items-center gap-1.5 rounded-sm hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0d9488]"
    >
      <SeverityMeter rank={rank} ramp={ramp} />
      <span
        className={`truncate text-[10px] uppercase tracking-wide ${
          rank === 1
            ? "font-bold text-[#6b7280]"
            : "font-semibold text-[#9ca3af]"
        }`}
      >
        {label}
      </span>
      <span className="sr-only">
        {t(`dashboard.kpi.severity.rank${rank}`)} —{" "}
        {t("dashboard.kpi.division.openGantt", { division: label })}
      </span>
    </Link>
  );
}

/** Valeur d'une division. Toujours en dessous de la division générale en taille
 * et en graisse — le chiffre de tête reste le plus gros de la tuile — et le
 * rang 1 se démarque du rang 2. */
function DivisionValue({ text, rank }: { text: string; rank: 1 | 2 }) {
  return (
    <span
      className={`text-[13px] tabular-nums ${
        rank === 1 ? "font-bold text-[#374151]" : "font-semibold text-[#6b7280]"
      }`}
    >
      {text}
    </span>
  );
}

/** Barre de part d'une tranche dans la racine — réservée aux métriques additives.
 * Part indéfinie (racine nulle) → barre vide. */
function ShareBar({ share, color }: { share: number | null; color: string }) {
  return (
    <div className="mt-1 h-[3px] w-full rounded-sm bg-[#f1f1f4]">
      <div
        className="h-full rounded-sm"
        style={{
          width: `${share === null ? 0 : Math.min(100, Math.max(0, share * 100))}%`,
          background: color,
        }}
      />
    </div>
  );
}

/** Division d'une métrique ADDITIVE. Ce composant prend un `AdditiveTile`, pas
 * un `Tile` : le pourcentage et la barre de part ne sont pas « masqués
 * ailleurs », ils sont hors d'atteinte du type non additif — passer une tuile
 * `count` / `mttr` / `mtbf` ici ne compile pas. */
function AdditiveDivisionRow({
  tile,
  division,
  root,
}: {
  tile: AdditiveTile;
  division: Division;
  root: BaseKpis;
}) {
  const { t } = useTranslation();
  const rank = SEVERITY_RANK[division.key];
  const share = shareOf(tile.weight(division.kpis), tile.weight(root));

  return (
    <div className="border-t border-[#f1f1f4] pt-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <DivisionLabel division={division} ramp={tile.ramp} />
        <span className="flex shrink-0 items-baseline gap-1.5">
          <DivisionValue text={tile.value(division.kpis)} rank={rank} />
          <span
            className="text-[11px] font-bold tabular-nums"
            title={t("dashboard.kpi.shareOfTotal")}
            style={{ color: severityShade(tile.ramp, rank) }}
          >
            {formatShare(share)}
          </span>
        </span>
      </div>
      <ShareBar share={share} color={severityShade(tile.ramp, rank)} />
    </div>
  );
}

/** Division d'une métrique NON additive : valeur seule. Aucune part n'est
 * calculable ici — le type ne porte pas de `weight`. */
function NonAdditiveDivisionRow({
  tile,
  division,
}: {
  tile: NonAdditiveTile;
  division: Division;
}) {
  const rank = SEVERITY_RANK[division.key];
  return (
    <div className="border-t border-[#f1f1f4] pt-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <DivisionLabel division={division} ramp={tile.ramp} />
        <DivisionValue text={tile.value(division.kpis)} rank={rank} />
      </div>
    </div>
  );
}

/** Aiguillage additif / non additif, fait UNE fois par tuile. Le variant est
 * capté dans une constante narrowée, si bien que chaque rangée reçoit un type
 * de tuile déjà restreint. */
function TileDivisions({
  tile,
  divisions,
  root,
}: {
  tile: Tile;
  divisions: Division[];
  root: BaseKpis;
}) {
  if (tile.weight) {
    const additive: AdditiveTile = tile;
    return (
      <div className="mt-2 space-y-1.5">
        {divisions.map((division) => (
          <AdditiveDivisionRow
            key={division.key}
            tile={additive}
            division={division}
            root={root}
          />
        ))}
      </div>
    );
  }
  const nonAdditive: NonAdditiveTile = tile;
  return (
    <div className="mt-2 space-y-1.5">
      {divisions.map((division) => (
        <NonAdditiveDivisionRow
          key={division.key}
          tile={nonAdditive}
          division={division}
        />
      ))}
    </div>
  );
}

/** Bandeau des 4 KPI (soulignement à la couleur de la métrique).
 * Chaque tuile porte jusqu'à trois divisions horizontales : générale en tête,
 * puis goulot et critique — dans cet ordre, qui est celui de la gravité.
 * `compact` : variante réduite pour le panneau drill-down. */
export function KpiCards({ kpis, compact }: { kpis: Kpis; compact?: boolean }) {
  const { t } = useTranslation();
  const divisions = secondaryDivisions(kpis);
  const hasDivisions = divisions.length > 0;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
      {TILES.map((tile) => (
        <div
          key={tile.key}
          className={`rounded-xl border border-[#e8e8ec] bg-white ${compact ? "p-3" : "p-4 shadow-sm"}`}
        >
          <p className="text-[11px] font-bold uppercase tracking-wider text-[#9ca3af]">
            {t(`dashboard.kpi.${tile.key}`)}
          </p>
          {hasDivisions && (
            <p className="mt-1.5 text-[10px] font-semibold uppercase tracking-wide text-[#9ca3af]">
              {t("dashboard.kpi.division.general")}
            </p>
          )}
          <p
            className={`font-bold tabular-nums text-[#16181d] ${hasDivisions ? "mt-0.5" : "mt-1.5"} ${compact ? "text-lg" : "text-2xl"}`}
          >
            {tile.value(kpis)}
          </p>
          <div
            className="mt-2 h-[3px] w-7 rounded-sm"
            style={{ background: tile.color }}
          />
          {hasDivisions && (
            <TileDivisions tile={tile} divisions={divisions} root={kpis} />
          )}
          {!compact && tile.hintKey && (
            <p className="mt-1 text-[11px] text-[#9ca3af]">{t(tile.hintKey)}</p>
          )}
          {/* La légende de lecture est affichée AUSSI en `compact`, contrairement à
              `hintKey`. Le drill-down est précisément l'endroit où les trois chiffres
              sont lus côte à côte, et rien d'autre ne dit pourquoi ils ne
              s'additionnent pas : un lecteur additionnerait les MTTR, compterait deux
              fois un arrêt, ou chercherait le tiers manquant des pourcentages du temps
              d'arrêt. Le coût en hauteur est accepté, et il n'est payé que quand une
              tranche existe — sans tranche, la tuile compacte est strictement
              identique à avant. */}
          {hasDivisions && (
            <p className="mt-1.5 text-[10px] leading-snug text-[#9ca3af]">
              {t(tile.weight ? tile.remainderKey : tile.captionKey)}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

export default KpiCards;
