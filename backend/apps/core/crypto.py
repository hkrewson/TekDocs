from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


@dataclass(frozen=True)
class Envelope:
    algorithm: str
    ciphertext: str
    data_nonce: str
    wrapped_key: str
    wrap_nonce: str

    def as_dict(self) -> dict[str, str]:
        return {
            "algorithm": self.algorithm,
            "ciphertext": self.ciphertext,
            "data_nonce": self.data_nonce,
            "wrapped_key": self.wrapped_key,
            "wrap_nonce": self.wrap_nonce,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, str]) -> Envelope:
        return cls(**payload)


class EnvelopeCipher:
    """AES-256-GCM envelope-encryption feasibility primitive for the SecretProvider boundary."""

    ALGORITHM = "AES-256-GCM+ENVELOPE-v1"

    def __init__(self, wrapping_key: bytes):
        if len(wrapping_key) != 32:
            raise ValueError("The wrapping key must contain exactly 32 bytes")
        self._wrapping_key = wrapping_key

    @classmethod
    def from_base64(cls, wrapping_key: str) -> EnvelopeCipher:
        return cls(_decode(wrapping_key))

    def encrypt(self, plaintext: bytes, associated_data: bytes) -> Envelope:
        data_key = os.urandom(32)
        data_nonce = os.urandom(12)
        wrap_nonce = os.urandom(12)
        ciphertext = AESGCM(data_key).encrypt(data_nonce, plaintext, associated_data)
        wrapped_key = AESGCM(self._wrapping_key).encrypt(wrap_nonce, data_key, b"tekdocs:dek:" + associated_data)
        return Envelope(
            algorithm=self.ALGORITHM,
            ciphertext=_encode(ciphertext),
            data_nonce=_encode(data_nonce),
            wrapped_key=_encode(wrapped_key),
            wrap_nonce=_encode(wrap_nonce),
        )

    def decrypt(self, envelope: Envelope, associated_data: bytes) -> bytes:
        if envelope.algorithm != self.ALGORITHM:
            raise ValueError("Unsupported envelope algorithm")
        data_key = AESGCM(self._wrapping_key).decrypt(
            _decode(envelope.wrap_nonce), _decode(envelope.wrapped_key), b"tekdocs:dek:" + associated_data
        )
        return AESGCM(data_key).decrypt(_decode(envelope.data_nonce), _decode(envelope.ciphertext), associated_data)

    def rewrap(self, envelope: Envelope, associated_data: bytes, new_cipher: EnvelopeCipher) -> Envelope:
        if envelope.algorithm != self.ALGORITHM:
            raise ValueError("Unsupported envelope algorithm")
        data_key = AESGCM(self._wrapping_key).decrypt(
            _decode(envelope.wrap_nonce), _decode(envelope.wrapped_key), b"tekdocs:dek:" + associated_data
        )
        wrap_nonce = os.urandom(12)
        wrapped_key = AESGCM(new_cipher._wrapping_key).encrypt(wrap_nonce, data_key, b"tekdocs:dek:" + associated_data)
        return Envelope(
            algorithm=envelope.algorithm,
            ciphertext=envelope.ciphertext,
            data_nonce=envelope.data_nonce,
            wrapped_key=_encode(wrapped_key),
            wrap_nonce=_encode(wrap_nonce),
        )
