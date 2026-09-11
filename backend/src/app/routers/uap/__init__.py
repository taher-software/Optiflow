from fastapi import APIRouter, Depends, status

from src.app.core.api_response import ApiResponse
from src.app.core.deps import require_roles
from src.app.globals.enum import Role

from src.app.routers.uap import services
from src.app.routers.uap.modelsIn import CreateUapIn, UpdateUapIn
from src.app.routers.uap.modelsOut import UapArchiveOut, UapOut

router = APIRouter(prefix="/uaps", tags=["uaps"])

# Owners, admins and production supervisors manage UAPs (Unite Autonome de
# Production / production areas).
_uap_scope = require_roles(Role.OWNER, Role.ADMIN, Role.PRODUCTION_SUPERVISOR)

# Read-only access (list/get) is additionally opened to production agents,
# who need it for the mobile declare-downtime cascading pickers.
_uap_read_scope = require_roles(
    Role.OWNER, Role.ADMIN, Role.PRODUCTION_SUPERVISOR, Role.PRODUCTION_AGENT
)


@router.post(
    "",
    response_model=ApiResponse[UapOut],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new UAP",
    description=(
        "Creates a UAP (Unite Autonome de Production / production area) in the "
        "caller's namespace. `name` must be unique within the namespace "
        "(comparison ignores leading/trailing whitespace and case). Each of "
        "the 8 id lists must reference existing users in the same namespace "
        "whose role matches the list (e.g. `maintenance_agent_ids` members "
        "must have the 'maintenance agent' role). Restricted to owner/admin/"
        "production supervisor."
    ),
    responses={
        403: {"description": "Caller lacks the required role."},
        409: {"description": "A UAP with this name already exists in the caller's namespace."},
        422: {
            "description": (
                "A referenced user id does not exist, is not in this "
                "namespace, or does not have the expected role for its list."
            )
        },
    },
)
async def create_uap(
    payload: CreateUapIn,
    current: dict = Depends(_uap_scope),
) -> ApiResponse[UapOut]:
    result = services.create_uap(payload, current["namespace_id"])
    return ApiResponse(message="UAP created.", data=result)


@router.get(
    "",
    response_model=ApiResponse[list[UapOut]],
    summary="List UAPs",
    description=(
        "Lists all UAPs in the caller's namespace. Restricted to "
        "owner/admin/production supervisor/production agent."
    ),
)
async def list_uaps(
    current: dict = Depends(_uap_read_scope),
) -> ApiResponse[list[UapOut]]:
    return ApiResponse(data=services.list_uaps(current["namespace_id"]))


@router.get(
    "/{uap_id}",
    response_model=ApiResponse[UapOut],
    summary="Get a UAP",
    description=(
        "Fetches one UAP by id. Restricted to owner/admin/production "
        "supervisor/production agent."
    ),
    responses={404: {"description": "UAP not found in the caller's namespace."}},
)
async def get_uap(
    uap_id: str,
    current: dict = Depends(_uap_read_scope),
) -> ApiResponse[UapOut]:
    return ApiResponse(data=services.get_uap(uap_id, current["namespace_id"]))


@router.put(
    "/{uap_id}",
    response_model=ApiResponse[UapOut],
    summary="Update a UAP",
    description=(
        "Partially updates a UAP in the caller's namespace. If `name` is "
        "provided it must be unique within the namespace (comparison ignores "
        "leading/trailing whitespace and case; the UAP being updated is "
        "excluded from the comparison, so keeping the same name, even with a "
        "different case, never conflicts). Any of the 8 id lists that is "
        "omitted (`None`) is left untouched; a provided list (even an empty "
        "one) fully replaces the existing one, after validation. Restricted "
        "to owner/admin/production supervisor."
    ),
    responses={
        404: {"description": "UAP not found in the caller's namespace."},
        409: {"description": "A UAP with this name already exists in the caller's namespace."},
        422: {
            "description": (
                "A referenced user id does not exist, is not in this "
                "namespace, or does not have the expected role for its list."
            )
        },
    },
)
async def update_uap(
    uap_id: str,
    payload: UpdateUapIn,
    current: dict = Depends(_uap_scope),
) -> ApiResponse[UapOut]:
    result = services.update_uap(uap_id, payload, current["namespace_id"])
    return ApiResponse(message="UAP updated.", data=result)


@router.delete(
    "/{uap_id}",
    response_model=ApiResponse[UapArchiveOut],
    summary="Archive a UAP",
    description=(
        "Archives a UAP in the caller's namespace — irreversibly: there is "
        "no way to undo this. The UAP immediately disappears from every "
        "list and from `GET /uaps/{uap_id}` (which then behaves as not "
        "found), but its past downtime tickets are kept so they keep "
        "counting in the plant's KPIs. Archiving cascades: every production "
        "line attached to this UAP, and every workstation attached to one "
        "of those lines, is archived along with it (an independent line or "
        "workstation is left untouched). Archiving an already-archived UAP "
        "is a no-op that still returns 200. Restricted to owner/admin/"
        "production supervisor."
    ),
    responses={404: {"description": "UAP not found in the caller's namespace."}},
)
async def delete_uap(
    uap_id: str,
    current: dict = Depends(_uap_scope),
) -> ApiResponse[UapArchiveOut]:
    result = services.delete_uap(uap_id, current["namespace_id"])
    return ApiResponse(message="UAP archived.", data=result)
