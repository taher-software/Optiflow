from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from src.app.core.api_response import ApiResponse
from src.app.core.deps import get_current_user, require_roles
from src.app.globals.enum import DownTimeStatus, Role

from src.app.routers.down_time import services
from src.app.routers.down_time.modelsIn import CreateDownTimeIn
from src.app.routers.down_time.modelsOut import (
    DownTimeAckOut,
    DownTimeOut,
    DownTimePageOut,
    DownTimeSummaryOut,
)

router = APIRouter(prefix="/down-times", tags=["down-times"])

# Only production agents report downtimes (they're the ones on the floor
# when a workstation/line/UAP stop happens).
_down_time_report_scope = require_roles(Role.PRODUCTION_AGENT)


@router.post(
    "",
    response_model=ApiResponse[DownTimeAckOut],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Report a new downtime",
    description=(
        "Reports a downtime in the caller's namespace, scoped at the plant, "
        "UAP, production line, or work station level (`production_scope`). "
        "The matching id field (`uap_id` / `production_line_id` / "
        "`workstation_id`) is required for its scope and is validated "
        "against the caller's namespace, including the cascading "
        "UAP -> production line -> workstation parent/child relationship. "
        "`department` is required (and restricted to `production`/"
        "`maintenance`) only when `down_time_type` is Setup / Changeover.\n\n"
        "This endpoint does not write the downtime ticket synchronously: it "
        "validates the request then dispatches the `add_down_time` async "
        "job (in-process today; a Pub/Sub publish / Cloud Task at the same "
        "call site tomorrow) and immediately returns `202 Accepted` with the "
        "job's id. Restricted to production agents."
    ),
    responses={
        403: {"description": "Caller is not a production agent."},
        422: {
            "description": (
                "Invalid scope/id combination: a missing required id for "
                "the given `production_scope`, an id that does not exist in "
                "the caller's namespace, an id that does not match its "
                "declared parent (e.g. a production line under a different "
                "UAP), or an invalid/missing `department` for a "
                "Setup / Changeover downtime."
            )
        },
    },
)
async def create_down_time(
    payload: CreateDownTimeIn,
    current: dict = Depends(_down_time_report_scope),
) -> ApiResponse[DownTimeAckOut]:
    result = services.create_down_time(
        payload, current["namespace_id"], current["id"]
    )
    return ApiResponse(message="Downtime reported.", data=result)


# NOTE: `/summary` is registered before `/{issue_id}` so the literal path
# segment is matched first — otherwise it would be captured as an `issue_id`
# path parameter (FastAPI/Starlette matches routes in declaration order).
@router.get(
    "/summary",
    response_model=ApiResponse[DownTimeSummaryOut],
    summary="Summarize downtime tickets by status",
    description=(
        "Returns a `{count, average_seconds}` block per lifecycle status "
        "(pending/ongoing/resolved/closed), computed over the caller's "
        "*visible* issues only (see `GET /down-times` for the visibility "
        "rule). `average_seconds` per status: pending = mean(now - "
        "created_at); ongoing = mean(now - acknowledged_at) (skipping "
        "issues missing `acknowledged_at`); resolved = mean(resolved_at - "
        "acknowledged_at); closed = mean(closed_at - resolved_at). It is "
        "`null` when the status has no issue with the timestamps the "
        "average needs. Any authenticated user may call this; the per-role "
        "visibility filter above does the narrowing."
    ),
)
async def get_down_time_summary(
    current: dict = Depends(get_current_user),
) -> ApiResponse[DownTimeSummaryOut]:
    result = services.get_down_time_summary(current)
    return ApiResponse(message="Downtime summary.", data=result)


@router.get(
    "",
    response_model=ApiResponse[DownTimePageOut],
    summary="List downtime tickets",
    description=(
        "Lists downtime tickets in the caller's namespace, newest first, "
        "optionally filtered by `status`, paginated via `limit`/`offset` "
        "(the response carries the page `items` plus `total`/`limit`/"
        "`offset`). Visibility: `owner`, `admin`, `manager`, `production "
        "supervisor`, and `production agent` see every issue in their "
        "namespace; every other role (maintenance/quality/logistic "
        "supervisor & agent) only sees issues whose `process` matches their "
        "own (derived from their role, e.g. 'maintenance agent' -> "
        "'maintenance'). Each issue includes resolved actor names, the "
        "caller's own permission flags "
        "(`can_acknowledge`/`can_resolve`/`can_close`/`can_delete`), and "
        "`time_in_status_seconds` (measured against the namespace's local "
        "now). Any authenticated user may call this; the visibility filter "
        "above does the narrowing, not a role allow-list."
    ),
)
async def list_down_times(
    status_filter: Optional[DownTimeStatus] = Query(
        default=None,
        alias="status",
        description="Optional lifecycle status to filter by.",
    ),
    limit: int = Query(
        default=20, ge=1, le=100, description="Page size (max 100)."
    ),
    offset: int = Query(default=0, ge=0, description="Number of items to skip."),
    current: dict = Depends(get_current_user),
) -> ApiResponse[DownTimePageOut]:
    result = services.list_down_times(
        current,
        status_filter.value if status_filter else None,
        limit=limit,
        offset=offset,
    )
    return ApiResponse(message="Downtime tickets.", data=result)


@router.get(
    "/{issue_id}",
    response_model=ApiResponse[DownTimeOut],
    summary="Get a single downtime ticket",
    description=(
        "Fetches one downtime ticket by id, scoped to the caller's "
        "namespace and visibility (see `GET /down-times`). Any authenticated "
        "user may call this."
    ),
    responses={
        404: {
            "description": (
                "No such ticket in the caller's namespace, or the ticket "
                "exists but isn't visible to the caller's role (returned as "
                "404, not 403, so existence isn't leaked across the "
                "visibility boundary)."
            )
        },
    },
)
async def get_down_time(
    issue_id: str,
    current: dict = Depends(get_current_user),
) -> ApiResponse[DownTimeOut]:
    result = services.get_down_time(issue_id, current)
    return ApiResponse(message="Downtime ticket.", data=result)


# --------------------------------------------------------------------------
# Lifecycle transitions: acknowledge -> resolve -> close, and delete.
# Declared under `/{issue_id}/...` action subpaths so they never collide
# with the `/summary` and `/{issue_id}` GET routes above (distinct methods
# and/or subpaths).
# --------------------------------------------------------------------------


@router.post(
    "/{issue_id}/acknowledge",
    response_model=ApiResponse[DownTimeOut],
    summary="Acknowledge a downtime ticket",
    description=(
        "Acknowledges a pending downtime ticket, moving it `pending` -> "
        "`ongoing` and starting the response clock. Restricted to the "
        "ticket's owning process agent (e.g. a 'maintenance agent' for a "
        "maintenance ticket, derived from the ticket's `process`). Returns "
        "the updated ticket, re-serialized so the caller's permission flags "
        "reflect the new status. Rejected with 403 when the ticket's "
        "`down_time_type` is close-only (e.g. material shortage / 'others') "
        "— those tickets skip acknowledge entirely and go straight "
        "`pending` -> `closed`."
    ),
    responses={
        403: {
            "description": (
                "Caller is not the ticket's owning process agent, or the "
                "ticket's `down_time_type` is close-only and cannot be "
                "acknowledged."
            )
        },
        404: {"description": "No such ticket in the caller's namespace."},
        409: {"description": "Ticket is not currently `pending`."},
    },
)
async def acknowledge_down_time(
    issue_id: str,
    current: dict = Depends(get_current_user),
) -> ApiResponse[DownTimeOut]:
    result = services.acknowledge_down_time(issue_id, current)
    return ApiResponse(message="Downtime ticket acknowledged.", data=result)


@router.post(
    "/{issue_id}/resolve",
    response_model=ApiResponse[DownTimeOut],
    summary="Resolve a downtime ticket",
    description=(
        "Resolves an ongoing downtime ticket, moving it `ongoing` -> "
        "`resolved`. Restricted to the ticket's owning process agent. "
        "Returns the updated ticket, re-serialized so the caller's "
        "permission flags reflect the new status. Rejected with 403 when "
        "the ticket's `down_time_type` is close-only (e.g. material "
        "shortage / 'others') — those tickets skip resolve entirely and go "
        "straight `pending` -> `closed`."
    ),
    responses={
        403: {
            "description": (
                "Caller is not the ticket's owning process agent, or the "
                "ticket's `down_time_type` is close-only and cannot be "
                "resolved."
            )
        },
        404: {"description": "No such ticket in the caller's namespace."},
        409: {"description": "Ticket is not currently `ongoing`."},
    },
)
async def resolve_down_time(
    issue_id: str,
    current: dict = Depends(get_current_user),
) -> ApiResponse[DownTimeOut]:
    result = services.resolve_down_time(issue_id, current)
    return ApiResponse(message="Downtime ticket resolved.", data=result)


@router.post(
    "/{issue_id}/close",
    response_model=ApiResponse[DownTimeOut],
    summary="Close a downtime ticket",
    description=(
        "Closes a downtime ticket, once production has validated the return "
        "to normal. Restricted to production agents. Returns the updated "
        "ticket, re-serialized so the caller's permission flags reflect the "
        "new status. For most tickets this moves `resolved` -> `closed`; "
        "for a close-only `down_time_type` (e.g. material shortage / "
        "'others') acknowledge/resolve are skipped entirely, so this closes "
        "directly from any non-closed status (`pending`, or, for a legacy "
        "ticket created before its type became close-only, `ongoing`/"
        "`resolved`) — only an already-`closed` ticket is rejected."
    ),
    responses={
        403: {"description": "Caller is not a production agent."},
        404: {"description": "No such ticket in the caller's namespace."},
        409: {
            "description": (
                "Ticket is not currently `resolved` (or, for a close-only "
                "`down_time_type`, the ticket is already `closed`)."
            )
        },
    },
)
async def close_down_time(
    issue_id: str,
    current: dict = Depends(get_current_user),
) -> ApiResponse[DownTimeOut]:
    result = services.close_down_time(issue_id, current)
    return ApiResponse(message="Downtime ticket closed.", data=result)


@router.delete(
    "/{issue_id}",
    response_model=ApiResponse[DownTimeOut],
    summary="Delete a downtime ticket",
    description=(
        "Deletes a still-pending downtime ticket and returns the deleted "
        "record. Restricted to the production agent who opened it "
        "(`created_by`) — a ticket already acknowledged, resolved, or "
        "closed can no longer be deleted."
    ),
    responses={
        403: {
            "description": (
                "Caller is not a production agent, or isn't the agent who "
                "opened this ticket."
            )
        },
        404: {"description": "No such ticket in the caller's namespace."},
        409: {"description": "Ticket is not currently `pending`."},
    },
)
async def delete_down_time(
    issue_id: str,
    current: dict = Depends(get_current_user),
) -> ApiResponse[DownTimeOut]:
    result = services.delete_down_time(issue_id, current)
    return ApiResponse(message="Downtime ticket deleted.", data=result)
