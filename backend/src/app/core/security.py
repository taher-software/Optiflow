import secrets
import string

from itsdangerous import URLSafeTimedSerializer

from .config import get_settings

# bcrypt operates on the first 72 bytes of the password.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    import bcrypt

    pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    import bcrypt

    pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(pw, hashed.encode("utf-8"))


def generate_password(length: int = 12) -> str:
    """Generate a random, reasonably strong initial password."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="email-confirm")


def make_confirmation_token(data: dict[str, str]) -> str:
    return _serializer().dumps(data)


def read_confirmation_token(token: str) -> dict[str, str]:
    """Decode a confirmation token. Raises itsdangerous.SignatureExpired /
    BadSignature on expiry / tampering."""
    max_age = get_settings().confirm_token_max_age_seconds
    return _serializer().loads(token, max_age=max_age)


def _access_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="auth-access")


def make_access_token(data: dict[str, str]) -> str:
    """Create a signed access token (bearer) carrying the given claims."""
    return _access_serializer().dumps(data)


def read_access_token(token: str) -> dict[str, str]:
    """Decode an access token. Raises itsdangerous.SignatureExpired /
    BadSignature on expiry / tampering."""
    max_age = get_settings().access_token_max_age_seconds
    return _access_serializer().loads(token, max_age=max_age)
