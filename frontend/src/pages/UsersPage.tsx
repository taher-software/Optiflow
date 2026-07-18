import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { ROUTES } from "../constants/routes";
import { roleSlug } from "../constants/users";
import { useUsersStore } from "../stores/useUsersStore";

/** Lists the namespace's users with their security codes. Owner/admin only. */
export function UsersPage() {
  const { t } = useTranslation();
  const users = useUsersStore((s) => s.users);
  const loading = useUsersStore((s) => s.loading);
  const error = useUsersStore((s) => s.error);
  const fetchUsers = useUsersStore((s) => s.fetchUsers);

  useEffect(() => {
    void fetchUsers();
  }, [fetchUsers]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">
          {t("users.title")}
        </h1>
        <Link
          to={ROUTES.newUser}
          className="rounded-xl bg-teal-400 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300"
        >
          {t("users.add")}
        </Link>
      </div>

      {loading && (
        <p className="mt-8 text-sm text-slate-400">{t("users.loading")}</p>
      )}
      {error && <p className="mt-8 text-sm text-red-400">{error}</p>}
      {!loading && !error && users.length === 0 && (
        <p className="mt-8 text-sm text-slate-400">{t("users.empty")}</p>
      )}

      {!loading && users.length > 0 && (
        <div className="mt-8 overflow-x-auto rounded-2xl border border-slate-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-900/60 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">{t("users.table.name")}</th>
                <th className="px-4 py-3">{t("users.table.role")}</th>
                <th className="px-4 py-3">{t("users.table.email")}</th>
                <th className="px-4 py-3">{t("users.table.securityCode")}</th>
                <th className="px-4 py-3 text-right">
                  {t("users.table.actions")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-slate-900/40">
                  <td className="px-4 py-3 text-white">
                    {u.first_name} {u.last_name}
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {t(`users.roles.${roleSlug(u.role)}.name`)}
                  </td>
                  <td className="px-4 py-3 text-slate-400">{u.email ?? "—"}</td>
                  <td className="px-4 py-3 font-mono text-teal-400">
                    {u.security_code}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      to={`${ROUTES.users}/${u.id}`}
                      className="text-sm font-medium text-teal-400 hover:text-teal-300"
                    >
                      {t("users.edit")}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default UsersPage;
