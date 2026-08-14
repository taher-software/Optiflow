from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from src.app.globals.enum import Process

# §5bis: a period longer than this is rejected outright — the spec's own
# assumption ("per-plant monthly downtime volumes are small") doesn't hold
# for arbitrarily long ranges, and nothing in the product needs more than a
# year of daily granularity in one call (fix #7).
_MAX_RANGE_DAYS = 366

# `path`'s max step count (fix #11) — generous headroom over the deepest
# realistic breadcrumb (uap>line>station>shift>type>process is 6) while still
# bounding the per-request work `_parse_drill_path`/`_apply_path_step` do.
MAX_PATH_STEPS = 8


class DateRangeIn(BaseModel):
    """Shared `[date_from, date_to]` inclusive calendar-day period. FastAPI
    already parses/validates the raw `date` query params before the router
    constructs one of these (see the `kpi` router), so a malformed date never
    reaches this model."""

    date_from: date = Field(..., description="Period start (inclusive).")
    date_to: date = Field(..., description="Period end (inclusive).")

    @model_validator(mode="after")
    def _reject_oversized_range(self) -> "DateRangeIn":
        if (self.date_to - self.date_from).days > _MAX_RANGE_DAYS:
            raise ValueError(f"to - from must not exceed {_MAX_RANGE_DAYS} days.")
        return self


class DashboardQueryIn(DateRangeIn):
    """Query params for `GET /kpi/dashboard`."""


class DrilldownQueryIn(DateRangeIn):
    """Query params for `GET /kpi/drilldown`."""

    path: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description=(
            "Breadcrumb path: `kind:id` steps separated by `>`, e.g. "
            "`uap:xxx>line:yyy` (kinds: uap/line/station/shift/type/process; "
            f"at most {MAX_PATH_STEPS} steps)."
        ),
    )
    process: Optional[Process] = Field(
        default=None, description="Optional process filter, narrows further."
    )
    shift: Optional[Literal["1", "2", "3"]] = Field(
        default=None, description="Optional shift filter ('1'/'2'/'3'), narrows further."
    )


class DailyQueryIn(DateRangeIn):
    """Query params for `GET /kpi/daily`."""

    metric: Literal["duration", "count", "mttr"] = Field(
        ..., description="Which KPI to bucket per day."
    )
    scope_kind: Literal["plant", "uap", "line", "station"] = Field(
        ..., description="Location scope; `scope_id` is required unless this is 'plant'."
    )
    scope_id: Optional[str] = Field(
        default=None, description="Id within `scope_kind`. Ignored when `scope_kind` is 'plant'."
    )
    process: Optional[Process] = Field(default=None, description="Optional process filter.")
    shift: Optional[Literal["1", "2", "3"]] = Field(
        default=None, description="Optional shift filter ('1'/'2'/'3')."
    )
