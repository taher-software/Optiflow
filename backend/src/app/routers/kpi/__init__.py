from datetime import date
from typing import Literal, Optional, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from src.app.core.api_response import ApiResponse
from src.app.core.deps import require_roles
from src.app.globals.enum import Process, Role

from src.app.routers.kpi import services
from src.app.routers.kpi.modelsIn import DailyQueryIn, DashboardQueryIn, DrilldownQueryIn
from src.app.routers.kpi.modelsOut import DailyPointsOut, DashboardData, DrilldownData

router = APIRouter(prefix="/kpi", tags=["kpi"])

# Dashboard/analytics are a management concern — mirrors the settings
# router's scope (owner/admin/manager/production supervisor).
_kpi_scope = require_roles(Role.OWNER, Role.ADMIN, Role.MANAGER, Role.PRODUCTION_SUPERVISOR)

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _build_query(model_cls: type[_ModelT], **kwargs) -> _ModelT:
    """Constructs a query model from already FastAPI-parsed params, turning
    any of its own validators (date-range ordering/size, ...) that raise into
    a 422 instead of an unhandled `pydantic.ValidationError` — these models
    are built by hand in the endpoint body, not as a FastAPI request
    parameter, so FastAPI never sees/handles the raw `ValidationError`
    itself."""
    try:
        return model_cls(**kwargs)
    except ValidationError as exc:
        # `exc.errors()` embeds the raw exception object (`ctx.error`) which
        # isn't JSON-serializable — pass through only the plain-string bits.
        detail = [
            {"loc": err["loc"], "msg": err["msg"], "type": err["type"]} for err in exc.errors()
        ]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail
        ) from exc


@router.get(
    "/dashboard",
    response_model=ApiResponse[DashboardData],
    summary="Plant KPI dashboard",
    description=(
        "Computes the 4 headline KPIs (downtime, count, MTTR, MTBF) for the "
        "caller's namespace over `[from, to]` (inclusive, ISO `YYYY-MM-DD`, "
        "span capped at 366 days), plus the by-shift / by-location / "
        "pareto-by-process / repair-by-process / by-type breakdowns. "
        "`downtime_seconds` is weighted per ticket by the number of "
        "workstations its scope affects (a plant-wide ticket counts once per "
        "workstation in the namespace, a line ticket once per workstation on "
        "that line, floored at 1) — `count`/`mttr_seconds` are not. "
        "`by_location` picks UAPs when the namespace has more than one, else "
        "production lines when more than one, else workstations. `by_shift` "
        "is empty unless the namespace runs more than one shift and only "
        "includes shifts that carry a configured clock window; tickets "
        "without a stored `shift` are excluded from that breakdown only "
        "(they still count everywhere else). Tickets still open (or closed "
        "but resolved inside the window) from before `from` are carried "
        "over into the downtime-based figures. `mtbf_seconds` is `None` "
        "wherever there's no meaningful planned-time denominator "
        "(by_location/by_type rows, or an unconfigured namespace with an "
        "empty period). See `.claude/specs/kpi-dashboard.md` §5bis for the "
        "exact KPI definitions. Restricted to owner/admin/manager/production "
        "supervisor, tenant-scoped to the caller's namespace."
    ),
    responses={
        403: {"description": "Caller lacks the required role."},
        422: {"description": "`to` is before `from`, or the span exceeds 366 days."},
    },
)
async def get_dashboard(
    from_: date = Query(..., alias="from", description="Period start (inclusive)."),
    to: date = Query(..., description="Period end (inclusive)."),
    current: dict = Depends(_kpi_scope),
) -> ApiResponse[DashboardData]:
    query = _build_query(DashboardQueryIn, date_from=from_, date_to=to)
    result = services.get_dashboard(query, current["namespace_id"])
    return ApiResponse(data=result)


@router.get(
    "/drilldown",
    response_model=ApiResponse[DrilldownData],
    response_model_exclude_none=True,
    summary="Drill into one KPI dimension",
    description=(
        "Narrows the dashboard's tickets along a breadcrumb `path` "
        "(`kind:id` steps separated by `>`, e.g. `uap:xxx>line:yyy`; kinds: "
        "uap/line/station/shift/type/process; at most 8 steps), optionally "
        "narrowed further by `process`/`shift` query params. Returns the "
        "narrowed `kpis`, the next hierarchy level's `children` (derived "
        "from the deepest location step anywhere in the path — UAP -> its "
        "production lines, or straight to stations when the UAP has no "
        "lines; line -> its stations; station -> no children; when the path "
        "has no location step at all, a trailing shift/type/process step "
        "falls back to the dashboard's top location level), and only the "
        "breakdown sections whose own dimension isn't already fixed by the "
        "path/params. A `type` step DOES fix `process`: a downtime type is "
        "analyzed by who intervenes on it, not by process, so a `type` "
        "drill-down never returns `pareto_by_process`/`repair_by_process` "
        "(even though a type can structurally span several processes, since "
        "the process is read per-ticket, not inferred from the type) and "
        "instead returns `mttr_by_agent`/`count_by_agent` — same as "
        "selecting a process directly (via path or the `process` query "
        "param). `children` are unaffected by this: a type still "
        "decorticates by places, never by types. Suppressed sections (their "
        "dimension is fixed by the path/params) are absent from the "
        "response body entirely (not `null`) — EXCEPT `children`, which is "
        "always present and is explicitly `null` for a leaf (station) "
        "depth, so a leaf can be told apart from a `children` list not yet "
        "returned. Restricted to owner/admin/manager/production supervisor."
    ),
    responses={
        403: {"description": "Caller lacks the required role."},
        422: {
            "description": (
                "Malformed `path` / unknown path kind / more than 8 steps / "
                "invalid `process` or `shift`, `to` before `from`, or the "
                "span exceeds 366 days."
            )
        },
    },
)
async def get_drilldown(
    path: str = Query(
        ...,
        min_length=1,
        max_length=512,
        description="Breadcrumb path, e.g. 'uap:xxx>line:yyy' (at most 8 steps).",
    ),
    process: Optional[Process] = Query(default=None, description="Optional process filter."),
    shift: Optional[Literal["1", "2", "3"]] = Query(
        default=None, description="Optional shift filter ('1'/'2'/'3')."
    ),
    from_: date = Query(..., alias="from", description="Period start (inclusive)."),
    to: date = Query(..., description="Period end (inclusive)."),
    current: dict = Depends(_kpi_scope),
) -> JSONResponse:
    query = _build_query(
        DrilldownQueryIn, path=path, process=process, shift=shift, date_from=from_, date_to=to
    )
    result = services.get_drilldown(query, current["namespace_id"])

    # `response_model_exclude_none=True` (above) omits every suppressed
    # section — but `children` is `None` for a MEANINGFUL reason at a
    # station (leaf) depth, distinct from "not applicable" (see
    # `DrilldownData.children`'s own docstring: "or `None` for a leaf
    # (station)"). A blanket exclude can't tell those two `None`s apart, so
    # bypass automatic response_model serialization here and re-add
    # `children` explicitly (even when `None`) after building the same
    # exclude-none payload every other section still gets.
    payload = ApiResponse(data=result).model_dump(exclude_none=True)
    if payload.get("data") is not None:
        payload["data"]["children"] = result.children
    return JSONResponse(content=jsonable_encoder(payload))


@router.get(
    "/daily",
    response_model=ApiResponse[DailyPointsOut],
    summary="Daily KPI series",
    description=(
        "Buckets the caller's namespace tickets into one point per local "
        "calendar day in `[from, to]` (span capped at 366 days) for one "
        "`metric` (duration/count/mttr), optionally narrowed to a "
        "`scope_kind`/`scope_id` (plant/uap/line/station; `scope_id` is "
        "required unless `scope_kind` is 'plant') and/or `process`/`shift`. "
        "A ticket belongs to the day of its `created_at` (namespace tz); "
        "`duration` attributes the ticket's full period-clamped downtime to "
        "that day (a carried-over ticket created before `from` is "
        "attributed wholly to `from`'s bucket rather than split per day), "
        "weighted per ticket by the number of workstations its scope "
        "affects (same rule as `/kpi/dashboard`'s `downtime_seconds`); "
        "`mttr` averages closed tickets created that day (0 when none), "
        "unweighted. Restricted to owner/admin/manager/production supervisor."
    ),
    responses={
        403: {"description": "Caller lacks the required role."},
        422: {
            "description": (
                "Invalid `metric`/`scope_kind`/`process`/`shift`, missing "
                "`scope_id` for a non-plant scope, `to` before `from`, or "
                "the span exceeds 366 days."
            )
        },
    },
)
async def get_daily(
    metric: Literal["duration", "count", "mttr"] = Query(
        ..., description="Which KPI to bucket per day."
    ),
    scope_kind: Literal["plant", "uap", "line", "station"] = Query(
        ..., description="Location scope; `scope_id` required unless 'plant'."
    ),
    scope_id: Optional[str] = Query(default=None, description="Id within `scope_kind`."),
    process: Optional[Process] = Query(default=None, description="Optional process filter."),
    shift: Optional[Literal["1", "2", "3"]] = Query(
        default=None, description="Optional shift filter ('1'/'2'/'3')."
    ),
    from_: date = Query(..., alias="from", description="Period start (inclusive)."),
    to: date = Query(..., description="Period end (inclusive)."),
    current: dict = Depends(_kpi_scope),
) -> ApiResponse[DailyPointsOut]:
    query = _build_query(
        DailyQueryIn,
        metric=metric,
        scope_kind=scope_kind,
        scope_id=scope_id,
        process=process,
        shift=shift,
        date_from=from_,
        date_to=to,
    )
    result = services.get_daily(query, current["namespace_id"])
    return ApiResponse(data=result)
