import { BRAND } from "../constants/brand";

/** Operio logo mark + wordmark. Presentational, no state. */
export function BrandLogo() {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-400 to-cyan-500 shadow-lg shadow-cyan-500/25">
        <svg
          viewBox="0 0 24 24"
          className="h-6 w-6 text-slate-900"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M3 17l5-5 4 4 8-8" />
          <path d="M16 8h5v5" />
        </svg>
      </span>
      <span className="text-3xl font-bold tracking-tight text-white">
        {BRAND.nameLead}
        <span className="text-teal-400">{BRAND.nameAccent}</span>
      </span>
    </div>
  );
}
