from functools import lru_cache
import logging
from google.cloud import pubsub_v1
from src.settings import settings
from google.api_core import exceptions as gcp_exceptions
import json
import uuid
from datetime import datetime, timezone
from src.app.globals.enum import JobType
from typing import Optional, Dict, Any


logger = logging.getLogger(__name__)


class PubSubInteraction:

    def __init__(self, topic_name="bodor_jobs"):
        self.publisher_client = pubsub_v1.PublisherClient()
        self.subscriber_client = pubsub_v1.SubscriberClient()
        self.topic_path = self._create_topic(topic_name)

    def _create_topic(self, topic_name):
        """
        Initialize Pub/Sub topic for async job processing.

        Creates the topic only if it doesn't exist. Properly distinguishes between
        different failure reasons (NotFound vs PermissionDenied, NetworkError, etc.)
        """

        if not settings.google_project_id:
            logger.warning(
                "Google Project ID is not set. Skipping Pub/Sub topic initialization."
            )
            raise ValueError("Google Project ID is not set.")

        TOPIC_PATH = self.publisher_client.topic_path(
            settings.google_project_id, topic_name
        )

        try:
            # Try to get the topic to check if it exists
            self.publisher_client.get_topic(request={"topic": TOPIC_PATH})
            logger.info(f"Pub/Sub topic {TOPIC_PATH} already exists.")
            return TOPIC_PATH

        except gcp_exceptions.NotFound:
            # Topic doesn't exist - this is the ONLY case where we should create it
            try:
                self.publisher_client.create_topic(request={"name": TOPIC_PATH})
                logger.info(f"Successfully created Pub/Sub topic: {TOPIC_PATH}")
            except gcp_exceptions.AlreadyExists:
                # Race condition: topic was created between our check and create attempt
                logger.info(
                    f"Pub/Sub topic {TOPIC_PATH} already exists (created concurrently)."
                )
            except gcp_exceptions.PermissionDenied as e:
                logger.error(f"Permission denied when creating topic {TOPIC_PATH}: {e}")
                raise
            except Exception as e:
                logger.error(f"Failed to create Pub/Sub topic {TOPIC_PATH}: {e}")
                raise

        except gcp_exceptions.PermissionDenied as e:
            # Permission error when checking - don't try to create, just raise
            logger.error(f"Permission denied when accessing topic {TOPIC_PATH}: {e}")
            raise

        except gcp_exceptions.Unauthenticated as e:
            # Authentication error - credentials issue
            logger.error(f"Authentication failed when accessing Pub/Sub: {e}")
            raise

        except gcp_exceptions.DeadlineExceeded as e:
            # Timeout error - network or service issue
            logger.error(f"Timeout when accessing topic {TOPIC_PATH}: {e}")
            raise

        except Exception as e:
            # Any other unexpected error - log and raise
            logger.error(f"Unexpected error when accessing topic {TOPIC_PATH}: {e}")
            raise

    def publish_job(
        self,
        job_type: JobType,
        namespace_id: int,
        payload: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
    ) -> str:
        """
        Publish a job to the Pub/Sub topic.

        Args:
            job_type: Type of job to execute (from JobType enum)
            namespace_id: Namespace ID to process
            payload: Optional additional data for the job
            job_id: Optional deterministic job ID; a UUID is generated when omitted

        Returns:
            job_id: Unique identifier for this job
        """
        # Use provided job_id or generate a unique one
        job_id = job_id or str(uuid.uuid4())

        # Construct message with standardized schema
        message_data = {
            "job_id": job_id,
            "job_type": job_type.value,  # Convert enum to string
            "namespace_id": namespace_id,
            "attempt": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {},
        }

        # Publish message to topic
        future = self.publisher_client.publish(
            self.topic_path, json.dumps(message_data).encode("utf-8")
        )

        # Wait for publish to complete and get message ID
        message_id = future.result()

        logger.info(
            f"Published job {job_id} (type={job_type.value}, namespace={namespace_id}, message_id={message_id})"
        )

        return job_id

    def publish_message(self, payload: dict):
        """Deprecated: Use publish_job() instead"""

        self.publisher_client.publish(
            self.topic_path, json.dumps(payload).encode("utf-8")
        )
        print(f"Published job: {payload}")

    def subscribe_to_topic(self):
        pass  #
