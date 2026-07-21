from typing import Optional

from pydantic import BaseModel, Field


class CloudJobAckOut(BaseModel):
    """Ack returned to Cloud Tasks / Pub/Sub once the push has been
    accepted for processing. Always `200`/success from this endpoint's point
    of view — `dispatch_job` owns retry/give-up semantics internally and
    never lets a handler failure propagate back to the push, since a non-2xx
    here would make Cloud Tasks redeliver the message indefinitely."""

    job_id: Optional[str] = Field(
        default=None, description="Idempotency key of the processed job, if any."
    )
