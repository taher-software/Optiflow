import secrets

from fastapi import HTTPException, status

from src.app.core.firestore import USERS_COLLECTION
from src.app.gcp.firestore import FirestoreClient

_MAX_CODE_ATTEMPTS = 100

# The 32-symbol unambiguous base32 alphabet: digits plus uppercase letters,
# excluding I, L, O, U (confusable with 1/0 on a phone screen). A code stays
# 4 characters long -- it is typed on a phone on a factory floor -- but is
# drawn from a much wider codomain than the legacy 4 decimal digits.
_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODE_LENGTH = 4


def generate_security_code(client: FirestoreClient, namespace_id: str) -> str:
    """Allocate a globally-unique 4-character security code.

    Shared by `user.services` (initial allocation on user creation) and
    `auth.services` (rotation on mobile device pairing) so both stay in sync
    with a single implementation.

    The code is drawn from `_CODE_ALPHABET` using `secrets` (cryptographically
    secure, unlike `random`). Uniqueness is checked globally (no
    `namespace_id` filter): the pairing lookup in `auth.services` searches
    `security_code` across every tenant, so a per-namespace guarantee alone
    would not be sufficient. `namespace_id` is kept as a parameter for
    call-site compatibility even though it is no longer used in the lookup.
    """
    for _ in range(_MAX_CODE_ATTEMPTS):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        clash = client.find_document(USERS_COLLECTION, {"security_code": code})
        if not clash:
            return code
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not allocate a unique security code. Please retry.",
    )
