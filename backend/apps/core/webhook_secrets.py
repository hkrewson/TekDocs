from __future__ import annotations

import json
from binascii import Error as Base64Error
from uuid import UUID

from cryptography.exceptions import InvalidTag
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .crypto import Envelope, EnvelopeCipher

PREFIX = "tdwebhook1:"


def _cipher() -> EnvelopeCipher:
    configured = settings.TEKDOCS_MASTER_KEY
    if not configured:
        raise ImproperlyConfigured("TEKDOCS_MASTER_KEY is required for webhook signing keys")
    try:
        return EnvelopeCipher.from_base64(configured)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured("TEKDOCS_MASTER_KEY must be a URL-safe base64 encoded 256-bit key") from exc


def _associated_data(*, tenant_id: UUID, endpoint_id: UUID, generation: int) -> bytes:
    return f"tekdocs:webhook-secret:v1:{tenant_id}:{endpoint_id}:{generation}".encode()


def encrypt_webhook_secret(*, secret: bytes, tenant_id: UUID, endpoint_id: UUID, generation: int) -> dict[str, str]:
    envelope = _cipher().encrypt(
        secret,
        _associated_data(tenant_id=tenant_id, endpoint_id=endpoint_id, generation=generation),
    )
    return {"provider": PREFIX, **envelope.as_dict()}


def decrypt_webhook_secret(
    *, envelope_payload: dict[str, str], tenant_id: UUID, endpoint_id: UUID, generation: int
) -> bytes:
    if envelope_payload.get("provider") != PREFIX:
        raise ImproperlyConfigured("Webhook signing key is not encrypted with the TekDocs provider")
    try:
        payload = {key: value for key, value in envelope_payload.items() if key != "provider"}
        # Round-trip through JSON rejects non-serializable or non-string database corruption consistently.
        normalized = json.loads(json.dumps(payload))
        return _cipher().decrypt(
            Envelope.from_dict(normalized),
            _associated_data(tenant_id=tenant_id, endpoint_id=endpoint_id, generation=generation),
        )
    except (Base64Error, InvalidTag, KeyError, TypeError, ValueError) as exc:
        raise ImproperlyConfigured("Webhook signing key could not be decrypted") from exc
