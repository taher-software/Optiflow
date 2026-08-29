from fastapi import APIRouter, status

from src.app.core.api_response import ApiResponse
from src.app.routers.workers import services
from src.app.routers.workers.modelsIn import CloudJobIn, PubSubPushIn
from src.app.routers.workers.modelsOut import CloudJobAckOut

router = APIRouter(tags=["workers"])


@router.post(
    "/cloud_job",
    response_model=ApiResponse[CloudJobAckOut],
    status_code=status.HTTP_200_OK,
    summary="Async worker entrypoint (Cloud Tasks only)",
    description=(
        "Receives the **Cloud Tasks** delivery for an async job — the flat "
        "body `{job_type, namespace_id, payload?, job_id?}` — looks the "
        "handler up in the job registry and calls it. Not the Pub/Sub push "
        "target: a Pub/Sub push envelope does not match this flat body and is "
        "rejected with `422` here (see `POST /pubsub_job` for that transport). "
        "**Unauthenticated by our bearer scheme** — this route is reached only "
        "through Cloud Tasks, authenticated at the infra layer via OIDC, not "
        "by our application's bearer token. Always responds `200` (retry is "
        "owned by the handler's own `backoff` decorator, not by HTTP status: a "
        "non-2xx here would make the transport redeliver indefinitely)."
    ),
)
async def cloud_job(payload: CloudJobIn) -> ApiResponse[CloudJobAckOut]:
    result = services.process_cloud_job(payload)
    return ApiResponse(message="Job processed.", data=result)


@router.post(
    "/pubsub_job",
    response_model=ApiResponse[CloudJobAckOut],
    status_code=status.HTTP_200_OK,
    summary="Async worker entrypoint (Pub/Sub push only)",
    description=(
        "Receives the **Pub/Sub push** delivery for a job published by "
        "`PubSubInteraction.publish_job` — the push envelope "
        "`{message: {data: <base64 JSON>, messageId, publishTime, "
        "attributes}, subscription}` — decodes `message.data` into the flat "
        "`{job_id, job_type, namespace_id, payload}` shape (`job_type` is "
        "read from the root of the decoded JSON), then delegates to the same "
        "engine as `POST /cloud_job`. Not the Cloud Tasks target: use "
        "`POST /cloud_job` for that transport.\n\n"
        "**Always responds `200`, even on a malformed or unprocessable "
        "envelope** (missing/invalid `data`, invalid base64, invalid JSON, a "
        "decoded body that is not a valid job, an unknown `job_type`, or a "
        "push with no `message` at all). A non-2xx here would make Pub/Sub "
        "redeliver a message that can never succeed, forever — so every such "
        "case is instead logged at `error` and acked without running a job. "
        "**Unauthenticated by our bearer scheme** — this route is reached "
        "only through the Pub/Sub push subscription, authenticated at the "
        "infra layer via OIDC, not by our application's bearer token."
    ),
)
async def pubsub_job(envelope: PubSubPushIn) -> ApiResponse[CloudJobAckOut]:
    result = services.process_pubsub_push(envelope)
    return ApiResponse(message="Job processed.", data=result)
