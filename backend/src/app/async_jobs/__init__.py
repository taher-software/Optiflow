"""Async job registry.

Flow (see `.claude/skills/async/SKILL.md`): an endpoint **publishes** a job to
Pub/Sub; the worker route `POST /cloud_job` receives the push and looks the
handler up here by `job_type`, then calls it directly. Retry is the handler's
own `backoff` decorator — there is deliberately **no manual dispatcher / retry
loop** in this module. The registry is just `JobType -> handler`.
"""

from __future__ import annotations

from typing import Callable, Optional

from src.app.globals.enum import JobType

from .add_down_time import add_down_time
from .notify_down_time_update import notify_down_time_update

JobHandler = Callable[[str, dict, str], None]

# The registry: JobType -> handler(namespace_id, payload, job_id).
JOB_REGISTRY: dict[JobType, JobHandler] = {
    JobType.ADD_DOWN_TIME: add_down_time,
    JobType.NOTIFY_DOWN_TIME_UPDATE: notify_down_time_update,
}


def get_job_handler(job_type: JobType | str) -> Optional[JobHandler]:
    """Resolve the handler for a job type (accepts a `JobType` or its raw
    string value). Returns None if the type is unknown/unregistered."""
    try:
        key = job_type if isinstance(job_type, JobType) else JobType(job_type)
    except ValueError:
        return None
    return JOB_REGISTRY.get(key)
