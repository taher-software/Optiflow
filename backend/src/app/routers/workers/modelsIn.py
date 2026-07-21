from typing import Optional

from pydantic import BaseModel, Field


class CloudJobIn(BaseModel):
    """Job message pushed by Cloud Tasks / Pub/Sub to the worker endpoint.

    Mirrors what a publisher hands to `dispatch_job` (see
    `src/app/async_jobs/__init__.py`): `job_type` is the `JobType` string
    value, `namespace_id` the tenant the job runs under, `payload` the
    job-specific data, and `job_id` the idempotency key (handlers must be
    safe to run twice for the same id)."""

    job_id: Optional[str] = Field(
        default=None,
        description=(
            "Idempotency key for this job invocation. If omitted, the "
            "underlying handler's own idempotency requirement is not met "
            "and it will treat the call as non-idempotent."
        ),
    )
    job_type: str = Field(
        ..., description="`JobType` string value identifying the handler."
    )
    namespace_id: str = Field(
        ..., min_length=1, description="Tenant (namespace) the job runs under."
    )
    payload: Optional[dict] = Field(
        default=None, description="Job-specific payload dict."
    )
