from fastapi import APIRouter, Depends, status

from src.app.core.api_response import ApiResponse
from src.app.core.deps import get_current_user, require_api_key

from src.app.routers.subscription import services
from src.app.routers.subscription.modelsIn import CreateSubscriptionIn
from src.app.routers.subscription.modelsOut import CatalogPlanOut, SubscriptionOut

router = APIRouter(
    prefix="/subscriptions",
    tags=["subscriptions"],
)


@router.post(
    "",
    response_model=ApiResponse[SubscriptionOut],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
    summary="Subscribe a namespace to a plan",
    description=(
        "Subscribes a namespace to a plan, matched by `plan_name`. Whether "
        "this is a *base* or an *extra* (quota) subscription is decided by "
        "the matched plan's `quota` (`null` => base, touching only "
        "`subscription_plan_id`/`subscription_start_date`/"
        "`subscription_end_date`; non-null => extra, touching only the "
        "`extra_subscription_*` fields and `oiu_generated`). The other "
        "kind's fields are always left untouched.\n\n"
        "The new period's start date is **today** (in the namespace's "
        "timezone, UTC fallback) when `today_start_day` is `true` or there "
        "is no current end date of the same kind; otherwise it starts the "
        "day after the current end date (even if that is in the past). The "
        "end date is `start + plan.duration` days.\n\n"
        "For an extra subscription, `oiu_generated` is added to the "
        "existing balance when the *previous* extra period had already "
        "ended on or before today, or replaced by `plan.quota` otherwise "
        "(no previous period, or a previous period still in the future).\n\n"
        "Returns the namespace's full subscription state after the update. "
        "Protected by the platform API key (`X-API-Key`), never by a user "
        "bearer token."
    ),
    responses={
        401: {"description": "Missing or invalid platform API key."},
        404: {"description": "`namespace_id` does not exist."},
        422: {"description": "`plan_name` matches no plan, or validation error."},
    },
)
async def create_subscription(
    payload: CreateSubscriptionIn,
) -> ApiResponse[SubscriptionOut]:
    result = services.create_subscription(payload)
    return ApiResponse(message="Subscription updated.", data=result)


@router.get(
    "/plans",
    response_model=ApiResponse[list[CatalogPlanOut]],
    status_code=status.HTTP_200_OK,
    summary="List the tenant-facing plan catalog",
    description=(
        "Returns the plan catalog shown on the web subscription/paywall "
        "page: only the plans whose name matches (same trimmed, "
        "case-insensitive comparison as plan-name uniqueness) one of "
        "`Operio Standard`, `Operio Dedicated`, `Operio Intelligence`, "
        "returned in that fixed order. A catalog name with no matching "
        "plan is simply absent from the result. Carries no subscription "
        "status -- that comes only from the login response.\n\n"
        "Protected by a user bearer token (any role), never the platform "
        "API key."
    ),
    responses={
        401: {"description": "Missing or invalid bearer token."},
    },
)
async def list_subscription_plans(
    _user: dict = Depends(get_current_user),
) -> ApiResponse[list[CatalogPlanOut]]:
    result = services.list_catalog_plans()
    return ApiResponse(message="Plan catalog.", data=result)
