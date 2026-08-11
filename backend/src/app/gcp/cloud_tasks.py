import logging
from google.cloud import tasks_v2
from google.api_core import exceptions as gcp_exceptions
from src.app.core.config import get_settings
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from src.app.globals.enum import JobType

logger = logging.getLogger(__name__)


class CloudTask:
    """
    Google Cloud Tasks manager for scheduling delayed task execution.

    This class provides an interface to create and manage Cloud Tasks queues
    and schedule tasks with configurable delays.
    """

    def __init__(self, queue_name: str, location: str ="europe-west1"):
        """
        Initialize Cloud Tasks client and create/verify queue.

        Args:
            queue_name: Name of the queue to create/use
            location: GCP region for the queue (default: 'europe-west1')
        """
        self.client = tasks_v2.CloudTasksClient()
        self.location = location
        self.queue_path = self._create_queue_path(queue_name)

    def _create_queue_path(self, queue_name: str) -> str:
        """
        Private method to create queue if it doesn't exist.

        Creates the queue only if it doesn't exist. Properly distinguishes between
        different failure reasons (NotFound vs PermissionDenied, NetworkError, etc.)

        Args:
            queue_name: Name of the queue

        Returns:
            str: Full queue path (projects/PROJECT_ID/locations/LOCATION/queues/QUEUE_NAME)

        Raises:
            ValueError: If Google Project ID is not configured
            PermissionDenied: If lacking permissions to access/create queue
            Unauthenticated: If authentication fails
            DeadlineExceeded: If request times out
        """
        settings = get_settings()
        if not settings.google_project_id:
            logger.warning(
                "Google Project ID is not set. Skipping Cloud Tasks queue initialization."
            )
            raise ValueError("Google Project ID is not set.")

        # Build the queue path
        queue_path = self.client.queue_path(
            settings.google_project_id, self.location, queue_name
        )

        try:
            # Try to get the queue to check if it exists
            self.client.get_queue(request={"name": queue_path})
            logger.info(f"Cloud Tasks queue {queue_path} already exists.")
            return queue_path

        except gcp_exceptions.NotFound:
            # Queue doesn't exist - this is the ONLY case where we should create it
            try:
                parent = self.client.common_location_path(
                    get_settings().google_project_id, self.location
                )
                queue = tasks_v2.Queue(name=queue_path)
                self.client.create_queue(request={"parent": parent, "queue": queue})
                logger.info(f"Successfully created Cloud Tasks queue: {queue_path}")
                return queue_path

            except gcp_exceptions.AlreadyExists:
                # Race condition: queue was created between our check and create attempt
                logger.info(
                    f"Cloud Tasks queue {queue_path} already exists (created concurrently)."
                )
                return queue_path

            except gcp_exceptions.PermissionDenied as e:
                logger.error(f"Permission denied when creating queue {queue_path}: {e}")
                raise

            except Exception as e:
                logger.error(f"Failed to create Cloud Tasks queue {queue_path}: {e}")
                raise

        except gcp_exceptions.PermissionDenied as e:
            # Permission error when checking - don't try to create, just raise
            logger.error(f"Permission denied when accessing queue {queue_path}: {e}")
            raise

        except gcp_exceptions.Unauthenticated as e:
            # Authentication error - credentials issue
            logger.error(f"Authentication failed when accessing Cloud Tasks: {e}")
            raise

        except gcp_exceptions.DeadlineExceeded as e:
            # Timeout error - network or service issue
            logger.error(f"Timeout when accessing queue {queue_path}: {e}")
            raise

        except Exception as e:
            # Any other unexpected error - log and raise
            logger.error(f"Unexpected error when accessing queue {queue_path}: {e}")
            raise

    def create_task(
        self,
        delay: int,
        namespace_id: str,
        job_type: JobType,
        timezone_name: Optional[str] = None,
        guest_id: str = None,
        event_id: int = None,
        payload: Optional[dict] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """
        Schedule a task with specified delay relative to the namespace's local time.

        Args:
            delay: Delay in seconds before task execution (max: 30 days = 2,592,000 seconds)
            namespace_id: Namespace ID to process
            job_type: Type of job from JobType enum
            timezone_name: IANA timezone name of the namespace (e.g. 'Europe/Paris').
                Mirrors `core.timezone.namespace_timezone`: legacy namespace
                documents predate the `timezone` field, so `None`/blank
                defaults to UTC rather than raising.
            guest_id: Optional guest ID (phone number) for guest-specific tasks
            event_id: Optional event ID for event-specific tasks (e.g. event_notif)
            payload: Optional job-specific payload dict, merged into the task
                body under a `"payload"` key — delivered to the worker route's
                `CloudJobIn.payload` exactly like the Pub/Sub path.
            task_id: Optional explicit task id to use as the task name instead
                of minting a fresh UUID. Passing the same `task_id` across
                retries of the *same logical creation* is what makes
                idempotent creation possible for a caller that wants it —
                see `Raises` below: this method itself no longer decides
                whether a repeat is "success"; it surfaces `AlreadyExists` to
                the caller, who is the only one positioned to know what an
                explicit, caller-chosen `task_id` colliding means for their
                own retry semantics. When omitted, the original behavior is
                unchanged — a fresh UUID is minted every call, and a
                collision is not realistically possible (nothing else in
                this codebase currently calls `create_task` at all, let
                alone with an explicit `task_id` — `core.escalation.
                schedule_escalation` is the only caller today).

        Returns:
            str: Task ID. The created Cloud Task is named with this id
                (``{queue_path}/tasks/{task_id}``) so it can later be cancelled
                via :meth:`delete_task`. Equal to `task_id` when provided,
                otherwise a freshly minted UUID.

        Raises:
            ValueError: If delay is invalid or worker_url is not configured
            google.api_core.exceptions.AlreadyExists: A task named `task_id`
                already exists in this queue, OR `task_id` is within Cloud
                Tasks' de-duplication window for a name that was recently
                deleted or executed (per Google's docs: up to 24 hours, or 9
                days for a queue created via `queue.yaml`/`queue.xml` —
                https://cloud.google.com/tasks/docs/reference/rest/v2/projects.locations.queues.tasks/create).
                This method cannot distinguish "already scheduled" from
                "tombstoned, nothing is scheduled" — both raise the same
                error — so it no longer swallows this into a truthy return.
                A caller passing an explicit `task_id` (for idempotent
                creation) should treat this as "a task under this name
                already exists" and decide accordingly; it is NOT
                necessarily a failure.
            Exception: Any other Cloud Tasks error (e.g. permission,
                network) propagates unchanged.
        """
        # Validate delay
        MAX_DELAY = 2592000  # 30 days in seconds
        if delay < 0:
            raise ValueError("Delay must be non-negative")
        if delay > MAX_DELAY:
            raise ValueError(f"Delay cannot exceed {MAX_DELAY} seconds (30 days)")

        # Use the caller-provided task id for idempotent retries, or mint a
        # fresh one (existing behavior) when none is given.
        task_id = task_id or str(uuid.uuid4())

        # Calculate schedule time anchored to the namespace's local clock.
        # Mirrors core.timezone.namespace_timezone: missing/blank/unknown
        # timezone defaults to UTC instead of raising.
        tz_name = timezone_name or "UTC"
        try:
            ns_tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            logger.warning(
                f"create_task: unknown timezone '{tz_name}' for namespace "
                f"'{namespace_id}', defaulting to UTC."
            )
            ns_tz = ZoneInfo("UTC")
        schedule_time = datetime.now(ns_tz) + timedelta(seconds=delay)

        # Build task body (matches CloudTaskPayload schema)
        body = {
            "job_id": task_id,
            "job_type": job_type.value,
            "namespace_id": namespace_id,
        }

        # Add guest_id if provided
        if guest_id:
            body["guest_id"] = guest_id

        # Add event_id if provided
        if event_id is not None:
            body["event_id"] = event_id

        # Add payload if provided (matches the Pub/Sub path's "payload" key,
        # so `CloudJobIn.payload` is populated identically regardless of
        # transport).
        if payload is not None:
            body["payload"] = payload

        # Construct the task. Naming the task after our task id makes it
        # addressable for deletion later; a fresh UUID per call (the default
        # when `task_id` is omitted) avoids Cloud Tasks' name de-duplication
        # window across separate cycles (see the `task_id` arg docs above,
        # and `Raises` below, for what a collision means and why this
        # method no longer decides that on the caller's behalf).
        settings = get_settings()
        worker_url = f"{settings.worker_url}/cloud_job"
        task = tasks_v2.Task(
            name=f"{self.queue_path}/tasks/{task_id}",
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=worker_url,
                headers={"Content-Type": "application/json"},
                body=json.dumps(body).encode("utf-8"),
                oidc_token=tasks_v2.OidcToken(
                    service_account_email=f"{settings.google_project_id}@appspot.gserviceaccount.com",
                    audience=worker_url,
                ),
            ),
            schedule_time=schedule_time,
        )

        # Submit the task to the queue
        try:
            self.client.create_task(request={"parent": self.queue_path, "task": task})
            logger.info(
                f"Created task {task_id} (type={job_type.value}, namespace={namespace_id}, "
                f"delay={delay}s, schedule_time={schedule_time.isoformat()})"
            )
            return task_id

        except gcp_exceptions.AlreadyExists:
            # A task named `task_id` already exists in this queue, OR
            # `task_id` is within Cloud Tasks' de-duplication window for a
            # name that recently executed/was deleted (tombstoned) — the two
            # are indistinguishable from this exception alone (see `Raises`
            # in the docstring above, and the docs link there). Do NOT
            # collapse this into a truthy return here: only the caller knows
            # whether a caller-chosen `task_id` colliding means "already
            # scheduled" (safe to treat as success) for their use case.
            # Keep the info log — this is an expected, non-error outcome for
            # an idempotent-creation caller — but let the exception
            # propagate.
            logger.info(
                f"Task {task_id} already exists (type={job_type.value}, "
                f"namespace={namespace_id}) — propagating `AlreadyExists` "
                "for the caller to interpret."
            )
            raise

        except Exception as e:
            logger.error(
                f"Failed to create task {task_id} (type={job_type.value}, namespace={namespace_id}): {e}",
                exc_info=True,
            )
            raise

    def delete_task(self, task_id: str) -> bool:
        """
        Cancel a previously scheduled task by its id.

        Best-effort: a task that has already executed, been deleted, or never
        existed (``NotFound``) is treated as already-gone and returns ``False``
        rather than raising, so callers can cancel without first checking
        existence.

        Args:
            task_id: The id returned by :meth:`create_task`.

        Returns:
            bool: True if a pending task was deleted, False if it no longer
                exists.

        Raises:
            Exception: On non-NotFound Cloud Tasks errors (permission, network).
        """
        if not task_id:
            return False

        task_path = f"{self.queue_path}/tasks/{task_id}"
        try:
            self.client.delete_task(request={"name": task_path})
            logger.info(f"Deleted scheduled task {task_id}")
            return True
        except gcp_exceptions.NotFound:
            logger.info(
                f"Task {task_id} not found (already executed or deleted); nothing to cancel"
            )
            return False
        except Exception as e:
            logger.error(f"Failed to delete task {task_id}: {e}", exc_info=True)
            raise
