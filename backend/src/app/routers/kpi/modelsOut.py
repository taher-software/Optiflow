from typing import Optional

from pydantic import BaseModel, Field


class BaseKpis(BaseModel):
    """The 4 headline KPIs, computed the same way for any ticket slice (plant,
    a breakdown row, a drill-down, ...) — see `.claude/specs/kpi-dashboard.md`
    §5bis for the exact definitions. Availability was removed in revision 2
    (no reliable planned-resources denominator).

    This is also the shape of a `Kpis.bottleneck`/`Kpis.critical` division —
    each type slice carries exactly these 4 fields, never a nested division
    of its own (a workstation has exactly one type)."""

    downtime_seconds: int = Field(
        ...,
        description=(
            "Summed per-ticket (period-clamped) downtime, seconds, weighted "
            "by the number of workstations each ticket's scope affects "
            "(§5bis.1bis) — a plant-wide ticket counts once per workstation "
            "in the namespace, a line ticket once per workstation on that "
            "line, etc., floored at 1."
        ),
    )
    count: int = Field(..., description="Number of tickets in the slice (unweighted).")
    mttr_seconds: int = Field(
        ..., description="Mean created_at -> resolved_at over CLOSED tickets only, seconds."
    )
    mtbf_seconds: Optional[int] = Field(
        default=None,
        description=(
            "Planned time of the slice's period divided by `count`; equals "
            "the planned time itself when `count` is 0. `None` when the "
            "slice has no meaningful planned-time denominator (unconfigured "
            "namespace planned time, or a breakdown row that doesn't carry "
            "its own planned time — e.g. by_location/by_type)."
        ),
    )


class Kpis(BaseKpis):
    """`BaseKpis` plus the two workstation-type divisions the dashboard cards
    split by (`WorkstationType`: standard/bottleneck/critical). The 4
    headline fields stay at the ROOT (unchanged consumers keep reading
    `kpis.downtime_seconds` etc.) — `standard` is never exposed as its own
    division, it is simply "the rest" of the root not covered by the other
    two.

    `bottleneck`/`critical` are `None` when the object's OWN perimeter
    (namespace for `overall`/`by_shift`, the UAP for a `uap` row, the line
    for a `line` row, the path's deepest location for a drill-down) holds NO
    workstation of that type at all — never rendered as a zeroed division in
    that case. They are present WITH ZEROS when the perimeter does hold
    workstations of that type but none had downtime in the period — `0`
    there genuinely means "no downtime", not "not applicable". Always
    `None` on a `station`-kind row/path (a workstation already has exactly
    one type, so splitting its own row by type is meaningless) and on
    `by_type`/`pareto_by_process`/`repair_by_process`."""

    bottleneck: Optional[BaseKpis] = Field(
        default=None,
        description=(
            "This slice's own KPIs for BOTTLENECK-typed workstations in the "
            "object's own perimeter, or `None` when that perimeter holds no "
            "bottleneck workstation at all."
        ),
    )
    critical: Optional[BaseKpis] = Field(
        default=None,
        description=(
            "This slice's own KPIs for CRITICAL-typed workstations in the "
            "object's own perimeter, or `None` when that perimeter holds no "
            "critical workstation at all."
        ),
    )


class BreakdownRow(BaseModel):
    """One row of a dimension breakdown (shift/uap/line/station/process/type)."""

    kind: str = Field(..., description="Dimension kind.")
    id: str = Field(..., description="Dimension value id.")
    label: str = Field(
        ...,
        description=(
            "Display label — the doc name for a location (uap/line/station), "
            "or the raw id for an enumerated dimension (shift/process/type), "
            "which the frontend translates via i18n."
        ),
    )
    kpis: Kpis


class ParetoRow(BaseModel):
    """One row of the process Pareto: share of total downtime + running
    cumulative. Rows are sorted descending by `share`."""

    id: str = Field(..., description="Process id.")
    label: str = Field(..., description="Display label (= id; frontend i18n).")
    share: float = Field(..., description="Share (0..1) of total downtime.")
    cumulative: float = Field(..., description="Running cumulative share (0..1).")


class Bar(BaseModel):
    """A compact analytical bar (seconds or count depending on the section),
    sorted descending by `value`."""

    id: str = Field(..., description="Bar id.")
    label: str = Field(..., description="Display label.")
    value: int = Field(..., description="Value — seconds or a count, per the section.")


class ShiftWindow(BaseModel):
    """One configured shift's real clock window, from the namespace's own
    settings — the source of truth for a shift label's displayed hours
    (e.g. "Équipe 2 (14h-22h)"), never a hardcoded table (§3 of
    `.claude/specs/kpi-dashboard.md`)."""

    id: str = Field(..., description='Shift id, `"1"`/`"2"`/`"3"`.')
    start_time: str = Field(..., description='Shift start, `"HH:MM"`, as stored.')
    end_time: str = Field(..., description='Shift end, `"HH:MM"`, as stored (may wrap midnight).')


class NamespaceMeta(BaseModel):
    """Tenant meta that drives the dashboard's conditional breakdowns."""

    name: str = Field(..., description="Namespace display name (`company_name`, or '').")
    shift_number: int = Field(..., description="Number of shifts the plant runs per day.")
    shifts: list[ShiftWindow] = Field(
        default_factory=list,
        description=(
            "The namespace's actually-configured shift windows, in order "
            "1->2->3 (reuses `_configured_shifts` — same shift-number bound "
            "and unparsable-window skip as the KPI computations). Empty when "
            "the namespace has no settings, or none of its shifts have a "
            "usable window. May have fewer entries than `shift_number` when "
            "a configured shift's window is missing/corrupted."
        ),
    )
    uap_count: int = Field(..., description="Number of UAPs in the namespace.")
    line_count: int = Field(..., description="Number of production lines in the namespace.")
    station_count: int = Field(..., description="Number of workstations in the namespace.")


class DashboardData(BaseModel):
    """Full-screen payload for `GET /kpi/dashboard`."""

    namespace: NamespaceMeta
    overall: Kpis
    by_shift: list[BreakdownRow] = Field(default_factory=list)
    by_location: list[BreakdownRow] = Field(default_factory=list)
    pareto_by_process: list[ParetoRow] = Field(default_factory=list)
    repair_by_process: list[Bar] = Field(default_factory=list)
    by_type: list[BreakdownRow] = Field(default_factory=list)


class DrilldownData(BaseModel):
    """Payload for `GET /kpi/drilldown`. A section is `None` (omitted) when
    its dimension is already fixed by the path/query filters — never an
    empty list in that case, so the frontend can tell "not applicable" apart
    from "applicable but empty"."""

    kpis: Kpis
    children: Optional[list[BreakdownRow]] = Field(
        default=None, description="Next hierarchy level's rows, or `None` for a leaf (station)."
    )
    children_hint_key: Optional[str] = Field(
        default=None, description="i18n key explaining the `children` level."
    )
    pareto_by_process: Optional[list[ParetoRow]] = Field(default=None)
    repair_by_process: Optional[list[Bar]] = Field(default=None)
    downtime_by_shift: Optional[list[Bar]] = Field(default=None)
    downtime_by_type: Optional[list[Bar]] = Field(default=None)
    mttr_by_agent: Optional[list[Bar]] = Field(default=None)
    count_by_agent: Optional[list[Bar]] = Field(default=None)


class DailyPoint(BaseModel):
    """One local-calendar-day bucket for `GET /kpi/daily`."""

    date: str = Field(..., description="ISO calendar date `YYYY-MM-DD`.")
    value: int = Field(..., description="Bucketed value for the requested metric.")


class DailyPointsOut(BaseModel):
    """Payload for `GET /kpi/daily`."""

    points: list[DailyPoint] = Field(default_factory=list)
