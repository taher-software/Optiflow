import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { SelectField } from "../components/SelectField";
import {
  DEFAULT_TIME_TO_ESCALATE,
  SHIFT_NUMBERS,
  type SaveSettingsPayload,
  type ShiftTime,
} from "../constants/settings";
import { useAuthStore } from "../stores/useAuthStore";
import { useSettingsStore } from "../stores/useSettingsStore";

type ShiftDraft = {
  start_time: string;
  end_time: string;
  break_minutes: string;
};

const EMPTY_SHIFT: ShiftDraft = {
  start_time: "",
  end_time: "",
  break_minutes: "0",
};

/** Namespace plant settings: number of shifts + each shift's clock window, and
 * the downtime escalation delay. Populated from the backend when settings
 * already exist, otherwise defaults; saved via create (first time) or patch. */
export function SettingsPage() {
  const { t } = useTranslation();
  const namespaceId = useAuthStore((s) => s.user?.namespace_id ?? "");

  const settings = useSettingsStore((s) => s.settings);
  const exists = useSettingsStore((s) => s.exists);
  const loading = useSettingsStore((s) => s.loading);
  const fetchSettings = useSettingsStore((s) => s.fetchSettings);
  const createSettings = useSettingsStore((s) => s.createSettings);
  const updateSettings = useSettingsStore((s) => s.updateSettings);

  const [shiftNumber, setShiftNumber] = useState(1);
  const [shifts, setShifts] = useState<ShiftDraft[]>([
    { ...EMPTY_SHIFT },
    { ...EMPTY_SHIFT },
    { ...EMPTY_SHIFT },
  ]);
  const [escalate, setEscalate] = useState(String(DEFAULT_TIME_TO_ESCALATE));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (namespaceId) void fetchSettings(namespaceId);
  }, [namespaceId, fetchSettings]);

  // Populate the form once settings load (or leave defaults when none exist).
  useEffect(() => {
    if (!settings) return;
    setShiftNumber(settings.shift_number);
    const toDraft = (s: ShiftTime | null): ShiftDraft =>
      s
        ? {
            start_time: s.start_time,
            end_time: s.end_time,
            break_minutes: String(s.break_minutes ?? 0),
          }
        : { ...EMPTY_SHIFT };
    setShifts([
      toDraft(settings.shift_1),
      toDraft(settings.shift_2),
      toDraft(settings.shift_3),
    ]);
    setEscalate(String(settings.time_to_escalate));
  }, [settings]);

  const setShift = (index: number, patch: Partial<ShiftDraft>) => {
    setShifts((prev) =>
      prev.map((s, i) => (i === index ? { ...s, ...patch } : s)),
    );
    setSaved(false);
  };

  const escalateSeconds = Number(escalate);
  const escalateValid =
    escalate.trim() !== "" &&
    Number.isFinite(escalateSeconds) &&
    Number.isInteger(escalateSeconds) &&
    escalateSeconds >= 0;

  const breakValid = (s: ShiftDraft) => {
    const n = Number(s.break_minutes);
    return s.break_minutes.trim() !== "" && Number.isInteger(n) && n >= 0;
  };
  const shiftsValid =
    shiftNumber === 1 ||
    shifts
      .slice(0, shiftNumber)
      .every((s) => s.start_time !== "" && s.end_time !== "" && breakValid(s));

  const valid = escalateValid && shiftsValid;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setSubmitting(true);
    setError(null);
    setSaved(false);

    const toShift = (i: number): ShiftTime | null =>
      i < shiftNumber &&
      shifts[i].start_time !== "" &&
      shifts[i].end_time !== ""
        ? {
            start_time: shifts[i].start_time,
            end_time: shifts[i].end_time,
            break_minutes: Number(shifts[i].break_minutes) || 0,
          }
        : null;

    const payload: SaveSettingsPayload = {
      shift_number: shiftNumber,
      shift_1: toShift(0),
      shift_2: toShift(1),
      shift_3: toShift(2),
      time_to_escalate: escalateSeconds,
    };

    const res = exists
      ? await updateSettings(payload)
      : await createSettings(payload);

    setSubmitting(false);
    if (res.ok) setSaved(true);
    else setError(res.error ?? t("settings.saveError"));
  };

  const minutes = escalateValid ? Math.round(escalateSeconds / 60) : null;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold tracking-tight">
        {t("settings.title")}
      </h1>
      <p className="mt-2 text-sm text-slate-400">{t("settings.subtitle")}</p>

      {loading ? (
        <p className="mt-8 text-sm text-slate-400">{t("settings.loading")}</p>
      ) : (
        <form onSubmit={submit} className="mt-8 space-y-8">
          {/* Shift schedule */}
          <section className="space-y-4">
            <SelectField
              id="shift_number"
              label={t("settings.shiftNumber.label")}
              required
              value={String(shiftNumber)}
              onChange={(v) => {
                setShiftNumber(Number(v));
                setSaved(false);
              }}
              options={SHIFT_NUMBERS.map((n) => ({
                value: String(n),
                label: String(n),
              }))}
            />
            <p className="text-xs text-slate-500">
              {t("settings.shiftNumber.help")}
            </p>

            {shiftNumber > 1 &&
              shifts.slice(0, shiftNumber).map((s, i) => (
                <div
                  key={i}
                  className="rounded-xl border border-slate-800 bg-slate-900/50 p-4"
                >
                  <p className="mb-3 text-sm font-semibold text-slate-200">
                    {t("settings.shift.title", { number: i + 1 })}
                  </p>
                  <div className="grid grid-cols-3 gap-4">
                    <TimeInput
                      id={`shift_${i}_start`}
                      label={t("settings.shift.start")}
                      value={s.start_time}
                      onChange={(v) => setShift(i, { start_time: v })}
                    />
                    <TimeInput
                      id={`shift_${i}_end`}
                      label={t("settings.shift.end")}
                      value={s.end_time}
                      onChange={(v) => setShift(i, { end_time: v })}
                    />
                    <div>
                      <label
                        htmlFor={`shift_${i}_break`}
                        className="mb-1 block text-xs font-medium text-slate-400"
                      >
                        {t("settings.shift.break")}
                      </label>
                      <input
                        id={`shift_${i}_break`}
                        type="number"
                        min={0}
                        step={1}
                        value={s.break_minutes}
                        onChange={(e) =>
                          setShift(i, { break_minutes: e.target.value })
                        }
                        className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-2.5 text-sm text-white focus:border-teal-400 focus:outline-none"
                      />
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-slate-500">
                    {t("settings.shift.breakHelp")}
                  </p>
                </div>
              ))}
          </section>

          {/* Escalation delay */}
          <section className="space-y-2">
            <label
              htmlFor="time_to_escalate"
              className="block text-sm font-medium text-slate-300"
            >
              {t("settings.escalate.label")}
              <span className="text-teal-400"> *</span>
            </label>
            <input
              id="time_to_escalate"
              type="number"
              min={0}
              step={1}
              value={escalate}
              onChange={(e) => {
                setEscalate(e.target.value);
                setSaved(false);
              }}
              className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white placeholder-slate-500 focus:border-teal-400 focus:outline-none"
            />
            <p className="text-xs text-slate-500">
              {t("settings.escalate.help")}
              {minutes !== null && (
                <span className="ml-1 text-slate-400">
                  {t("settings.escalate.approx", { minutes })}
                </span>
              )}
            </p>
          </section>

          {error && <p className="text-sm text-red-400">{error}</p>}
          {saved && (
            <p className="text-sm text-teal-400">{t("settings.saved")}</p>
          )}

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={submitting || !valid}
              className="rounded-xl bg-teal-400 px-6 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-300 disabled:opacity-60"
            >
              {submitting ? t("settings.saving") : t("settings.save")}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

interface TimeInputProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}

/** Labeled 24h time picker (native `HH:MM`). */
function TimeInput({ id, label, value, onChange }: TimeInputProps) {
  return (
    <div>
      <label
        htmlFor={id}
        className="mb-1 block text-xs font-medium text-slate-400"
      >
        {label}
      </label>
      <input
        id={id}
        type="time"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-2.5 text-sm text-white focus:border-teal-400 focus:outline-none"
      />
    </div>
  );
}

export default SettingsPage;
