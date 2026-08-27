import { useTranslation } from "react-i18next";

import { BrandLogo } from "../components/BrandLogo";
import { LegalFooter } from "../components/LegalFooter";
import { Spinner } from "../components/Spinner";

/**
 * Splash / launch screen shown while the web app boots
 * (session check, tenant resolution, initial data).
 * Presentational only — no data fetching.
 */
export function SplashPage() {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-screen flex-col bg-gradient-to-b from-slate-950 via-slate-900 to-slate-800 px-6 text-center">
      <div className="flex flex-1 flex-col items-center justify-center">
        <BrandLogo />
        <p className="mt-5 max-w-xs text-sm font-medium text-slate-400">
          {t("tagline")}
        </p>
        <Spinner className="mt-12" />
      </div>
      <div className="py-8">
        <LegalFooter />
      </div>
    </div>
  );
}

export default SplashPage;
