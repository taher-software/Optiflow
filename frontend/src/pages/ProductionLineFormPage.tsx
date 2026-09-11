import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { ConfirmDeleteDialog } from "../components/ConfirmDeleteDialog";
import { SelectField } from "../components/SelectField";
import { TextField } from "../components/TextField";
import { ROUTES } from "../constants/routes";
import type { CreateProductionLinePayload } from "../constants/productionLines";
import { useProductionLinesStore } from "../stores/useProductionLinesStore";
import { useUapsStore } from "../stores/useUapsStore";
import { useWorkstationsStore } from "../stores/useWorkstationsStore";
import { lineDeletionImpact, NO_IMPACT } from "../utils/deletionImpact";

/** Create or edit a production line (edit mode when a :id param is present). */
export function ProductionLineFormPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = Boolean(id);

  const uaps = useUapsStore((s) => s.uaps);
  const fetchUaps = useUapsStore((s) => s.fetchUaps);
  const createLine = useProductionLinesStore((s) => s.createLine);
  const getLine = useProductionLinesStore((s) => s.getLine);
  const updateLine = useProductionLinesStore((s) => s.updateLine);
  const deleteLine = useProductionLinesStore((s) => s.deleteLine);
  // Stations are read only to spell out what a deletion sweeps up.
  const workstations = useWorkstationsStore((s) => s.workstations);
  const fetchWorkstations = useWorkstationsStore((s) => s.fetchWorkstations);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [uapId, setUapId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  /** The persisted name, so the confirmation names the line as it is saved. */
  const [savedName, setSavedName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(!isEdit);

  useEffect(() => {
    void fetchUaps();
  }, [fetchUaps]);

  useEffect(() => {
    if (!isEdit) return;
    void fetchWorkstations();
  }, [isEdit, fetchWorkstations]);

  useEffect(() => {
    if (!id) return;
    void getLine(id).then((res) => {
      if (res.ok && res.data) {
        setName(res.data.name);
        setSavedName(res.data.name);
        setDescription(res.data.description);
        setUapId(res.data.uap_id ?? "");
      } else {
        setError(res.error ?? t("lines.form.loadError"));
      }
      setLoaded(true);
    });
  }, [id, getLine, t]);

  const valid = name.trim() !== "";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setSubmitting(true);
    setError(null);

    // `uap_id` is always present in the payload: the API distinguishes an
    // omitted key ("leave untouched") from an explicit null ("detach"), so
    // picking the independent option must serialize to `"uap_id": null`.
    const payload: CreateProductionLinePayload = {
      name: name.trim(),
      description: description.trim(),
      uap_id: uapId === "" ? null : uapId,
    };
    const res =
      isEdit && id ? await updateLine(id, payload) : await createLine(payload);

    setSubmitting(false);
    if (res.ok) navigate(ROUTES.lines);
    else setError(res.error ?? t("lines.form.saveError"));
  };

  const impact = useMemo(
    () => (id ? lineDeletionImpact(id, workstations) : NO_IMPACT),
    [id, workstations],
  );

  const remove = async () => {
    if (!id) return;
    setDeleting(true);
    setError(null);
    const res = await deleteLine(id);
    setDeleting(false);
    setConfirming(false);
    if (res.ok) navigate(ROUTES.lines);
    else setError(res.error ?? t("lines.form.deleteError"));
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold tracking-tight">
        {isEdit ? t("lines.form.editTitle") : t("lines.form.createTitle")}
      </h1>

      {!loaded ? (
        <p className="mt-8 text-sm text-slate-400">{t("lines.loading")}</p>
      ) : (
        <form onSubmit={submit} className="mt-8 space-y-6">
          <TextField
            id="name"
            label={t("lines.form.name")}
            required
            value={name}
            onChange={setName}
            placeholder={t("lines.form.namePlaceholder")}
          />

          <div>
            <label
              htmlFor="description"
              className="mb-1 block text-sm font-medium text-slate-300"
            >
              {t("lines.form.description")}
            </label>
            <textarea
              id="description"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white placeholder-slate-500 focus:border-teal-400 focus:outline-none"
              placeholder={t("lines.form.descriptionPlaceholder")}
            />
          </div>

          <SelectField
            id="uap_id"
            label={t("lines.form.zoneArea")}
            value={uapId}
            onChange={setUapId}
            placeholder={t("lines.form.independent")}
            options={uaps.map((u) => ({ value: u.id, label: u.name }))}
          />

          {error && <p className="text-sm text-red-400">{error}</p>}

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => navigate(ROUTES.lines)}
              className="rounded-xl border border-slate-700 px-4 py-3 text-sm font-medium text-slate-200 transition-colors hover:border-slate-500 hover:text-white"
            >
              {t("lines.form.cancel")}
            </button>
            <button
              type="submit"
              disabled={submitting || !valid}
              className="rounded-xl bg-teal-400 px-6 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300 disabled:opacity-60"
            >
              {submitting
                ? isEdit
                  ? t("lines.form.saving")
                  : t("lines.form.creating")
                : t("lines.form.save")}
            </button>
            {isEdit && (
              <button
                type="button"
                onClick={() => setConfirming(true)}
                disabled={deleting}
                className="ml-auto rounded-xl border border-red-500/50 px-4 py-3 text-sm font-medium text-red-400 transition-colors hover:border-red-500 hover:text-red-300 disabled:opacity-60"
              >
                {deleting ? t("lines.form.deleting") : t("lines.form.delete")}
              </button>
            )}
          </div>
        </form>
      )}

      <ConfirmDeleteDialog
        open={confirming}
        title={t("lines.form.confirmDelete.title")}
        body={t("lines.form.confirmDelete.body", { name: savedName })}
        impact={impact}
        busy={deleting}
        onConfirm={remove}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
}

export default ProductionLineFormPage;
