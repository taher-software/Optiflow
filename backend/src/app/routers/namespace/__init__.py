from fastapi import APIRouter, Depends, Path

from src.app.core.api_response import ApiResponse
from src.app.core.deps import require_api_key

from src.app.routers.namespace import services
from src.app.routers.namespace.modelsOut import NamespaceCleanupOut

router = APIRouter(
    prefix="/namespaces", tags=["namespaces"], dependencies=[Depends(require_api_key)]
)

# Every id this backend generates for a namespace/user/etc. is a `str(uuid.uuid4())`
# (see e.g. `tests/factories/namespace.py`'s `NamespaceDocFactory`) — hex digits and
# hyphens. This pattern is deliberately a little more permissive than a strict UUID
# regex (allows underscores, any length up to 128) so it never rejects a
# legitimately-generated id, while still 422-ing obvious junk (path traversal,
# whitespace, empty segments) before it ever reaches a Firestore lookup.
_NAMESPACE_ID_PATTERN = r"^[A-Za-z0-9_-]{1,128}$"


@router.delete(
    "/{namespace_id}",
    response_model=ApiResponse[NamespaceCleanupOut],
    summary="Wipe a namespace and everything it owns",
    description=(
        "Back-office, irreversible deletion of a namespace (tenant) and "
        "every piece of Firestore data it owns: its users, UAPs, "
        "production lines, workstations, downtime tickets "
        "(`down_time/{namespace_id}/issues/*` + the parent doc) and plant "
        "settings (`NamespaceSettings/{namespace_id}/settings/*` + the "
        "parent doc), then the `namespace` doc itself. Runs regardless of "
        "the namespace's subscription state — no confirmation field, no "
        "active-subscription guard. Never touches `plan` (global) or "
        "`temporary_connection` (not namespace-owned).\n\n"
        "Deletion pages keys-only and batches writes (Firestore batched "
        "writes, chunked to 500 operations) so a large tenant is never "
        "loaded into memory at once, and runs in a fixed order — see "
        "`routers.namespace.services` for why — so a failed run can be "
        "retried: every step is idempotent and the namespace doc, deleted "
        "last, keeps `DELETE` meaningfully retriable until it fully "
        "succeeds. Deleted user emails become free for a new registration. "
        "Pending Cloud Tasks (e.g. an escalation cycle on a still-open "
        "ticket) are not cancelled by this call; the escalation handler "
        "finds no namespace/issue when it eventually fires and exits "
        "cleanly (existing behaviour).\n\n"
        "Protected by the platform API key (`X-API-Key`), never by a user "
        "bearer token."
    ),
    responses={
        401: {"description": "Missing or invalid platform API key."},
        404: {"description": "Namespace not found."},
        422: {"description": "`namespace_id` is malformed."},
    },
)
def delete_namespace(
    namespace_id: str = Path(
        ...,
        pattern=_NAMESPACE_ID_PATTERN,
        description="Id of the namespace to wipe.",
        examples=["5b2f1d3e-df3a-4a9e-9c2b-1a2b3c4d5e6f"],
    ),
) -> ApiResponse[NamespaceCleanupOut]:
    result = services.delete_namespace(namespace_id)
    return ApiResponse(message="Namespace deleted.", data=result)
