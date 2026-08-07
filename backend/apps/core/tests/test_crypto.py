import os

import pytest
from cryptography.exceptions import InvalidTag

from apps.core.crypto import EnvelopeCipher


def test_envelope_cipher_round_trip_and_rewrap():
    first = EnvelopeCipher(os.urandom(32))
    second = EnvelopeCipher(os.urandom(32))
    context = b"tenant:00000000-0000-4000-8000-000000000001:secret:one:version:1"
    envelope = first.encrypt(b"example secret", context)

    assert first.decrypt(envelope, context) == b"example secret"
    rotated = first.rewrap(envelope, context, second)
    assert rotated.ciphertext == envelope.ciphertext
    assert second.decrypt(rotated, context) == b"example secret"


def test_envelope_cipher_authenticates_context():
    cipher = EnvelopeCipher(os.urandom(32))
    envelope = cipher.encrypt(b"example secret", b"tenant:one")

    with pytest.raises(InvalidTag):
        cipher.decrypt(envelope, b"tenant:two")


def test_envelope_cipher_requires_256_bit_wrapping_key():
    with pytest.raises(ValueError, match="exactly 32 bytes"):
        EnvelopeCipher(b"too-short")
