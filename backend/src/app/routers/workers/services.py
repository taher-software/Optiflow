"""Business logic for `POST /cloud_job` — the async worker entrypoint.

Looks the handler up in the job registry, runs it, and returns the handler's
own response. Retry is owned by the handler's `backoff` decorator, so this
route always acks `200` (even after a handler gives up) — the broker must not
requeue a job that either succeeded or cannot succeed.
"""

import logging

from src.app.async_jobs import get_job_handler

from src.app.routers.workers.modelsIn import CloudJobIn
from src.app.routers.workers.modelsOut import CloudJobAckOut

logger = logging.getLogger(__name__)


def process_cloud_job(payload: CloudJobIn) -> CloudJobAckOut:
    handler = get_job_handler(payload.job_type)
    if handler is None:
        logger.error(
            f"process_cloud_job: no handler for job_type '{payload.job_type}' "
            f"(job_id={payload.job_id}); acking without processing."
        )
        return CloudJobAckOut(job_id=payload.job_id, result=None)

    result = handler(payload.namespace_id, payload.payload or {}, payload.job_id)
    return CloudJobAckOut(job_id=payload.job_id, result=result)
