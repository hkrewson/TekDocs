import json
from binascii import Error as Base64Error

from cryptography.exceptions import InvalidTag
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.core.crypto import Envelope, EnvelopeCipher

PREFIX = "tdmfa1:"
ASSOCIATED_DATA = b"tekdocs:mfa-authenticator:v1"


def _cipher() -> EnvelopeCipher:
    configured = settings.TEKDOCS_MASTER_KEY
    if not configured:
        raise ImproperlyConfigured("TEKDOCS_MASTER_KEY is required for MFA storage")
    try:
        return EnvelopeCipher.from_base64(configured)
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured("TEKDOCS_MASTER_KEY must be a URL-safe base64 encoded 256-bit key") from exc


def encrypt_mfa_value(value: str) -> str:
    envelope = _cipher().encrypt(value.encode("utf-8"), ASSOCIATED_DATA)
    return PREFIX + json.dumps(envelope.as_dict(), separators=(",", ":"), sort_keys=True)


def decrypt_mfa_value(value: str) -> str:
    if not value.startswith(PREFIX):
        raise ImproperlyConfigured("MFA secret storage is not encrypted with the TekDocs provider")
    try:
        payload = json.loads(value.removeprefix(PREFIX))
        return _cipher().decrypt(Envelope.from_dict(payload), ASSOCIATED_DATA).decode("utf-8")
    except (Base64Error, InvalidTag, KeyError, TypeError, UnicodeDecodeError, ValueError) as exc:
        raise ImproperlyConfigured("MFA secret storage could not be decrypted") from exc
