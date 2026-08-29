from typing import Any, Optional

from pydantic import BaseModel, Field


class CloudJobAckOut(BaseModel):
    """Ack returned to the broker (Cloud Tasks / Pub/Sub) once the push has
    been processed. This endpoint always responds `200` — retry is owned by the
    handler's own `backoff` decorator, and a non-2xx here would make the broker
    redeliver the message indefinitely."""

    job_id: Optional[str] = Field(
        default=None,
        description="Idempotency key of the processed job, if any.",
        examples=["8f14e45f-ceea-467e-9c4e-8b0d9d3b1a11"],
    )
    result: Optional[Any] = Field(
        default=None,
        description="The handler's own result (e.g. `{status, ...}`), if any.",
        examples=[{"status": "notified", "recipients": 2}],
    )
