from fastapi import APIRouter, Depends, status

from src.app.core.api_response import ApiResponse
from src.app.core.deps import require_roles
from src.app.globals.enum import Role

from src.app.routers.workstation import services
from src.app.routers.workstation.modelsIn import CreateWorkstationIn, UpdateWorkstationIn
from src.app.routers.workstation.modelsOut import WorkstationArchiveOut, WorkstationOut

router = APIRouter(prefix="/workstations", tags=["workstations"])

# Owners, admins and production supervisors manage workstations.
_workstation_scope = require_roles(Role.OWNER, Role.ADMIN, Role.PRODUCTION_SUPERVISOR)

# Read-only access (list/get) is additionally opened to production agents,
# who need it for the mobile declare-downtime cascading pickers.
_workstation_read_scope = require_roles(
    Role.OWNER, Role.ADMIN, Role.PRODUCTION_SUPERVISOR, Role.PRODUCTION_AGENT
)


@router.post(
    "",
    response_model=ApiResponse[WorkstationOut],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workstation",
    description=(
        "Creates a workstation in the caller's namespace. `name` must be "
        "unique within the namespace (comparison ignores leading/trailing "
        "whitespace and case). `production_line_id` is optional: omit it (or "
        "send `null`) for an independent workstation not attached to any "
        "production line; if provided it must reference an existing "
        "production line in the same namespace. `type` must be one of the "
        "`WorkstationType` values. Restricted to owner/admin/production "
        "supervisor."
    ),
    responses={
        403: {"description": "Caller lacks the required role."},
        409: {
            "description": (
                "A workstation with this name already exists in the caller's "
                "namespace."
            )
        },
        422: {
            "description": (
                "`production_line_id` does not reference an existing "
                "production line in this namespace, or `type` is invalid."
            )
        },
    },
)
async def create_workstation(
    payload: CreateWorkstationIn,
    current: dict = Depends(_workstation_scope),
) -> ApiResponse[WorkstationOut]:
    result = services.create_workstation(payload, current["namespace_id"])
    return ApiResponse(message="Workstation created.", data=result)


@router.get(
    "",
    response_model=ApiResponse[list[WorkstationOut]],
    summary="List workstations",
    description=(
        "Lists all workstations in the caller's namespace. Restricted to "
        "owner/admin/production supervisor/production agent."
    ),
)
async def list_workstations(
    current: dict = Depends(_workstation_read_scope),
) -> ApiResponse[list[WorkstationOut]]:
    return ApiResponse(data=services.list_workstations(current["namespace_id"]))


@router.get(
    "/{station_id}",
    response_model=ApiResponse[WorkstationOut],
    summary="Get a workstation",
    description=(
        "Fetches one workstation by id. Restricted to owner/admin/production "
        "supervisor/production agent."
    ),
    responses={404: {"description": "Workstation not found in the caller's namespace."}},
)
async def get_workstation(
    station_id: str,
    current: dict = Depends(_workstation_read_scope),
) -> ApiResponse[WorkstationOut]:
    return ApiResponse(data=services.get_workstation(station_id, current["namespace_id"]))


@router.put(
    "/{station_id}",
    response_model=ApiResponse[WorkstationOut],
    summary="Update a workstation",
    description=(
        "Partially updates a workstation in the caller's namespace. If "
        "`name` is provided it must be unique within the namespace "
        "(comparison ignores leading/trailing whitespace and case; the "
        "workstation being updated is excluded from the comparison, so "
        "keeping the same name, even with a different case, never "
        "conflicts). A field omitted from the request body is left "
        "untouched. `production_line_id` uses tri-state semantics: omit it "
        "to leave the current attachment unchanged, provide a valid id to "
        "attach/re-attach the workstation to that production line, or "
        "explicitly provide `null` to detach it (making it independent). "
        "Restricted to owner/admin/production supervisor."
    ),
    responses={
        404: {"description": "Workstation not found in the caller's namespace."},
        409: {
            "description": (
                "A workstation with this name already exists in the caller's "
                "namespace."
            )
        },
        422: {
            "description": (
                "`production_line_id` does not reference an existing "
                "production line in this namespace, or `type` is invalid."
            )
        },
    },
)
async def update_workstation(
    station_id: str,
    payload: UpdateWorkstationIn,
    current: dict = Depends(_workstation_scope),
) -> ApiResponse[WorkstationOut]:
    result = services.update_workstation(station_id, payload, current["namespace_id"])
    return ApiResponse(message="Workstation updated.", data=result)


@router.delete(
    "/{station_id}",
    response_model=ApiResponse[WorkstationArchiveOut],
    summary="Archive a workstation",
    description=(
        "Archives a workstation in the caller's namespace — irreversibly: "
        "there is no way to undo this. The workstation immediately "
        "disappears from every list and from `GET /workstations/"
        "{station_id}` (which then behaves as not found), but its past "
        "downtime tickets are kept so they keep counting in the plant's "
        "KPIs, and no new ticket can target it. A workstation has no "
        "children, so archiving it never cascades. Archiving an "
        "already-archived workstation is a no-op that still returns 200. "
        "Restricted to owner/admin/production supervisor."
    ),
    responses={404: {"description": "Workstation not found in the caller's namespace."}},
)
async def delete_workstation(
    station_id: str,
    current: dict = Depends(_workstation_scope),
) -> ApiResponse[WorkstationArchiveOut]:
    result = services.delete_workstation(station_id, current["namespace_id"])
    return ApiResponse(message="Workstation archived.", data=result)
