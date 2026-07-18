import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { MemberGroupSelect } from "../components/MemberGroupSelect";
import { TextField } from "../components/TextField";
import { ROUTES } from "../constants/routes";
import {
  emptyMembers,
  UAP_MEMBER_GROUPS,
  type CreateUapPayload,
  type UapMemberField,
} from "../constants/uaps";
import { useUapsStore } from "../stores/useUapsStore";
import { useUsersStore } from "../stores/useUsersStore";

/** Create or edit a production area (edit mode when a :id param is present). */
export function UapFormPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = Boolean(id);

  const users = useUsersStore((s) => s.users);
  const fetchUsers = useUsersStore((s) => s.fetchUsers);
  const createUap = useUapsStore((s) => s.createUap);
  const getUap = useUapsStore((s) => s.getUap);
  const updateUap = useUapsStore((s) => s.updateUap);
  const deleteUap = useUapsStore((s) => s.deleteUap);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [members, setMembers] =
    useState<Record<UapMemberField, string[]>>(emptyMembers);
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(!isEdit);

  useEffect(() => {
    void fetchUsers();
  }, [fetchUsers]);

  useEffect(() => {
    if (!id) return;
    void getUap(id).then((res) => {
      if (res.ok && res.data) {
        setName(res.data.name);
        setDescription(res.data.description);
        const next = emptyMembers();
        for (const { field } of UAP_MEMBER_GROUPS) {
          next[field] = res.data[field] ?? [];
        }
        setMembers(next);
      } else {
        setError(res.error ?? t("uaps.form.loadError"));
      }
      setLoaded(true);
    });
  }, [id, getUap, t]);

  const usersByRole = useMemo(() => {
    const map: Record<string, typeof users> = {};
    for (const g of UAP_MEMBER_GROUPS) {
      map[g.role] = users.filter((u) => u.role === g.role);
    }
    return map;
  }, [users]);

  const toggleMember = (field: UapMemberField, userId: string) => {
    setMembers((prev) => {
      const set = prev[field];
      const next = set.includes(userId)
        ? set.filter((x) => x !== userId)
        : [...set, userId];
      return { ...prev, [field]: next };
    });
  };

  const valid = name.trim() !== "";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setSubmitting(true);
    setError(null);

    const payload: CreateUapPayload = {
      name: name.trim(),
      description: description.trim(),
      ...members,
    };
    const res =
      isEdit && id ? await updateUap(id, payload) : await createUap(payload);

    setSubmitting(false);
    if (res.ok) navigate(ROUTES.uaps);
    else setError(res.error ?? t("uaps.form.saveError"));
  };

  const remove = async () => {
    if (!id || !window.confirm(t("uaps.form.confirmDelete"))) return;
    setDeleting(true);
    setError(null);
    const res = await deleteUap(id);
    setDeleting(false);
    if (res.ok) navigate(ROUTES.uaps);
    else setError(res.error ?? t("uaps.form.deleteError"));
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold tracking-tight">
        {isEdit ? t("uaps.form.editTitle") : t("uaps.form.createTitle")}
      </h1>

      {!loaded ? (
        <p className="mt-8 text-sm text-slate-400">{t("uaps.loading")}</p>
      ) : (
        <form onSubmit={submit} className="mt-8 space-y-6">
          <TextField
            id="name"
            label={t("uaps.form.name")}
            required
            value={name}
            onChange={setName}
            placeholder={t("uaps.form.namePlaceholder")}
          />

          <div>
            <label
              htmlFor="description"
              className="mb-1 block text-sm font-medium text-slate-300"
            >
              {t("uaps.form.description")}
            </label>
            <textarea
              id="description"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white placeholder-slate-500 focus:border-teal-400 focus:outline-none"
              placeholder={t("uaps.form.descriptionPlaceholder")}
            />
          </div>

          <div>
            <span className="mb-3 block text-sm font-medium text-slate-300">
              {t("uaps.form.resources")}
            </span>
            <div className="space-y-3">
              {UAP_MEMBER_GROUPS.map((g) => (
                <MemberGroupSelect
                  key={g.field}
                  role={g.role}
                  users={usersByRole[g.role] ?? []}
                  selected={members[g.field]}
                  onToggle={(userId) => toggleMember(g.field, userId)}
                />
              ))}
            </div>
          </div>

          {error && <p className="text-sm text-red-400">{error}</p>}

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => navigate(ROUTES.uaps)}
              className="rounded-xl border border-slate-700 px-4 py-3 text-sm font-medium text-slate-200 transition-colors hover:border-slate-500 hover:text-white"
            >
              {t("uaps.form.cancel")}
            </button>
            <button
              type="submit"
              disabled={submitting || !valid}
              className="rounded-xl bg-teal-400 px-6 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300 disabled:opacity-60"
            >
              {submitting
                ? isEdit
                  ? t("uaps.form.saving")
                  : t("uaps.form.creating")
                : t("uaps.form.save")}
            </button>
            {isEdit && (
              <button
                type="button"
                onClick={remove}
                disabled={deleting}
                className="ml-auto rounded-xl border border-red-500/50 px-4 py-3 text-sm font-medium text-red-400 transition-colors hover:border-red-500 hover:text-red-300 disabled:opacity-60"
              >
                {deleting ? t("uaps.form.deleting") : t("uaps.form.delete")}
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}

export default UapFormPage;
