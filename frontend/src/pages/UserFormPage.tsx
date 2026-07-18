import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { PasswordField } from "../components/PasswordField";
import { RoleSelector } from "../components/RoleSelector";
import { TextField } from "../components/TextField";
import { ROUTES } from "../constants/routes";
import {
  roleNeedsEmail,
  type CreateUserPayload,
  type UpdateUserPayload,
} from "../constants/users";
import { useUsersStore } from "../stores/useUsersStore";

/** Create or edit a user (edit mode when a :id param is present). */
export function UserFormPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = Boolean(id);

  const createUser = useUsersStore((s) => s.createUser);
  const getUser = useUsersStore((s) => s.getUser);
  const updateUser = useUsersStore((s) => s.updateUser);

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [role, setRole] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(!isEdit);

  useEffect(() => {
    if (!id) return;
    void getUser(id).then((res) => {
      if (res.ok && res.data) {
        setFirstName(res.data.first_name);
        setLastName(res.data.last_name);
        setRole(res.data.role);
        setEmail(res.data.email ?? "");
      } else {
        setError(res.error ?? t("users.form.loadError"));
      }
      setLoaded(true);
    });
  }, [id, getUser, t]);

  const isOwner = role === "owner";
  const needsEmail = role !== "" && roleNeedsEmail(role);
  const valid =
    firstName.trim() !== "" &&
    lastName.trim() !== "" &&
    role !== "" &&
    (!needsEmail || email.trim() !== "") &&
    (isEdit || password.length >= 6);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setSubmitting(true);
    setError(null);

    const emailPart = email.trim() ? { email: email.trim() } : {};
    const res =
      isEdit && id
        ? await updateUser(id, {
            first_name: firstName,
            last_name: lastName,
            ...(isOwner ? {} : { role }),
            ...emailPart,
            ...(password.trim() ? { password: password.trim() } : {}),
          } satisfies UpdateUserPayload)
        : await createUser({
            first_name: firstName,
            last_name: lastName,
            role,
            password,
            ...emailPart,
          } satisfies CreateUserPayload);

    setSubmitting(false);
    if (res.ok) navigate(ROUTES.users);
    else setError(res.error ?? t("users.form.saveError"));
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold tracking-tight">
        {isEdit ? t("users.form.editTitle") : t("users.form.createTitle")}
      </h1>

      {!loaded ? (
        <p className="mt-8 text-sm text-slate-400">{t("users.loading")}</p>
      ) : (
        <form onSubmit={submit} className="mt-8 space-y-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              id="first_name"
              label={t("users.form.firstName")}
              required
              value={firstName}
              onChange={setFirstName}
            />
            <TextField
              id="last_name"
              label={t("users.form.lastName")}
              required
              value={lastName}
              onChange={setLastName}
            />
          </div>

          <div>
            <span className="mb-2 block text-sm font-medium text-slate-300">
              {t("users.form.role")}
            </span>
            {isOwner ? (
              <p className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3 text-sm text-slate-400">
                {t("users.roles.owner.name")} — {t("users.form.roleLocked")}
              </p>
            ) : (
              <RoleSelector value={role} onChange={setRole} />
            )}
          </div>

          <TextField
            id="email"
            type="email"
            label={
              t("users.form.email") +
              (needsEmail ? " *" : ` (${t("users.form.optional")})`)
            }
            required={needsEmail}
            value={email}
            onChange={setEmail}
            placeholder="user@company.com"
          />

          <PasswordField
            id="password"
            label={
              isEdit ? t("users.form.passwordEdit") : t("users.form.password")
            }
            required={!isEdit}
            value={password}
            onChange={setPassword}
            placeholder={isEdit ? t("users.form.passwordEditHint") : "••••••"}
          />

          {error && <p className="text-sm text-red-400">{error}</p>}

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => navigate(ROUTES.users)}
              className="rounded-xl border border-slate-700 px-4 py-3 text-sm font-medium text-slate-200 transition-colors hover:border-slate-500 hover:text-white"
            >
              {t("users.form.cancel")}
            </button>
            <button
              type="submit"
              disabled={submitting || !valid}
              className="rounded-xl bg-teal-400 px-6 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300 disabled:opacity-60"
            >
              {submitting
                ? isEdit
                  ? t("users.form.saving")
                  : t("users.form.creating")
                : t("users.form.save")}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

export default UserFormPage;
