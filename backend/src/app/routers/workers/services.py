"""Business logic for `POST /cloud_job` — the async worker entrypoint.

`dispatch_job` already never raises (it classifies and swallows both
functional and system failures per the async skill's contract), but this
wrapper is defensive on top of that: whatever happens, this endpoint must
still ack (Cloud Tasks retries indefinitely on a non-2xx, and retry
ownership belongs to the dispatcher, not the transport).
"""

import logging

from src.app.async_jobs import dispatch_job

from src.app.routers.workers.modelsIn import CloudJobIn
from src.app.routers.workers.modelsOut import CloudJobAckOut

logger = logging.getLogger(__name__)


def process_cloud_job(payload: CloudJobIn) -> CloudJobAckOut:
    try:
        dispatch_job(
            payload.job_type,
            payload.namespace_id,
            payload.payload or {},
            job_id=payload.job_id,
        )
    except Exception:
        # Defensive: dispatch_job already swallows handler errors, but this
        # endpoint must never fail to ack regardless of what goes wrong.
        logger.exception(
            f"process_cloud_job: unexpected error dispatching job_type="
            f"'{payload.job_type}' (job_id={payload.job_id})."
        )
    return CloudJobAckOut(job_id=payload.job_id)
