from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.cloud import firestore

NAMESPACE_COLLECTION = "namespace"
USERS_COLLECTION = "Users"


@lru_cache
def get_db() -> "firestore.Client":
    """Return a cached Firestore client using the default service-account
    credentials (Application Default Credentials). Imported lazily so the app
    module imports without the Firestore SDK / credentials being present."""
    from google.cloud import firestore

    return firestore.Client()
