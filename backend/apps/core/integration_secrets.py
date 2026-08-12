from __future__ import annotations

import json
from binascii import Error as Base64Error
from uuid import UUID

from cryptography.exceptions import InvalidTag
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .crypto import Envelope, EnvelopeCipher

PREFIX = "tdintegration1:"


def _cipher() -> EnvelopeCipher:
    configured = settings.TEKDOCS_MASTER_KEY
    if not configured:
        raise ImproperlyConfigured("TEKDOCS_MASTER_KEY is required for integration credentials")
    try:
        return EnvelopeCipher.from_base64(configured)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured("TEKDOCS_MASTER_KEY must be a URL-safe base64 encoded 256-bit key") from exc


def _aad(*, tenant_id: UUID, connection_id: UUID, generation: int) -> bytes:
    return f"tekdocs:integration-secret:v1:{tenant_id}:{connection_id}:{generation}".encode()


def encrypt_integration_secret(
    *, secret: bytes, tenant_id: UUID, connection_id: UUID, generation: int
) -> dict[str, str]:
    envelope = _cipher().encrypt(secret, _aad(tenant_id=tenant_id, connection_id=connection_id, generation=generation))
    return {"provider": PREFIX, **envelope.as_dict()}


def decrypt_integration_secret(
    *, envelope_payload: dict[str, str], tenant_id: UUID, connection_id: UUID, generation: int
) -> bytes:
    if envelope_payload.get("provider") != PREFIX:
        raise ImproperlyConfigured("Integration credential is not encrypted with the TekDocs provider")
    try:
        payload = {key: value for key, value in envelope_payload.items() if key != "provider"}
        normalized = json.loads(json.dumps(payload))
        return _cipher().decrypt(
            Envelope.from_dict(normalized),
            _aad(tenant_id=tenant_id, connection_id=connection_id, generation=generation),
        )
    except (Base64Error, InvalidTag, KeyError, TypeError, ValueError) as exc:
        raise ImproperlyConfigured("Integration credential could not be decrypted") from exc
