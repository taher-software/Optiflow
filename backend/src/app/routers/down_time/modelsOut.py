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
    can_acknowledge: bool = Field(
        ...,
        description=(
            "Whether the caller may acknowledge this ticket now. Always "
            "`false` for a close-only `down_time_type` (e.g. material "
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
