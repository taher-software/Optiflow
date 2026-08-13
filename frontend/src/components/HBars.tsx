import type { Bar } from "../constants/dashboard";
import { shade } from "../utils/dashboardFormat";

interface HBarsProps {
  bars: Bar[];
  /** Rampe séquentielle (intensité ∝ valeur) OU couleur fixe. */
  ramp: readonly string[] | string;
  format: (value: number) => string;
  /** Traduit un id/libellé de barre (défaut : le libellé brut). */
  labelOf?: (bar: Bar) => string;
}

/** Barres horizontales compactes des sections analytiques (drill / stats). */
export function HBars({ bars, ramp, format, labelOf }: HBarsProps) {
  if (bars.length === 0) return null;
  const max = Math.max(...bars.map((b) => b.value), 1);

  return (
    <div>
      {bars.map((bar) => {
        const ratio = bar.value / max;
        return (
          <div
            key={bar.id}
            className="grid grid-cols-[130px_1fr_110px] items-center gap-2.5 py-1.5 text-[12.5px]"
          >
            <span className="truncate font-medium text-[#4b5563]">
              {labelOf ? labelOf(bar) : bar.label}
            </span>
            <span className="h-[9px] overflow-hidden rounded-[5px] bg-[#f3f4f6]">
              <span
                className="block h-full rounded-[5px]"
                style={{
                  width: `${Math.max(3, Math.round(ratio * 100))}%`,
                  background:
                    typeof ramp === "string" ? ramp : shade(ramp, ratio),
                }}
              />
            </span>
            <span className="text-right font-semibold tabular-nums text-[#16181d]">
              {format(bar.value)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default HBars;
