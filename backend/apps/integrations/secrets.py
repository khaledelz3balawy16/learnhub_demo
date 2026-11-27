"""HR API keys at rest: Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from
settings.HR_INTEGRATION["CREDENTIAL_KEY"] (env CREDENTIAL_ENCRYPTION_KEY).

The plain key is only ever held in memory for one request to Breathe. It is never
returned by the API, logged or written to the audit trail.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from core.errors import ServiceError


def is_configured() -> bool:
    return len(settings.HR_INTEGRATION.get("CREDENTIAL_KEY") or "") >= 32


def _fernet() -> Fernet:
    if not is_configured():
        raise ServiceError(
            "not_configured",
            "HR connections are not set up on this server yet. Ask the platform team.",
            status=503,
        )
    raw = settings.HR_INTEGRATION["CREDENTIAL_KEY"].encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw).digest()))


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        raise ServiceError("no_key", "This connection has no API key. Reconnect it.", status=409)
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # the server key changed since the company connected: they must enter it again
        raise ServiceError(
            "key_unreadable", "The saved API key can't be read. Replace the key.", status=409
        ) from None
