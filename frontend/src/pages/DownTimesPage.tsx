import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { GanttDivision } from "../components/GanttDivision";
import { GanttLegend } from "../components/GanttLegend";
import {
  GANTT_TYPE_FILTERS,
  parseDayParam,
  parseTypeFilter,
  type GanttTypeFilter,
} from "../constants/downTimesGantt";
import { useDownTimesGanttStore } from "../stores/useDownTimesGanttStore";
import { breakBands, hourTicks, windowMs } from "../utils/ganttGeometry";
import { lineRows, stationRows, uapRows } from "../utils/ganttRows";

const filterBtnCls =
  "rounded-lg border px-3.5 py-1.5 text-[13px] font-medium transition-colors";

/** Day-scoped downtime gantt (`GET /down-times/gantt`, spec
 * `.claude/specs/downtime-gantt.md`). One production day at a time — never a
 * range — with an optional workstation-type filter carried by `?type=`.
 * Light theme on the dark shell, like the dashboard and stats pages. */
export function DownTimesPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();

  const data = useDownTimesGanttStore((s) => s.data);
  const day = useDownTimesGanttStore((s) => s.day);
  const type = useDownTimesGanttStore((s) => s.type);
  const loading = useDownTimesGanttStore((s) => s.loading);
  const error = useDownTimesGanttStore((s) => s.error);
  const offline = useDownTimesGanttStore((s) => s.offline);
  const fetchGantt = useDownTimesGanttStore((s) => s.fetchGantt);
  const setDay = useDownTimesGanttStore((s) => s.setDay);
  const setType = useDownTimesGanttStore((s) => s.setType);
  const openFromUrl = useDownTimesGanttStore((s) => s.openFromUrl);

  /* The query params are the single source of truth for the view the visitor
     ARRIVES on: the URL drives the store (and the initial load), the filter
     buttons only rewrite the URL. One direction, so a link shared with
     `?type=bottleneck&day=2026-08-31` lands on exactly the view its author saw
     — and that is the link the dashboard builds when its selected period does
     not contain today.

     `?day=` is read on arrival only; from then on the date picker owns the day
     and a filter click must not drag the view back to the day of the link. */
  const urlDay = parseDayParam(searchParams.get("day"));
  const urlType = parseTypeFilter(searchParams.get("type"));
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current) {
      setType(urlType);
      return;
    }
    opened.current = true;
    openFromUrl(urlDay, urlType);
  }, [urlDay, urlType, setType, openFromUrl]);

  const selectType = (next: GanttTypeFilter) => {
    const params = new URLSearchParams(searchParams);
    if (next) params.set("type", next);
    else params.delete("type");
    setSearchParams(params, { replace: true });
  };

  const win = data ? windowMs(data.window) : null;
  const breaks = win && data ? breakBands(data.shifts, win) : [];
  /* One graduation for the whole page: the axis is repeated under every
     division, but the window it graduates is the same for all of them. */
  const ticks = data ? hourTicks(data.window) : [];
  const uaps = data ? uapRows(data.uaps) : [];
  const lines = data ? lineRows(data.lines) : [];
  const stations = data
    ? stationRows(data.work_stations, (raw) =>
        t(`workstations.types.${raw}`, { defaultValue: raw }),
      )
    : [];
  const isEmpty =
    uaps.length === 0 && lines.length === 0 && stations.length === 0;

  const statusBlock = error ? (
    <ErrorState
      title={
        offline ? t("common.errors.unreachable") : t("common.errors.title")
      }
      detail={offline ? t("common.errors.unreachableHint") : error}
      retryLabel={t("common.errors.retry")}
      onRetry={() => void fetchGantt()}
    />
  ) : !data || !win ? (
    <p className="mt-10 text-[13px] text-[#9ca3af]">
      {loading
        ? t("downTimes.loading")
        : data
          ? t("downTimes.noWindow")
          : t("downTimes.empty")}
    </p>
  ) : null;

  return (
    <div className="min-h-full bg-[#fafafa] px-8 py-8 text-[#16181d]">
      <div className="mx-auto max-w-6xl">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-widest text-[#0d9488]">
              {t("downTimes.eyebrow")}
            </p>
            <h1 className="mt-0.5 text-[22px] font-bold tracking-tight">
              {t("downTimes.title")}
            </h1>
            <p className="mt-1 max-w-xl text-[13px] text-[#4b5563]">
              {t("downTimes.subtitle")}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <label className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-[#9ca3af]">
              {t("downTimes.day")}
              <input
                type="date"
                value={day}
                onChange={(e) => setDay(e.target.value)}
                className="rounded-lg border border-[#d1d5db] bg-white px-2.5 py-1.5 text-[13px] font-normal normal-case tracking-normal text-[#16181d] focus:border-[#0d9488] focus:outline-none"
              />
            </label>
            <div className="flex flex-wrap items-center justify-end gap-2">
              {GANTT_TYPE_FILTERS.map((value) => (
                <button
                  key={value || "all"}
                  type="button"
                  onClick={() => selectType(value)}
                  aria-pressed={type === value}
                  className={`${filterBtnCls} ${
                    type === value
                      ? "border-[#0d9488] bg-[#0d9488] font-semibold text-white"
                      : "border-[#d1d5db] bg-white text-[#4b5563] hover:text-[#16181d]"
                  }`}
                >
                  {t(`downTimes.filter.${value || "all"}`)}
                </button>
              ))}
            </div>
          </div>
        </div>

        {statusBlock ??
          (data && win && (
            <>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-[#e8e8ec] pb-3">
                <p className="text-[12px] text-[#4b5563]">
                  {t("downTimes.windowOf", { day: data.day })}
                  {data.shifts.length === 0 && (
                    <span className="ml-2 text-[11px] text-[#9ca3af]">
                      {t("downTimes.noShifts")}
                    </span>
                  )}
                </p>
                <GanttLegend />
              </div>

              {isEmpty ? (
                <p className="mt-10 text-[13px] text-[#9ca3af]">
                  {type
                    ? t("downTimes.emptyFiltered", {
                        type: t(`downTimes.filter.${type}`),
                      })
                    : t("downTimes.emptyDay")}
                </p>
              ) : (
                /* An empty division is not rendered AT ALL — not even a note.
                   With a type filter the endpoint answers a workstation-only
                   view (spec §2.5), so the UAP and line divisions simply drop
                   out, exactly like a division nothing stopped in. */
                <div className="space-y-4">
                  {uaps.length > 0 && (
                    <GanttDivision
                      title={t("downTimes.divisions.uaps")}
                      rows={uaps}
                      win={win}
                      breaks={breaks}
                      shifts={data.shifts}
                      ticks={ticks}
                    />
                  )}
                  {lines.length > 0 && (
                    <GanttDivision
                      title={t("downTimes.divisions.lines")}
                      rows={lines}
                      win={win}
                      breaks={breaks}
                      shifts={data.shifts}
                      ticks={ticks}
                    />
                  )}
                  {stations.length > 0 && (
                    <GanttDivision
                      title={t("downTimes.divisions.stations")}
                      rows={stations}
                      win={win}
                      breaks={breaks}
                      shifts={data.shifts}
                      ticks={ticks}
                    />
                  )}
                </div>
              )}
            </>
          ))}
      </div>
    </div>
  );
}

export default DownTimesPage;
