import { useTranslation } from "react-i18next";

import { roleSlug, type User } from "../constants/users";

interface MemberGroupSelectProps {
  /** Role value this group is for (e.g. "maintenance agent"). */
  role: string;
  /** Users in the namespace holding this role. */
  users: User[];
  /** Currently selected user ids. */
  selected: string[];
  /** Toggle a user id in/out of the selection. */
  onToggle: (userId: string) => void;
}

/** One member group of the UAP form: all users of a given role, each a
 * toggleable chip. Presentational — selection state is owned by the parent. */
export function MemberGroupSelect({
  role,
  users,
  selected,
  onToggle,
}: MemberGroupSelectProps) {
  const { t } = useTranslation();
  const slug = roleSlug(role);

  return (
    <div className="rounded-2xl border border-slate-800 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">
          {t(`users.roles.${slug}.name`)}
        </h3>
        <span className="text-xs text-slate-500">
          {selected.length}/{users.length}
        </span>
      </div>

      {users.length === 0 ? (
        <p className="mt-3 text-xs text-slate-500">
          {t("uaps.form.noMembers")}
        </p>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          {users.map((u) => {
            const isSelected = selected.includes(u.id);
            return (
              <button
                type="button"
                key={u.id}
                onClick={() => onToggle(u.id)}
                aria-pressed={isSelected}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                  isSelected
                    ? "border-teal-400 bg-teal-400/10 text-teal-200"
                    : "border-slate-700 text-slate-300 hover:border-slate-500"
                }`}
              >
                {u.first_name} {u.last_name}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
