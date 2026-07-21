"""Async job dispatch table.

Jobs are triggered (published) via Pub/Sub / Cloud Tasks; the worker router
(`POST /`) receives the push and calls `dispatch_job(...)` with the
`job_type`, `namespace_id`, `payload`, and `job_id` carried by the message.

This module owns:
- The `JobType -> handler` registry.
- `dispatch_job`, the single public entrypoint, which wraps every handler
  call with the retry/backoff + functional-vs-system-failure contract
  described in `.claude/skills/async/SKILL.md`:
    - Idempotency is the handler's responsibility (each handler must be safe
      to run twice for the same `job_id`).
    - Functional failures (invalid input / business condition not met) are
      logged and NOT retried.
    - System failures (transient / external system down) are retried with
      backoff, up to `MAX_RETRIES` attempts; once exhausted, the error is
      logged and swallowed (the caller — a push endpoint — should still
      respond 200 so the message is not endlessly requeued).

Jobs are currently invoked in-process (synchronously); a real Pub/Sub /
Cloud Tasks transport already exists in `src/app/gcp/` and can be wired in
as the push-receiving worker router without changing this module's
contract.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from src.app.globals.enum import JobType

from .add_down_time import add_down_time
from .exceptions import FunctionalJobError, SystemJobError

logger = logging.getLogger(__name__)

# Max attempts for a job that keeps failing with a system (transient) error.
MAX_RETRIES = 3

# Base delay (seconds) for the exponential backoff between retries.
_BACKOFF_BASE_SECONDS = 0.5

JobHandler = Callable[[str, dict, str], None]

# The dispatch table: JobType -> handler(namespace_id, payload, job_id).
JOB_REGISTRY: dict[JobType, JobHandler] = {
    JobType.ADD_DOWN_TIME: add_down_time,
}


def _normalize_job_type(job_type: JobType | str) -> JobType:
    """Accept either a `JobType` member or its raw string value."""
    if isinstance(job_type, JobType):
        return job_type
    return JobType(job_type)


def dispatch_job(
    job_type: JobType | str,
    namespace_id: str,
    payload: dict,
    job_id: str | None = None,
) -> None:
    """
    Dispatch a job to its registered handler, applying the retry/backoff and
    failure-classification contract.

    Args:
        job_type: The `JobType` (or its string value) identifying the handler.
        namespace_id: Tenant (namespace) the job runs under.
        payload: Job-specific payload dict, as produced by the publisher.
        job_id: Idempotency key for this job invocation. If not provided, one
            is not synthesized here — handlers that require idempotency
            (all of them should) expect a stable id from the publisher
            (e.g. the Pub/Sub message id or a caller-generated uuid).

    Returns:
        None. Never raises: functional failures are logged and skipped;
        system failures are retried up to `MAX_RETRIES` then logged and
        swallowed — callers (the worker router) should respond 200
        regardless so the message is not requeued.
    """
    try:
        normalized_type = _normalize_job_type(job_type)
    except ValueError:
        logger.error(f"dispatch_job: unknown job_type '{job_type}', skipping.")
        return

    handler = JOB_REGISTRY.get(normalized_type)
    if handler is None:
        logger.error(
            f"dispatch_job: no handler registered for job_type '{normalized_type}', skipping."
        )
        return

    attempt = 0
    while True:
        attempt += 1
        try:
            handler(namespace_id, payload, job_id)
            return
        except FunctionalJobError as e:
            logger.error(
                f"dispatch_job: functional failure for job_type "
                f"'{normalized_type}' (job_id={job_id}): {e}. Skipping retry."
            )
            return
        except SystemJobError as e:
            if attempt >= MAX_RETRIES:
                logger.error(
                    f"dispatch_job: system failure for job_type "
                    f"'{normalized_type}' (job_id={job_id}) after {attempt} "
                    f"attempt(s), giving up: {e}"
                )
                return
            delay = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                f"dispatch_job: system failure for job_type "
                f"'{normalized_type}' (job_id={job_id}) on attempt {attempt}/"
                f"{MAX_RETRIES}: {e}. Retrying in {delay}s."
            )
            time.sleep(delay)
        except Exception as e:
            # Unclassified errors are treated as system failures (safer
            # default: retry rather than silently drop a job that may have
            # failed transiently), same retry/backoff/give-up path.
            if attempt >= MAX_RETRIES:
                logger.error(
                    f"dispatch_job: unclassified failure for job_type "
                    f"'{normalized_type}' (job_id={job_id}) after {attempt} "
                    f"attempt(s), giving up: {e}"
                )
                return
            delay = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                f"dispatch_job: unclassified failure for job_type "
                f"'{normalized_type}' (job_id={job_id}) on attempt {attempt}/"
                f"{MAX_RETRIES}: {e}. Retrying in {delay}s."
            )
            time.sleep(delay)
