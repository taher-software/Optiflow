"""
Firestore client for creating collections and documents.

This module provides a FirestoreClient class that follows the same pattern
as other GCP service classes (CloudTask, PubSubInteraction).
"""

from google.cloud import firestore
from google.api_core import exceptions
from src.settings import settings
import logging

logger = logging.getLogger(__name__)


class FirestoreClient:
    """
    Firestore client for creating collections and documents.

    Follows the same pattern as CloudTask and PubSubInteraction classes.
    Collections are created implicitly when first document is added (standard Firestore behavior).

    Example:
        # Create a client
        client = FirestoreClient()

        # Create a document with auto-generated ID
        doc_id = client.create_document("users", {"name": "John", "email": "john@example.com"})
        print(f"Created document with ID: {doc_id}")
    """

    def __init__(self, project_id: str = None, database_id: str = "(optiflow)"):
        """
        Initialize Firestore client.

        Args:
            project_id: GCP project ID (auto-detected if None)
            database_id: Firestore database ID (default: "(optiflow)")

        Raises:
            exceptions.PermissionDenied: If credentials lack necessary permissions
            exceptions.Unauthenticated: If credentials are missing or invalid
            Exception: On other initialization errors
        """
        try:
            # Use provided project_id or auto-detect from settings
            self.project_id = project_id or settings.google_project_id
            self.database_id = database_id

            logger.info(
                f"Initializing Firestore client for project: {self.project_id}, "
                f"database: {self.database_id}"
            )

            # Initialize Firestore client (connects to existing database)
            self.client = firestore.Client(
                project=self.project_id, database=self.database_id
            )

            logger.info(
                f"Successfully initialized Firestore client for project {self.project_id}"
            )

        except exceptions.PermissionDenied as e:
            logger.error(
                f"Permission denied when initializing Firestore client. "
                f"Check service account permissions: {str(e)}",
                exc_info=True,
            )
            raise

        except exceptions.Unauthenticated as e:
            logger.error(
                f"Authentication failed when initializing Firestore client. "
                f"Check credentials configuration: {str(e)}",
                exc_info=True,
            )
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error initializing Firestore client: {str(e)}",
                exc_info=True,
            )
            raise

    def create_document(
        self, collection_name: str, data: dict, document_id: str = None
    ) -> str:
        """
        Create a new document in the specified collection.

        Collections are created implicitly if they don't exist (standard Firestore behavior).

        Args:
            collection_name: Name of the collection (e.g., "users", "orders")
            data: Dictionary containing document data
            document_id: Optional document ID. Auto-generated if not provided.

        Returns:
            str: Document ID (provided or auto-generated)

        Raises:
            ValueError: If collection_name or data is invalid
            exceptions.PermissionDenied: If credentials lack write permissions
            exceptions.DeadlineExceeded: If operation times out
            Exception: On other Firestore API errors

        Example:
            doc_id = client.create_document("users", {"name": "Alice", "age": 30})
            doc_id = client.create_document("users", {"name": "Bob"}, document_id="bob-123")
        """
        # Validate inputs
        if not collection_name or not isinstance(collection_name, str):
            raise ValueError("collection_name must be a non-empty string")

        if not isinstance(data, dict):
            raise ValueError("data must be a dictionary")

        if not data:
            raise ValueError("data dictionary cannot be empty")

        try:
            logger.info(f"Creating document in collection '{collection_name}'")

            collection_ref = self.client.collection(collection_name)

            if document_id:
                doc_ref = collection_ref.document(document_id)
                doc_ref.set(data)
            else:
                _, doc_ref = collection_ref.add(data)

            logger.info(
                f"Successfully created document with ID '{doc_ref.id}' "
                f"in collection '{collection_name}'"
            )

            return doc_ref.id

        except exceptions.PermissionDenied as e:
            logger.error(
                f"Permission denied when creating document in collection '{collection_name}'. "
                f"Check Firestore IAM permissions: {str(e)}",
                exc_info=True,
            )
            raise

        except exceptions.Unauthenticated as e:
            logger.error(
                f"Authentication failed when creating document in collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

        except exceptions.DeadlineExceeded as e:
            logger.error(
                f"Timeout when creating document in collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error creating document in collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

    def find_document(self, collection_name: str, params: dict) -> dict | None:
        """
        Find the first document in a collection that matches all provided parameters.

        Uses AND logic - the document must match ALL provided parameters.
        Returns the first matching document found, or None if no matches.

        Args:
            collection_name: Name of the collection to search (e.g., "users", "orders")
            params: Dictionary of field-value pairs to match (e.g., {"email": "john@example.com", "status": "active"})

        Returns:
            dict | None: Document data including 'id' field if found, None if no match

        Raises:
            ValueError: If collection_name or params is invalid
            exceptions.PermissionDenied: If credentials lack read permissions
            exceptions.DeadlineExceeded: If operation times out
            Exception: On other Firestore API errors

        Example:
            # Find user by email
            doc = client.find_document("users", {"email": "alice@example.com"})
            if doc:
                print(f"Found user: {doc['name']} with ID: {doc['id']}")
            else:
                print("No user found")

            # Find order by customer and status
            order = client.find_document("orders", {"customer_id": "123", "status": "pending"})
        """
        # Validate inputs
        if not collection_name or not isinstance(collection_name, str):
            raise ValueError("collection_name must be a non-empty string")

        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")

        if not params:
            raise ValueError("params dictionary cannot be empty")

        try:
            logger.info(
                f"Searching for document in collection '{collection_name}' with params: {params}"
            )

            # Get collection reference
            collection_ref = self.client.collection(collection_name)

            # Build query with AND logic (all params must match)
            query = collection_ref
            for field, value in params.items():
                query = query.where(field, "==", value)

            # Execute query and get first result
            docs = query.limit(1).stream()

            # Get the first document if it exists
            for doc in docs:
                doc_data = doc.to_dict()
                doc_data["id"] = doc.id  # Include document ID in result

                logger.info(
                    f"Found matching document with ID '{doc.id}' in collection '{collection_name}'"
                )
                return doc_data

            # No matching document found
            logger.info(
                f"No matching document found in collection '{collection_name}' for params: {params}"
            )
            return None

        except exceptions.PermissionDenied as e:
            logger.error(
                f"Permission denied when searching collection '{collection_name}'. "
                f"Check Firestore IAM permissions: {str(e)}",
                exc_info=True,
            )
            raise

        except exceptions.Unauthenticated as e:
            logger.error(
                f"Authentication failed when searching collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

        except exceptions.DeadlineExceeded as e:
            logger.error(
                f"Timeout when searching collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error searching collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

    def get_document(self, collection_name: str, document_id: str) -> dict | None:
        """
        Retrieve a document by its ID from a specific collection.

        Args:
            collection_name: Name of the collection (e.g., "users", "orders")
            document_id: Firestore document ID to retrieve

        Returns:
            dict | None: Document data including 'id' field if found, None if document doesn't exist

        Raises:
            ValueError: If collection_name or document_id is invalid
            exceptions.PermissionDenied: If credentials lack read permissions
            exceptions.DeadlineExceeded: If operation times out
            Exception: On other Firestore API errors

        Example:
            # Get document by ID
            doc = client.get_document("users", "abc123xyz")
            if doc:
                print(f"User name: {doc['name']}")
                print(f"User email: {doc['email']}")
            else:
                print("Document not found")
        """
        # Validate inputs
        if not collection_name or not isinstance(collection_name, str):
            raise ValueError("collection_name must be a non-empty string")

        if not document_id or not isinstance(document_id, str):
            raise ValueError("document_id must be a non-empty string")

        try:
            logger.info(
                f"Retrieving document '{document_id}' from collection '{collection_name}'"
            )

            # Get document reference
            doc_ref = self.client.collection(collection_name).document(document_id)

            # Get document snapshot
            doc = doc_ref.get()

            # Check if document exists
            if not doc.exists:
                logger.info(
                    f"Document '{document_id}' not found in collection '{collection_name}'"
                )
                return None

            # Convert document to dictionary and include ID
            doc_data = doc.to_dict()
            doc_data["id"] = doc.id

            logger.info(
                f"Successfully retrieved document '{document_id}' from collection '{collection_name}'"
            )

            return doc_data

        except exceptions.PermissionDenied as e:
            logger.error(
                f"Permission denied when retrieving document '{document_id}' from collection '{collection_name}'. "
                f"Check Firestore IAM permissions: {str(e)}",
                exc_info=True,
            )
            raise

        except exceptions.Unauthenticated as e:
            logger.error(
                f"Authentication failed when retrieving document '{document_id}' from collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

        except exceptions.DeadlineExceeded as e:
            logger.error(
                f"Timeout when retrieving document '{document_id}' from collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error retrieving document '{document_id}' from collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

    def update_document(
        self, collection_name: str, document_id: str, data: dict
    ) -> bool:
        """
        Merge ``data`` into an existing document.

        Uses Firestore's ``set(..., merge=True)`` so only the supplied fields are
        overwritten and any fields not present in ``data`` are left untouched.

        Args:
            collection_name: Name of the collection (e.g., "users", "orders")
            document_id: Firestore document ID to update
            data: Dictionary of field-value pairs to merge into the document

        Returns:
            bool: True if the document existed and was updated, False if no
                document with ``document_id`` exists (nothing is written).

        Raises:
            ValueError: If collection_name, document_id or data is invalid
            exceptions.PermissionDenied: If credentials lack write permissions
            exceptions.DeadlineExceeded: If operation times out
            Exception: On other Firestore API errors

        Example:
            updated = client.update_document("users", "abc123", {"name": "Alice"})
            if updated:
                print("Document updated")
            else:
                print("Document not found")
        """
        # Validate inputs
        if not collection_name or not isinstance(collection_name, str):
            raise ValueError("collection_name must be a non-empty string")

        if not document_id or not isinstance(document_id, str):
            raise ValueError("document_id must be a non-empty string")

        if not isinstance(data, dict):
            raise ValueError("data must be a dictionary")

        if not data:
            raise ValueError("data dictionary cannot be empty")

        try:
            logger.info(
                f"Updating document '{document_id}' in collection '{collection_name}'"
            )

            doc_ref = self.client.collection(collection_name).document(document_id)

            # Only update an existing document — match the get/delete contract
            # that returns False rather than implicitly creating a new doc.
            if not doc_ref.get().exists:
                logger.info(
                    f"Document '{document_id}' not found in collection "
                    f"'{collection_name}', nothing to update"
                )
                return False

            # merge=True so callers can patch a subset of fields without wiping
            # the rest of the document.
            doc_ref.set(data, merge=True)

            logger.info(
                f"Successfully updated document '{document_id}' in collection "
                f"'{collection_name}'"
            )

            return True

        except exceptions.PermissionDenied as e:
            logger.error(
                f"Permission denied when updating document '{document_id}' in collection '{collection_name}'. "
                f"Check Firestore IAM permissions: {str(e)}",
                exc_info=True,
            )
            raise

        except exceptions.Unauthenticated as e:
            logger.error(
                f"Authentication failed when updating document '{document_id}' in collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

        except exceptions.DeadlineExceeded as e:
            logger.error(
                f"Timeout when updating document '{document_id}' in collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error updating document '{document_id}' in collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

    def delete_document(self, collection_name: str, document_id: str) -> bool:
        """
        Delete a document by its ID from a specific collection.

        Args:
            collection_name: Name of the collection (e.g., "users", "orders")
            document_id: Firestore document ID to delete

        Returns:
            bool: True if document was deleted, False if document didn't exist

        Raises:
            ValueError: If collection_name or document_id is invalid
            exceptions.PermissionDenied: If credentials lack delete permissions
            exceptions.DeadlineExceeded: If operation times out
            Exception: On other Firestore API errors

        Example:
            # Delete document by ID
            deleted = client.delete_document("users", "abc123xyz")
            if deleted:
                print("Document deleted successfully")
            else:
                print("Document not found")
        """
        # Validate inputs
        if not collection_name or not isinstance(collection_name, str):
            raise ValueError("collection_name must be a non-empty string")

        if not document_id or not isinstance(document_id, str):
            raise ValueError("document_id must be a non-empty string")

        try:
            logger.info(
                f"Deleting document '{document_id}' from collection '{collection_name}'"
            )

            # Get document reference
            doc_ref = self.client.collection(collection_name).document(document_id)

            # Check if document exists before deleting
            doc = doc_ref.get()
            if not doc.exists:
                logger.info(
                    f"Document '{document_id}' not found in collection '{collection_name}', nothing to delete"
                )
                return False

            # Delete the document
            doc_ref.delete()

            logger.info(
                f"Successfully deleted document '{document_id}' from collection '{collection_name}'"
            )

            return True

        except exceptions.PermissionDenied as e:
            logger.error(
                f"Permission denied when deleting document '{document_id}' from collection '{collection_name}'. "
                f"Check Firestore IAM permissions: {str(e)}",
                exc_info=True,
            )
            raise

        except exceptions.Unauthenticated as e:
            logger.error(
                f"Authentication failed when deleting document '{document_id}' from collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

        except exceptions.DeadlineExceeded as e:
            logger.error(
                f"Timeout when deleting document '{document_id}' from collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error deleting document '{document_id}' from collection '{collection_name}': {str(e)}",
                exc_info=True,
            )
            raise
