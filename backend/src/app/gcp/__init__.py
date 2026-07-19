"""
Google Cloud Platform integrations.

This module provides access to GCP services used by the application,
including Cloud Storage, Pub/Sub, Cloud Tasks, and Firestore.
"""

from functools import lru_cache
from typing import TYPE_CHECKING

from .firestore import FirestoreClient

if TYPE_CHECKING:
    from .cloud_tasks import CloudTask
    from .pub_sub import PubSubInteraction


@lru_cache
def get_pubsub_publisher(topic_name: str = "optiflow_jobs") -> "PubSubInteraction":
    """
    Get or create the singleton Pub/Sub publisher instance.

    `PubSubInteraction` is imported lazily (only when this is actually
    called) so importing `src.app.gcp` never requires the Pub/Sub SDK /
    credentials to be present — mirrors the Firestore client's lazy wiring.

    Returns:
        PubSubInteraction: Singleton publisher for job queuing
    """
    from .pub_sub import PubSubInteraction

    return PubSubInteraction(topic_name=topic_name)


@lru_cache
def get_cloud_task_manager(queue_name: str = "optiflow-tasks") -> "CloudTask":
    """
    Get or create the singleton Cloud Task manager instance.

    `CloudTask` is imported lazily (only when this is actually called) so
    importing `src.app.gcp` never requires the Cloud Tasks SDK / credentials
    to be present — mirrors the Firestore client's lazy wiring.

    Args:
        queue_name: Name of the Cloud Tasks queue (default: "optiflow_tasks")

    Returns:
        CloudTask: Singleton Cloud Task manager for delayed job scheduling
    """
    from .cloud_tasks import CloudTask

    return CloudTask(queue_name=queue_name)


@lru_cache
def get_firestore_client() -> FirestoreClient:
    """
    Get or create the singleton Firestore client instance.

    The underlying GCP connection is established lazily on first use
    (see `FirestoreClient`), so calling this at import time is safe.

    Returns:
        FirestoreClient: Singleton Firestore client for document operations
    """
    return FirestoreClient()
