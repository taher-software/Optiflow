from typing import Optional

from pydantic import BaseModel, Field


class DownTimeAckOut(BaseModel):
    """Acknowledgement returned when a downtime report has been accepted and
    handed off to the async worker. The ticket itself is not created
    synchronously — `job_id` is the idempotency key the `add_down_time` async
    job uses as the eventual issue document id, so callers can use it to poll
    or correlate once the ticket lands."""

    job_id: str = Field(
        ...,
        description=(
            "Idempotency key for the dispatched `add_down_time` job; also "
            "the id the downtime ticket ('issue') will be created under."
        ),
    )


class DownTimeOut(BaseModel):
    """A downtime ticket ("issue"), enriched for the caller: resolved actor
    names, the caller's own permission flags on this issue, and the elapsed
    time in the current status."""

    id: str = Field(..., description="Issue id.")
    namespace_id: str = Field(..., description="Tenant (namespace/plant) id.")
    created_at: str = Field(
        ..., description="ISO timestamp (namespace tz) the ticket was opened."
    )
    updated_at: str = Field(
        ..., description="ISO timestamp (namespace tz) of the last update."
    )
    down_time_scope: str = Field(
        ..., description="Granularity the downtime was declared at."
    )
    uap_id: Optional[str] = Field(default=None, description="UAP id, if scoped to one.")
    production_line_id: Optional[str] = Field(
        default=None, description="Production line id, if scoped to one."
    )
    workstation_id: Optional[str] = Field(
        default=None, description="Workstation id, if scoped to one."
    )
    down_time_type: str = Field(..., description="Root cause category.")
    department: Optional[str] = Field(
        default=None,
        description="Department override for Setup/Changeover tickets, if any.",
    )
    process: str = Field(
        ..., description="Process/department that owns this ticket."
    )
    status: str = Field(
        ..., description="Current lifecycle status: pending/ongoing/resolved/closed."
    )
    created_by: str = Field(..., description="Id of the user who reported the ticket.")
    created_by_name: Optional[str] = Field(
        default=None, description="Full name of `created_by`, if resolvable."
    )
    acknowledged_at: Optional[str] = Field(
        default=None, description="ISO timestamp the ticket was acknowledged, if any."
    )
    acknowledged_by: Optional[str] = Field(
        default=None, description="Id of the user who acknowledged the ticket, if any."
    )
    acknowledged_by_name: Optional[str] = Field(
        default=None, description="Full name of `acknowledged_by`, if resolvable."
    )
    resolved_at: Optional[str] = Field(
        default=None, description="ISO timestamp the ticket was resolved, if any."
    )
    resolved_by: Optional[str] = Field(
        default=None, description="Id of the user who resolved the ticket, if any."
    )
    resolved_by_name: Optional[str] = Field(
        default=None, description="Full name of `resolved_by`, if resolvable."
    )
    closed_at: Optional[str] = Field(
        default=None, description="ISO timestamp the ticket was closed, if any."
    )
    closed_by: Optional[str] = Field(
        default=None, description="Id of the user who closed the ticket, if any."
    )
    closed_by_name: Optional[str] = Field(
        default=None, description="Full name of `closed_by`, if resolvable."
    )
    rejected_at: Optional[str] = Field(
        default=None,
        description=(
            "ISO timestamp (namespace tz) production last sent a resolution "
            "back on this ticket, if any."
        ),
    )
    rejected_by: Optional[str] = Field(
        default=None,
        description="Id of the production agent who last rejected the resolution, if any.",
    )
    rejected_by_name: Optional[str] = Field(
        default=None, description="Full name of `rejected_by`, if resolvable."
    )
    rejection_count: int = Field(
        default=0,
        description=(
            "Number of times a resolution on this ticket has been rejected "
            "back to `ongoing`. Defaults to 0 for legacy documents that "
            "predate this field."
        ),
    )
    can_acknowledge: bool = Field(
        ...,
        description=(
            "Whether the caller may acknowledge this ticket now. Always "
            "`false` for a close-only `down_time_type` (e.g. WIP "
            "shortage / 'others') — those tickets skip acknowledge entirely."
        ),
    )
    can_resolve: bool = Field(
        ...,
        description=(
            "Whether the caller may resolve this ticket now. Always `false` "
            "for a close-only `down_time_type` — those tickets skip resolve "
            "entirely."
        ),
    )
    can_close: bool = Field(
        ...,
        description=(
            "Whether the caller may close this ticket now. For a close-only "
            "`down_time_type`, true from any status except `closed` "
            "(instead of requiring `resolved`), since acknowledge/resolve "
            "are skipped and a legacy ticket may already be `ongoing`/"
            "`resolved`."
        ),
    )
    can_reject: bool = Field(
        ...,
        description=(
            "Whether the caller (a production agent) may reject this "
            "ticket's resolution back to `ongoing` now. True only while the "
            "ticket is `resolved` and its `down_time_type` is not "
            "close-only (a close-only ticket never passes through "
            "`resolved`, so this is always `false` for one)."
        ),
    )
    can_delete: bool = Field(
        ..., description="Whether the caller may delete this ticket now."
    )
    time_in_status_seconds: Optional[float] = Field(
        default=None,
        description=(
            "Seconds elapsed since the ticket entered its current status "
            "(pending: since created_at, ongoing: since acknowledged_at, "
            "resolved: since resolved_at, closed: since closed_at). `null` "
            "when the entry timestamp for the current status is missing."
        ),
    )


class DownTimeStatusSummaryOut(BaseModel):
    """Aggregate stats for one downtime status."""

    count: int = Field(..., description="Number of visible issues in this status.")
    average_seconds: Optional[float] = Field(
        default=None,
        description=(
            "Average elapsed time (seconds) for issues in this status, per "
            "the status-specific definition (see `DownTimeSummaryOut`); "
            "`null` when there is no issue with the needed timestamps."
        ),
    )


class DownTimeSummaryOut(BaseModel):
    """Downtime ticket counts/averages, over the caller's visible issues.

    Averages: `pending` = mean(now - created_at); `ongoing` = mean(now -
    acknowledged_at) (skipping issues missing `acknowledged_at`); `resolved` =
    mean(resolved_at - acknowledged_at); `closed` = mean(closed_at -
    resolved_at). `now` is the current time in the namespace's timezone."""

    pending: DownTimeStatusSummaryOut
    ongoing: DownTimeStatusSummaryOut
    resolved: DownTimeStatusSummaryOut
    closed: DownTimeStatusSummaryOut


class DownTimePageOut(BaseModel):
    """A page of downtime tickets plus the pagination envelope."""

    items: list[DownTimeOut] = Field(
        default_factory=list, description="The tickets on this page (newest first)."
    )
    total: int = Field(
        ..., description="Total number of visible (filtered) tickets across all pages."
    )
    limit: int = Field(..., description="Page size applied.")
    offset: int = Field(..., description="Offset applied.")


# --------------------------------------------------------------------------
# GET /down-times/gantt — see `.claude/specs/downtime-gantt.md` §2.
# --------------------------------------------------------------------------


class GanttWindowOut(BaseModel):
    """The production-day window (§2.2) — a shift-derived span that may run
    past midnight for a wrapping last shift."""

    start: str = Field(..., description="ISO datetime (namespace tz), window start.")
    end: str = Field(..., description="ISO datetime (namespace tz), window end.")


class GanttShiftOut(BaseModel):
    """One configured shift, projected onto absolute datetimes of the
    queried production day (§2.2)."""

    shift: str = Field(..., description="Shift number, as a string (e.g. '1').")
    start: str = Field(..., description="ISO datetime (namespace tz), shift start.")
    end: str = Field(..., description="ISO datetime (namespace tz), shift end.")
    break_start: Optional[str] = Field(
        default=None, description="ISO datetime of the shift's break start, if any."
    )
    break_end: Optional[str] = Field(
        default=None, description="ISO datetime of the shift's break end, if any."
    )


class GanttIntervalOut(BaseModel):
    """One down/unconfirmed segment on a resource's row (§2.3), clamped to
    `window` and already merged/subtracted per the state rules."""

    start_time: str = Field(..., description="ISO datetime (namespace tz), segment start.")
    end_time: str = Field(..., description="ISO datetime (namespace tz), segment end.")
    state: str = Field(..., description="'down' or 'unconfirmed'.")


class GanttUapRowOut(BaseModel):
    """One UAP row of the gantt (§2.4)."""

    uap_id: str = Field(..., description="UAP id.")
    name: str = Field(..., description="UAP's stored name (kept even if archived).")
    down_times: list[GanttIntervalOut] = Field(
        default_factory=list, description="This UAP's intervals, sorted by start_time."
    )


class GanttLineRowOut(BaseModel):
    """One production line row of the gantt (§2.4)."""

    line_id: str = Field(..., description="Production line id.")
    name: str = Field(..., description="Line's stored name (kept even if archived).")
    down_times: list[GanttIntervalOut] = Field(
        default_factory=list, description="This line's intervals, sorted by start_time."
    )


class GanttWorkStationRowOut(BaseModel):
    """One workstation row of the gantt (§2.4/§2.5)."""

    workstation_id: str = Field(..., description="Workstation id.")
    name: str = Field(..., description="Station's stored name (kept even if archived).")
    type: str = Field(..., description="Workstation type (standard/bottleneck/critical).")
    down_times: list[GanttIntervalOut] = Field(
        default_factory=list, description="This station's intervals, sorted by start_time."
    )


class DownTimeGanttOut(BaseModel):
    """A day-scoped Gantt of the plant (`GET /down-times/gantt`) — see
    `.claude/specs/downtime-gantt.md` §2 for the full contract. `uaps` /
    `lines` / `work_stations` are always present (possibly empty); without
    `type`, all three may carry rows (§2.4); with `type`, `uaps`/`lines` are
    always empty and `work_stations` holds only the matching-type stations,
    with ancestor downtime propagated onto them (§2.5)."""

    day: str = Field(..., description="Resolved production day, ISO 'YYYY-MM-DD'.")
    window: GanttWindowOut = Field(..., description="The production-day window (§2.2).")
    shifts: list[GanttShiftOut] = Field(
        default_factory=list, description="Configured shifts projected onto `day`."
    )
    uaps: list[GanttUapRowOut] = Field(default_factory=list, description="UAP rows.")
    lines: list[GanttLineRowOut] = Field(
        default_factory=list, description="Production line rows."
    )
    work_stations: list[GanttWorkStationRowOut] = Field(
        default_factory=list, description="Workstation rows."
    )
