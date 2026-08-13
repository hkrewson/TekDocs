import base64
import io
import os

import pytest
from cryptography.exceptions import InvalidTag

from tekdocs.recovery_archive import RecoveryArchiveError, decrypt_file, encrypt_stream, load_key, manifest_mac


def test_authenticated_archive_round_trip_and_tamper_rejection(tmp_path):
    key = os.urandom(32)
    encrypted = io.BytesIO()
    encrypt_stream(io.BytesIO(b"retained database and media"), encrypted, key=key, label="database")
    artifact = tmp_path / "database.tdr"
    artifact.write_bytes(encrypted.getvalue())
    restored = tmp_path / "database.dump"

    decrypt_file(artifact, restored, key=key, label="database")
    assert restored.read_bytes() == b"retained database and media"

    tampered = bytearray(artifact.read_bytes())
    tampered[-20] ^= 1
    artifact.write_bytes(tampered)
    restored.unlink()
    with pytest.raises(InvalidTag):
        decrypt_file(artifact, restored, key=key, label="database")
    assert not restored.exists()


def test_key_and_manifest_contract(tmp_path):
    key = os.urandom(32)
    key_file = tmp_path / "recovery.key"
    key_file.write_bytes(base64.urlsafe_b64encode(key))
    key_file.chmod(0o600)
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"format":"tekdocs-recovery-v1"}\n')

    assert load_key(key_file) == key
    assert manifest_mac(manifest, key=key) == manifest_mac(manifest, key=key)
    with pytest.raises(RecoveryArchiveError):
        load_key(tmp_path / "missing.key")

    key_file.chmod(0o640)
    with pytest.raises(RecoveryArchiveError, match="group or other"):
        load_key(key_file)
