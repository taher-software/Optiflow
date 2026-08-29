"""Business logic for the async worker entrypoints (`POST /cloud_job` and
`POST /pubsub_job`).

Looks the handler up in the job registry, runs it, and returns the handler's
own response. Retry is owned by the handler's `backoff` decorator, so both
routes always ack `200` (even after a handler gives up, or on a message that
can never be turned into a valid job) — the broker must not requeue a job
that either succeeded or cannot succeed.

`process_pubsub_push` only transforms the Pub/Sub push envelope into the
flat `CloudJobIn` shape and delegates to `process_cloud_job` — it never
duplicates dispatch logic.
"""

import base64
import binascii
import json
import logging

from pydantic import ValidationError

from src.app.async_jobs import get_job_handler
from src.app.routers.workers.modelsIn import CloudJobIn, PubSubPushIn
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


def process_pubsub_push(envelope: PubSubPushIn) -> CloudJobAckOut:
    """Transform a Pub/Sub push envelope into a `CloudJobIn` and delegate to
    `process_cloud_job`. Any envelope that cannot be turned into a valid job
    is logged at `error` and acked with `CloudJobAckOut(result=None)`, so the
    broker never redelivers a message that can never succeed. A catch-all
    around the whole body guarantees this holds even for failures we did not
    anticipate individually (e.g. a `RecursionError` from pathologically
    nested JSON, or an unexpected exception out of the delegated handler
    call) — this function is designed to never let an exception escape to
    the route, which would otherwise surface as a non-2xx and cause infinite
    redelivery."""

    try:
        return _process_pubsub_push(envelope)
    except Exception:
        # Last-resort guard, see docstring. `logger.exception` already
        # carries the exception and its traceback — do not interpolate it.
        logger.exception(
            "process_pubsub_push: unexpected error while processing push "
            f"envelope (subscription={envelope.subscription}); acking "
            "without processing."
        )
        return CloudJobAckOut(job_id=None, result=None)


def _process_pubsub_push(envelope: PubSubPushIn) -> CloudJobAckOut:
    if envelope.message is None:
        logger.error(
            "process_pubsub_push: push envelope has no 'message' field "
            f"(subscription={envelope.subscription}); acking without processing."
        )
        return CloudJobAckOut(job_id=None, result=None)

    message = envelope.message

    if message.data is None:
        logger.error(
            "process_pubsub_push: message has no 'data' field "
            f"(messageId={message.message_id}, subscription={envelope.subscription}); "
            "acking without processing."
        )
        return CloudJobAckOut(job_id=None, result=None)

    try:
        raw = base64.b64decode(message.data, validate=True)
    except (binascii.Error, ValueError) as exc:
        logger.error(
            "process_pubsub_push: invalid base64 in message.data "
            f"(messageId={message.message_id}, subscription={envelope.subscription}): "
            f"{exc}; acking without processing."
        )
        return CloudJobAckOut(job_id=None, result=None)

    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.error(
            "process_pubsub_push: invalid JSON in decoded message.data "
            f"(messageId={message.message_id}, subscription={envelope.subscription}): "
            f"{exc}; acking without processing."
        )
        return CloudJobAckOut(job_id=None, result=None)

    if not isinstance(decoded, dict):
        logger.error(
            "process_pubsub_push: decoded message.data is not a JSON object "
            f"(messageId={message.message_id}, subscription={envelope.subscription}); "
            "acking without processing."
        )
        return CloudJobAckOut(job_id=None, result=None)

    job_id = decoded.get("job_id")
    job_type = decoded.get("job_type")
    payload = decoded.get("payload")

    try:
        job = CloudJobIn(
            job_id=job_id,
            job_type=job_type,
            namespace_id=decoded.get("namespace_id"),
            payload=payload,
        )
    except ValidationError as exc:
        error_causes = [
            (e["loc"], e["type"])
            for e in exc.errors(include_url=False, include_input=False)
        ]
        logger.error(
            "process_pubsub_push: decoded message cannot be converted to a "
            f"valid job (messageId={message.message_id}, job_id={job_id}, "
            f"job_type={job_type}): {error_causes}; acking without processing."
        )
        return CloudJobAckOut(
            job_id=job_id if isinstance(job_id, str) else None, result=None
        )

    # A message with no `payload` still runs the job, with `{}` in its
    # place, so that gap is worth its own error log — but only when the job
    # is actually going to run. If `job_type` is unknown, nothing runs at
    # all: `process_cloud_job` below already logs that as the real problem,
    # and logging "missing payload" on top of it would be a second,
    # misleading error about a message that never executed.
    # This is a read-only lookup to decide whether to log, not a dispatch —
    # the actual call still goes exclusively through `process_cloud_job`.
    job_will_run = get_job_handler(job.job_type) is not None
    if payload is None and job_will_run:
        logger.error(
            "process_pubsub_push: decoded message has no 'payload'; running "
            f"handler with {{}} (messageId={message.message_id}, "
            f"job_id={job_id}, job_type={job_type})."
        )

    return process_cloud_job(job)
