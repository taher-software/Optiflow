import { BrandLogo } from "../components/BrandLogo";
import { Spinner } from "../components/Spinner";
import { BRAND } from "../constants/brand";

/**
 * Splash / launch screen shown while the web app boots
 * (session check, tenant resolution, initial data).
 * Presentational only — no data fetching.
 */
export function SplashPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-slate-950 via-slate-900 to-slate-800 px-6 text-center">
      <BrandLogo />
      <p className="mt-5 max-w-xs text-sm font-medium text-slate-400">
        {BRAND.tagline}
      </p>
      <Spinner className="mt-12" />
    </div>
  );
}

export default SplashPage;
