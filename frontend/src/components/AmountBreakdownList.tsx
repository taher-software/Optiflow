export interface AmountLine {
  label: string;
  value: string;
}

interface AmountBreakdownListProps {
  lines: AmountLine[];
  totalLabel: string;
  totalValue: string;
}

/** Amount lines (HT, TVA, timbre…) followed by the emphasized total.
 * Presentational, no state. */
export function AmountBreakdownList({
  lines,
  totalLabel,
  totalValue,
}: AmountBreakdownListProps) {
  return (
    <dl className="space-y-1.5 text-sm">
      {lines.map((l) => (
        <div key={l.label} className="flex justify-between gap-4">
          <dt className="text-slate-400">{l.label}</dt>
          <dd className="tabular-nums text-slate-200">{l.value}</dd>
        </div>
      ))}
      <div className="flex justify-between gap-4 border-t border-slate-800 pt-2">
        <dt className="font-semibold text-white">{totalLabel}</dt>
        <dd className="font-semibold tabular-nums text-teal-300">
          {totalValue}
        </dd>
      </div>
    </dl>
  );
}

export default AmountBreakdownList;
