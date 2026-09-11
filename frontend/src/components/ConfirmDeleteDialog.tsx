import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { hasImpact, type DeletionImpact } from "../utils/deletionImpact";

/** How many names a group lists before the remainder becomes a count. */
const NAME_LIMIT = 6;

interface ConfirmDeleteDialogProps {
  open: boolean;
  /** The question in the heading, e.g. "Delete this production area?". */
  title: string;
  /** One sentence naming the resource about to be deleted. */
  body: string;
  /** What else the deletion takes with it. Empty when it takes nothing. */
  impact: DeletionImpact;
  /** True while the deletion request is in flight. */
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Modal that asks the user to confirm a permanent deletion, spelling out
 * everything that disappears with it. Presentational: the caller owns the
 * open state, the impact and the request. */
export function ConfirmDeleteDialog({
  open,
  title,
  body,
  impact,
  busy,
  onConfirm,
  onCancel,
}: ConfirmDeleteDialogProps) {
  const { t } = useTranslation();
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, busy, onCancel]);

  if (!open) return null;

  const groups = [
    { key: "lines", names: impact.lines.map((l) => l.name) },
    { key: "stations", names: impact.workstations.map((w) => w.name) },
  ].filter((g) => g.names.length > 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-delete-title"
        aria-describedby="confirm-delete-body"
        className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl"
      >
        <h2
          id="confirm-delete-title"
          className="text-lg font-semibold text-white"
        >
          {title}
        </h2>

        <p id="confirm-delete-body" className="mt-3 text-sm text-slate-300">
          {body}
        </p>

        {groups.length > 0 && (
          <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/5 p-4">
            <p className="text-sm font-medium text-red-300">
              {t("deleteDialog.alsoDeleted")}
            </p>
            <ul className="mt-2 space-y-2 text-sm text-slate-300">
              {groups.map((g) => (
                <li key={g.key}>
                  <span className="font-medium text-white">
                    {t(`deleteDialog.${g.key}Count`, { count: g.names.length })}
                  </span>
                  <span className="block text-slate-400">
                    {g.names.slice(0, NAME_LIMIT).join(", ")}
                    {g.names.length > NAME_LIMIT &&
                      `, ${t("deleteDialog.andMore", {
                        count: g.names.length - NAME_LIMIT,
                      })}`}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <p
          className={`text-sm font-medium text-red-400 ${
            hasImpact(impact) ? "mt-4" : "mt-3"
          }`}
        >
          {t("deleteDialog.irreversible")}
        </p>

        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-xl border border-slate-700 px-4 py-3 text-sm font-medium text-slate-200 transition-colors hover:border-slate-500 hover:text-white disabled:opacity-60"
          >
            {t("deleteDialog.cancel")}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded-xl bg-red-500 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-red-400 disabled:opacity-60"
          >
            {busy ? t("deleteDialog.deleting") : t("deleteDialog.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmDeleteDialog;
