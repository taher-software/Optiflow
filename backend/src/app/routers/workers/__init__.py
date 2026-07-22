from fastapi import APIRouter, status

from src.app.core.api_response import ApiResponse

from src.app.routers.workers import services
from src.app.routers.workers.modelsIn import CloudJobIn
from src.app.routers.workers.modelsOut import CloudJobAckOut

router = APIRouter(tags=["workers"])


@router.post(
    "/cloud_job",
    response_model=ApiResponse[CloudJobAckOut],
    status_code=status.HTTP_200_OK,
    summary="Async worker entrypoint (Cloud Tasks / Pub/Sub push)",
    description=(
        "Receives the push delivery for an async job (`job_type`, "
        "`namespace_id`, optional `payload`/`job_id`), looks the handler up in "
        "the job registry and calls it. **Unauthenticated by our bearer "
        "scheme** — this route is reached only through Cloud Tasks / Pub/Sub "
        "push subscriptions, authenticated at the infra layer via OIDC, not by "
        "our application's bearer token. Always responds `200` (retry is owned "
        "by the handler's own `backoff` decorator, not by HTTP status: a "
        "non-2xx here would make the transport redeliver indefinitely)."
    ),
)
async def cloud_job(payload: CloudJobIn) -> ApiResponse[CloudJobAckOut]:
    result = services.process_cloud_job(payload)
    return ApiResponse(message="Job processed.", data=result)
