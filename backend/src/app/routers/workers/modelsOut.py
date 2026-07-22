from typing import Any, Optional

from pydantic import BaseModel, Field


class CloudJobAckOut(BaseModel):
    """Ack returned to the broker (Cloud Tasks / Pub/Sub) once the push has
    been processed. This endpoint always responds `200` — retry is owned by the
    handler's own `backoff` decorator, and a non-2xx here would make the broker
    redeliver the message indefinitely."""

    job_id: Optional[str] = Field(
        default=None, description="Idempotency key of the processed job, if any."
    )
    result: Optional[Any] = Field(
        default=None,
        description="The handler's own result (e.g. `{status, ...}`), if any.",
    )
