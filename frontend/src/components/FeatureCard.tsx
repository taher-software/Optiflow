import type { Feature } from "../constants/features";
import { FeatureIcon } from "./FeatureIcon";

interface FeatureCardProps {
  feature: Feature;
}

/** A single value-proposition card. Presentational, no state. */
export function FeatureCard({ feature }: FeatureCardProps) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 transition-colors hover:border-teal-500/50">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-teal-400/10 text-teal-400">
        <FeatureIcon name={feature.icon} />
      </div>
      <h3 className="mt-4 text-lg font-semibold text-white">{feature.title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-slate-400">
        {feature.description}
      </p>
    </div>
  );
}
