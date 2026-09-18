from fastapi import APIRouter, Depends, status

from src.app.core.api_response import ApiResponse
from src.app.core.deps import require_api_key

from src.app.routers.plan import services
from src.app.routers.plan.modelsIn import CreatePlanIn, UpdatePlanIn
from src.app.routers.plan.modelsOut import PlanOut

router = APIRouter(
    prefix="/plans", tags=["plans"], dependencies=[Depends(require_api_key)]
)


@router.post(
    "",
    response_model=ApiResponse[PlanOut],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new commercial plan",
    description=(
        "Creates a platform-level commercial plan (not tenant-scoped). "
        "`name` must be unique across every plan (comparison ignores "
        "leading/trailing whitespace and case). `quota`, when present, "
        "makes this an *extra* (quota) plan; leave it out (or send `null`) "
        "for a *base* plan — see `POST /subscriptions` for how the "
        "distinction is used. Protected by the platform API key "
        "(`X-API-Key`), never by a user bearer token."
    ),
    responses={
        401: {"description": "Missing or invalid platform API key."},
        409: {"description": "A plan with this name already exists."},
    },
)
async def create_plan(payload: CreatePlanIn) -> ApiResponse[PlanOut]:
    result = services.create_plan(payload)
    return ApiResponse(message="Plan created.", data=result)


@router.get(
    "",
    response_model=ApiResponse[list[PlanOut]],
    summary="List commercial plans",
    description=(
        "Lists every commercial plan, sorted by name. Protected by the "
        "platform API key."
    ),
    responses={401: {"description": "Missing or invalid platform API key."}},
)
async def list_plans() -> ApiResponse[list[PlanOut]]:
    return ApiResponse(data=services.list_plans())


@router.get(
    "/{plan_id}",
    response_model=ApiResponse[PlanOut],
    summary="Get a commercial plan",
    description="Fetches one plan by id. Protected by the platform API key.",
    responses={
        401: {"description": "Missing or invalid platform API key."},
        404: {"description": "Plan not found."},
    },
)
async def get_plan(plan_id: str) -> ApiResponse[PlanOut]:
    return ApiResponse(data=services.get_plan(plan_id))


@router.patch(
    "/{plan_id}",
    response_model=ApiResponse[PlanOut],
    summary="Update a commercial plan",
    description=(
        "Partially updates a plan. Any field omitted from the payload is "
        "left untouched. If `name` is provided it must be unique across "
        "every plan (comparison ignores leading/trailing whitespace and "
        "case; the plan being updated is excluded from the comparison). "
        "`quota` follows an omitted-vs-`null` distinction rather than the "
        "value alone: omit it to leave the current quota unchanged, send it "
        "explicitly as `null` to clear it (turning the plan back into a "
        "base plan), or send a non-negative integer to set it. Editing a "
        "plan never touches namespaces already subscribed to it — their "
        "computed dates/quota stay as they are. Protected by the platform "
        "API key."
    ),
    responses={
        401: {"description": "Missing or invalid platform API key."},
        404: {"description": "Plan not found."},
        409: {"description": "A plan with this name already exists."},
    },
)
async def update_plan(plan_id: str, payload: UpdatePlanIn) -> ApiResponse[PlanOut]:
    result = services.update_plan(plan_id, payload)
    return ApiResponse(message="Plan updated.", data=result)


@router.delete(
    "/{plan_id}",
    response_model=ApiResponse[PlanOut],
    summary="Delete a commercial plan",
    description=(
        "Deletes a plan, returning the deleted plan. Rejected with `409` "
        "when any namespace currently references this plan via "
        "`subscription_plan_id` or `extra_subscription_plan_id` — a plan in "
        "use is never deleted. Protected by the platform API key."
    ),
    responses={
        401: {"description": "Missing or invalid platform API key."},
        404: {"description": "Plan not found."},
        409: {"description": "This plan is in use by at least one namespace."},
    },
)
async def delete_plan(plan_id: str) -> ApiResponse[PlanOut]:
    result = services.delete_plan(plan_id)
    return ApiResponse(message="Plan deleted.", data=result)
