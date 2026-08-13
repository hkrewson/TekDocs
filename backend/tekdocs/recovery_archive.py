from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"TEKDOCS1"
NONCE_SIZE = 12
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024


class RecoveryArchiveError(ValueError):
    pass


def load_key(path: Path) -> bytes:
    try:
        key_stat = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(key_stat.st_mode):
            raise RecoveryArchiveError("The recovery key must be a regular file, not a link.")
        if stat.S_IMODE(key_stat.st_mode) & 0o077:
            raise RecoveryArchiveError("The recovery key must not be accessible to group or other users.")
        encoded = path.read_bytes().strip()
        key = base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4))
    except (OSError, binascii.Error, ValueError) as exc:
        raise RecoveryArchiveError("The recovery key is unavailable or malformed.") from exc
    if len(key) != 32:
        raise RecoveryArchiveError("The recovery key must decode to exactly 32 bytes.")
    return key


def _aad(label: str) -> bytes:
    if not label or len(label.encode("utf-8")) > 128 or any(ord(character) < 33 for character in label):
        raise RecoveryArchiveError("The artifact label is invalid.")
    return f"tekdocs-recovery-v1:{label}".encode()


def encrypt_stream(source: BinaryIO, destination: BinaryIO, *, key: bytes, label: str) -> None:
    nonce = os.urandom(NONCE_SIZE)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(_aad(label))
    destination.write(MAGIC + nonce)
    while chunk := source.read(CHUNK_SIZE):
        destination.write(encryptor.update(chunk))
    destination.write(encryptor.finalize())
    destination.write(encryptor.tag)


def decrypt_file(source_path: Path, destination_path: Path, *, key: bytes, label: str) -> None:
    size = source_path.stat().st_size
    minimum_size = len(MAGIC) + NONCE_SIZE + TAG_SIZE
    if size < minimum_size:
        raise RecoveryArchiveError("The encrypted artifact is truncated.")
    with source_path.open("rb") as source:
        if source.read(len(MAGIC)) != MAGIC:
            raise RecoveryArchiveError("The encrypted artifact format is unsupported.")
        nonce = source.read(NONCE_SIZE)
        source.seek(-TAG_SIZE, os.SEEK_END)
        tag = source.read(TAG_SIZE)
        ciphertext_size = size - minimum_size
        source.seek(len(MAGIC) + NONCE_SIZE)
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(_aad(label))
        destination_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary_fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination_path.name}.", dir=destination_path.parent
        )
        try:
            with os.fdopen(temporary_fd, "wb") as destination:
                remaining = ciphertext_size
                while remaining:
                    chunk = source.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise RecoveryArchiveError("The encrypted artifact is truncated.")
                    destination.write(decryptor.update(chunk))
                    remaining -= len(chunk)
                destination.write(decryptor.finalize())
                destination.flush()
                os.fsync(destination.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, destination_path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


def manifest_mac(path: Path, *, key: bytes) -> str:
    mac_key = hmac.digest(key, b"tekdocs-recovery-v1:manifest-key", "sha256")
    return hmac.new(mac_key, path.read_bytes(), hashlib.sha256).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="TekDocs authenticated recovery archive helper")
    parser.add_argument("operation", choices=("encrypt", "decrypt", "manifest-mac", "verify-manifest"))
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--label")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-mac")
    arguments = parser.parse_args()
    try:
        key = load_key(arguments.key_file)
        if arguments.operation == "encrypt":
            if not arguments.label:
                raise RecoveryArchiveError("Encryption requires an artifact label.")
            encrypt_stream(sys.stdin.buffer, sys.stdout.buffer, key=key, label=arguments.label)
        elif arguments.operation == "decrypt":
            if not arguments.label or arguments.input is None or arguments.output is None:
                raise RecoveryArchiveError("Decryption requires a label, input, and output.")
            decrypt_file(arguments.input, arguments.output, key=key, label=arguments.label)
        elif arguments.operation == "manifest-mac":
            if arguments.input is None:
                raise RecoveryArchiveError("Manifest authentication requires an input.")
            print(manifest_mac(arguments.input, key=key))
        else:
            if arguments.input is None or not arguments.expected_mac:
                raise RecoveryArchiveError("Manifest verification requires an input and expected MAC.")
            actual = manifest_mac(arguments.input, key=key)
            if not hmac.compare_digest(actual, arguments.expected_mac):
                raise RecoveryArchiveError("The recovery manifest authentication failed.")
    except (InvalidTag, RecoveryArchiveError, OSError, ValueError) as exc:
        if isinstance(exc, InvalidTag):
            exc = RecoveryArchiveError("The encrypted artifact authentication failed.")
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
