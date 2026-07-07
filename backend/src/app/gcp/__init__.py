"""
Google Cloud Platform integrations.

This module provides access to GCP services used by the application,
including Cloud Storage, Pub/Sub, Cloud Tasks, and Firestore.
"""

from functools import lru_cache
from .pub_sub import PubSubInteraction
from .cloud_tasks import CloudTask
from .firestore import FirestoreClient


@lru_cache
def get_pubsub_publisher(topic_name: str = "optiflow_jobs") -> PubSubInteraction:
    """
    Get or create the singleton Pub/Sub publisher instance.

    Returns:
        PubSubInteraction: Singleton publisher for job queuing
    """
    return PubSubInteraction(topic_name=topic_name)


@lru_cache
def get_cloud_task_manager(queue_name: str = "optiflow-tasks") -> CloudTask:
    """
    Get or create the singleton Cloud Task manager instance.

    Args:
        queue_name: Name of the Cloud Tasks queue (default: "optiflow_tasks")

    Returns:
        CloudTask: Singleton Cloud Task manager for delayed job scheduling
    """
    return CloudTask(queue_name=queue_name)


@lru_cache
def get_firestore_client(database_id: str = "(optiflow)") -> FirestoreClient:
    """
    Get or create the singleton Firestore client instance.

    Args:
        database_id: Firestore database ID (default: "(optiflow)")

    Returns:
        FirestoreClient: Singleton Firestore client for document operations
    """
    return FirestoreClient(database_id=database_id)


# Singleton instances for easy importing
pubsub_publisher = get_pubsub_publisher()
cloud_task_manager = get_cloud_task_manager()
firestore_client = get_firestore_client()
