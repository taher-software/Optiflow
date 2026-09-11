import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { ConfirmDeleteDialog } from "../components/ConfirmDeleteDialog";
import { SelectField } from "../components/SelectField";
import { TextField } from "../components/TextField";
import { ROUTES } from "../constants/routes";
import {
  WORKSTATION_TYPES,
  type CreateWorkstationPayload,
} from "../constants/workstations";
import { useProductionLinesStore } from "../stores/useProductionLinesStore";
import { useWorkstationsStore } from "../stores/useWorkstationsStore";
import { NO_IMPACT } from "../utils/deletionImpact";

/** Create or edit a workstation (edit mode when a :id param is present). */
export function WorkstationFormPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = Boolean(id);

  const lines = useProductionLinesStore((s) => s.lines);
  const fetchLines = useProductionLinesStore((s) => s.fetchLines);
  const createWorkstation = useWorkstationsStore((s) => s.createWorkstation);
  const getWorkstation = useWorkstationsStore((s) => s.getWorkstation);
  const updateWorkstation = useWorkstationsStore((s) => s.updateWorkstation);
  const deleteWorkstation = useWorkstationsStore((s) => s.deleteWorkstation);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [lineId, setLineId] = useState("");
  const [type, setType] = useState<string>(WORKSTATION_TYPES[0]);
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  /** The persisted name, so the confirmation names the station as it is saved. */
  const [savedName, setSavedName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(!isEdit);

  useEffect(() => {
    void fetchLines();
  }, [fetchLines]);

  useEffect(() => {
    if (!id) return;
    void getWorkstation(id).then((res) => {
      if (res.ok && res.data) {
        setName(res.data.name);
        setSavedName(res.data.name);
        setDescription(res.data.description);
        setLineId(res.data.production_line_id ?? "");
        setType(res.data.type);
      } else {
        setError(res.error ?? t("stations.form.loadError"));
      }
      setLoaded(true);
    });
  }, [id, getWorkstation, t]);

  const valid = name.trim() !== "" && type !== "";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setSubmitting(true);
    setError(null);

    const payload: CreateWorkstationPayload = {
      name: name.trim(),
      description: description.trim(),
      production_line_id: lineId === "" ? null : lineId,
      type,
    };
    const res =
      isEdit && id
        ? await updateWorkstation(id, payload)
        : await createWorkstation(payload);

    setSubmitting(false);
    if (res.ok) navigate(ROUTES.stations);
    else setError(res.error ?? t("stations.form.saveError"));
  };

  const remove = async () => {
    if (!id) return;
    setDeleting(true);
    setError(null);
    const res = await deleteWorkstation(id);
    setDeleting(false);
    setConfirming(false);
    if (res.ok) navigate(ROUTES.stations);
    else setError(res.error ?? t("stations.form.deleteError"));
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold tracking-tight">
        {isEdit ? t("stations.form.editTitle") : t("stations.form.createTitle")}
      </h1>

      {!loaded ? (
        <p className="mt-8 text-sm text-slate-400">{t("stations.loading")}</p>
      ) : (
        <form onSubmit={submit} className="mt-8 space-y-6">
          <TextField
            id="name"
            label={t("stations.form.name")}
            required
            value={name}
            onChange={setName}
            placeholder={t("stations.form.namePlaceholder")}
          />

          <div>
            <label
              htmlFor="description"
              className="mb-1 block text-sm font-medium text-slate-300"
            >
              {t("stations.form.description")}
            </label>
            <textarea
              id="description"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white placeholder-slate-500 focus:border-teal-400 focus:outline-none"
              placeholder={t("stations.form.descriptionPlaceholder")}
            />
          </div>

          <SelectField
            id="production_line_id"
            label={t("stations.form.line")}
            value={lineId}
            onChange={setLineId}
            placeholder={t("stations.form.independent")}
            options={lines.map((l) => ({ value: l.id, label: l.name }))}
          />

          <SelectField
            id="type"
            label={t("stations.form.type")}
            required
            value={type}
            onChange={setType}
            options={WORKSTATION_TYPES.map((ty) => ({
              value: ty,
              label: t(`stations.types.${ty}`),
            }))}
          />

          {error && <p className="text-sm text-red-400">{error}</p>}

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => navigate(ROUTES.stations)}
              className="rounded-xl border border-slate-700 px-4 py-3 text-sm font-medium text-slate-200 transition-colors hover:border-slate-500 hover:text-white"
            >
              {t("stations.form.cancel")}
            </button>
            <button
              type="submit"
              disabled={submitting || !valid}
              className="rounded-xl bg-teal-400 px-6 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300 disabled:opacity-60"
            >
              {submitting
                ? isEdit
                  ? t("stations.form.saving")
                  : t("stations.form.creating")
                : t("stations.form.save")}
            </button>
            {isEdit && (
              <button
                type="button"
                onClick={() => setConfirming(true)}
                disabled={deleting}
                className="ml-auto rounded-xl border border-red-500/50 px-4 py-3 text-sm font-medium text-red-400 transition-colors hover:border-red-500 hover:text-red-300 disabled:opacity-60"
              >
                {deleting
                  ? t("stations.form.deleting")
                  : t("stations.form.delete")}
              </button>
            )}
          </div>
        </form>
      )}

      <ConfirmDeleteDialog
        open={confirming}
        title={t("stations.form.confirmDelete.title")}
        body={t("stations.form.confirmDelete.body", { name: savedName })}
        impact={NO_IMPACT}
        busy={deleting}
        onConfirm={remove}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
}

export default WorkstationFormPage;
