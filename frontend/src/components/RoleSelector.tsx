import { useTranslation } from "react-i18next";

import { ASSIGNABLE_ROLES, roleSlug } from "../constants/users";

interface RoleSelectorProps {
  value: string;
  onChange: (role: string) => void;
}

/** Selectable list of assignable roles, each showing its description. */
export function RoleSelector({ value, onChange }: RoleSelectorProps) {
  const { t } = useTranslation();

  return (
    <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
      {ASSIGNABLE_ROLES.map((role) => {
        const slug = roleSlug(role);
        const selected = value === role;
        return (
          <button
            type="button"
            key={role}
            onClick={() => onChange(role)}
            className={`w-full rounded-xl border p-3 text-left transition-colors ${
              selected
                ? "border-teal-400 bg-teal-400/10"
                : "border-slate-700 hover:border-slate-500"
            }`}
          >
            <span className="text-sm font-semibold text-white">
              {t(`users.roles.${slug}.name`)}
            </span>
            <span className="mt-1 block text-xs leading-relaxed text-slate-400">
              {t(`users.roles.${slug}.description`)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
