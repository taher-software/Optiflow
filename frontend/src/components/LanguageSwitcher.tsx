import { useTranslation } from "react-i18next";

import { SUPPORTED_LANGUAGES } from "../i18n";

/** FR / EN language toggle. Presentational. */
export function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const current = i18n.resolvedLanguage ?? i18n.language;

  return (
    <div className="inline-flex overflow-hidden rounded-lg border border-slate-700 text-xs">
      {SUPPORTED_LANGUAGES.map((lang) => (
        <button
          key={lang}
          type="button"
          onClick={() => void i18n.changeLanguage(lang)}
          className={
            current === lang
              ? "bg-teal-400 px-2.5 py-1 font-semibold text-slate-950"
              : "px-2.5 py-1 font-medium text-slate-300 hover:text-white"
          }
        >
          {lang.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
