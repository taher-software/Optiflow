from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
        examples=["8f14e45f-ceea-467e-9c4e-8b0d9d3b1a11"],
    )
    job_type: str = Field(
        ...,
        description="`JobType` string value identifying the handler.",
        examples=["notify_down_time_update"],
    )
    namespace_id: str = Field(
        ...,
        min_length=1,
        description="Tenant (namespace) the job runs under.",
        examples=["plant-lyon-01"],
    )
    payload: Optional[dict] = Field(
        default=None,
        description="Job-specific payload dict.",
        examples=[
            {
                "down_time_id": "dt_9f2a",
                "event": "acknowledged",
                "actor_id": "user_42",
            }
        ],
    )


class PubSubMessageIn(BaseModel):
    """The `message` object of a Pub/Sub push envelope
    (https://cloud.google.com/pubsub/docs/push). Deliberately **permissive**
    (unknown fields ignored, nothing required) — this endpoint must never
    reject an envelope with a 422, or the broker will redeliver a message
    that can never succeed forever. Malformed/missing fields are instead
    handled and logged by `services.process_pubsub_push`."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    data: Optional[str] = Field(
        default=None,
        description=(
            "Base64-encoded JSON body, exactly what "
            "`PubSubInteraction.publish_job` published: "
            "`{job_id, job_type, namespace_id, payload, ...}`."
        ),
        examples=[
            (
                "eyJqb2JfaWQiOiAiOGYxNGU0NWYtY2VlYS00NjdlLTljNGUtOGIwZDlkM2Ix"
                "YTExIiwgImpvYl90eXBlIjogIm5vdGlmeV9kb3duX3RpbWVfdXBkYXRlIiwg"
                "Im5hbWVzcGFjZV9pZCI6ICJwbGFudC1seW9uLTAxIiwgInBheWxvYWQiOiB7"
                "ImRvd25fdGltZV9pZCI6ICJkdF85ZjJhIiwgImV2ZW50IjogImFja25vd2xl"
                "ZGdlZCIsICJhY3Rvcl9pZCI6ICJ1c2VyXzQyIn19"
            )
        ],
    )
    message_id: Optional[str] = Field(
        default=None,
        alias="messageId",
        description="Pub/Sub-assigned message id, used only for logging/correlation.",
        examples=["10406043493934219"],
    )
    publish_time: Optional[str] = Field(
        default=None,
        alias="publishTime",
        description="Publish timestamp, informational only.",
        examples=["2026-08-28T10:00:00.123Z"],
    )
    attributes: Optional[dict] = Field(
        default=None,
        description="Pub/Sub message attributes, informational only.",
        examples=[{}],
    )


class PubSubPushIn(BaseModel):
    """A Pub/Sub push subscription HTTP request body. Also **permissive**:
    a push envelope missing `message` must still ack `200` (never a 422),
    so `message` is optional here — its absence is handled and logged by
    `services.process_pubsub_push`."""

    model_config = ConfigDict(extra="ignore")

    message: Optional[PubSubMessageIn] = Field(
        default=None,
        description="The published message; only absent on a malformed push.",
        examples=[
            {
                "data": (
                    "eyJqb2JfaWQiOiAiOGYxNGU0NWYtY2VlYS00NjdlLTljNGUtOGIwZDlk"
                    "M2IxYTExIiwgImpvYl90eXBlIjogIm5vdGlmeV9kb3duX3RpbWVfdXBk"
                    "YXRlIiwgIm5hbWVzcGFjZV9pZCI6ICJwbGFudC1seW9uLTAxIiwgInBh"
                    "eWxvYWQiOiB7ImRvd25fdGltZV9pZCI6ICJkdF85ZjJhIiwgImV2ZW50"
                    "IjogImFja25vd2xlZGdlZCIsICJhY3Rvcl9pZCI6ICJ1c2VyXzQyIn19"
                ),
                "messageId": "10406043493934219",
                "publishTime": "2026-08-28T10:00:00.123Z",
                "attributes": {},
            }
        ],
    )
    subscription: Optional[str] = Field(
        default=None,
        description="Full subscription resource name, used only for logging/correlation.",
        examples=["projects/optiflow-prod/subscriptions/worker-push"],
    )
