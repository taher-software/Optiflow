import secrets

from fastapi import HTTPException, status

from src.app.core.firestore import USERS_COLLECTION
from src.app.gcp.firestore import FirestoreClient

_MAX_CODE_ATTEMPTS = 100


def generate_security_code(client: FirestoreClient, namespace_id: str) -> str:
    """Allocate a unique 4-digit security code within the namespace.

    Shared by `user.services` (initial allocation on user creation) and
    `auth.services` (rotation on mobile device pairing) so both stay in sync
    with a single implementation.
    """
    for _ in range(_MAX_CODE_ATTEMPTS):
        code = f"{secrets.randbelow(10000):04d}"
        clash = client.find_document(
            USERS_COLLECTION,
            {"namespace_id": namespace_id, "security_code": code},
        )
        if not clash:
            return code
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not allocate a unique security code. Please retry.",
    )
