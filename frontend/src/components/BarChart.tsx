import { useState } from "react";

interface Series {
  name: string;
  color: string;
  values: number[];
}

interface BarChartProps {
  /** 1 série (suivi) ou 2 (comparaison, barres groupées). */
  series: Series[];
  /** Libellé de l'axe X pour l'index i (ex. "05/07" ou "J3"). */
  labelOf: (index: number) => string;
  /** Format des valeurs (tooltip + axe Y). */
  format: (value: number) => string;
}

interface Hover {
  x: number;
  y: number;
  title: string;
  value: string;
}

const W = 1040;
const H = 240;
const PAD_L = 52;
const PAD_B = 24;
const PAD_T = 10;

/** Bargraph journalier SVG (grille discrète, coins arrondis, tooltip au
 * survol). Présentationnel — aucune donnée chargée ici. */
export function BarChart({ series, labelOf, format }: BarChartProps) {
  const [hover, setHover] = useState<Hover | null>(null);
  if (series.length === 0 || series[0].values.length === 0) return null;

  const groups = series[0].values.length;
  const maxV = Math.max(...series.flatMap((s) => s.values), 1);
  const gw = (W - PAD_L - 8) / groups;
  const bw = Math.max(3, Math.min(26, (gw - 4) / series.length - 2));
  const step = Math.ceil(groups / 12);

  return (
    <div className="relative">
      <svg
        width="100%"
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        role="img"
      >
        {[0, 1, 2, 3].map((g) => {
          const y = PAD_T + (H - PAD_B - PAD_T) * (1 - g / 3);
          return (
            <g key={g}>
              <line
                x1={PAD_L}
                y1={y}
                x2={W}
                y2={y}
                stroke="#eceef1"
                strokeWidth={1}
              />
              <text
                x={PAD_L - 6}
                y={y + 3}
                textAnchor="end"
                className="fill-[#9ca3af] text-[10.5px]"
              >
                {format(Math.round((maxV * g) / 3))}
              </text>
            </g>
          );
        })}
        {series.map((s, si) =>
          s.values.map((v, i) => {
            const h = Math.max(2, ((H - PAD_B - PAD_T) * v) / maxV);
            const x =
              PAD_L +
              i * gw +
              (gw - series.length * (bw + 2)) / 2 +
              si * (bw + 2);
            return (
              <rect
                key={`${si}-${i}`}
                x={x}
                y={H - PAD_B - h}
                width={bw}
                height={h}
                rx={3}
                fill={s.color}
                onMouseMove={(e) =>
                  setHover({
                    x: e.clientX,
                    y: e.clientY,
                    title: `${labelOf(i)} · ${s.name}`,
                    value: format(v),
                  })
                }
                onMouseLeave={() => setHover(null)}
              />
            );
          }),
        )}
        {Array.from({ length: groups }, (_, i) => i)
          .filter((i) => i % step === 0)
          .map((i) => (
            <text
              key={i}
              x={PAD_L + i * gw + gw / 2}
              y={H - 8}
              textAnchor="middle"
              className="fill-[#9ca3af] text-[10.5px]"
            >
              {labelOf(i)}
            </text>
          ))}
      </svg>
      {hover && (
        <div
          className="pointer-events-none fixed z-50 min-w-[120px] rounded-lg border border-[#d1d5db] bg-white px-2.5 py-2 text-[12px] text-[#16181d] shadow-lg"
          style={{ left: hover.x + 14, top: hover.y - 10 }}
        >
          <div className="mb-0.5 text-[11px] text-[#9ca3af]">{hover.title}</div>
          <b className="tabular-nums">{hover.value}</b>
        </div>
      )}
    </div>
  );
}

export default BarChart;
