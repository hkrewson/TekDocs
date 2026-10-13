import base64
import io
import os

import pytest
from cryptography.exceptions import InvalidTag

import tekdocs.recovery_archive as recovery_archive
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


def test_encrypt_cli_accepts_a_private_input_file(tmp_path, monkeypatch):
    key = os.urandom(32)
    key_file = tmp_path / "recovery.key"
    key_file.write_bytes(base64.urlsafe_b64encode(key))
    key_file.chmod(0o600)
    source = tmp_path / "repositories.tar"
    source.write_bytes(b"repository recovery archive")
    encrypted = io.BytesIO()
    monkeypatch.setattr(recovery_archive.sys, "stdout", type("Output", (), {"buffer": encrypted})())
    monkeypatch.setattr(
        recovery_archive.sys,
        "argv",
        [
            "recovery_archive",
            "encrypt",
            "--key-file",
            str(key_file),
            "--label",
            "repositories",
            "--input",
            str(source),
        ],
    )

    assert recovery_archive.main() == 0
    artifact = tmp_path / "repositories.tdr"
    artifact.write_bytes(encrypted.getvalue())
    restored = tmp_path / "restored.tar"
    decrypt_file(artifact, restored, key=key, label="repositories")
    assert restored.read_bytes() == source.read_bytes()


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


def test_key_contract_rejects_links_without_masking_the_reason(tmp_path):
    target = tmp_path / "recovery-target.key"
    target.write_bytes(base64.urlsafe_b64encode(os.urandom(32)))
    target.chmod(0o600)
    link = tmp_path / "recovery.key"
    link.symlink_to(target)

    with pytest.raises(RecoveryArchiveError, match="regular file, not a link"):
        load_key(link)


def test_archive_encryption_and_decryption_enforce_plaintext_security_bound(tmp_path, monkeypatch):
    key = os.urandom(32)
    monkeypatch.setattr(recovery_archive, "MAX_PLAINTEXT_BYTES", 8)
    with pytest.raises(RecoveryArchiveError, match="16 GiB"):
        encrypt_stream(io.BytesIO(b"123456789"), io.BytesIO(), key=key, label="database")

    encrypted = io.BytesIO()
    monkeypatch.setattr(recovery_archive, "MAX_PLAINTEXT_BYTES", 64)
    encrypt_stream(io.BytesIO(b"123456789"), encrypted, key=key, label="database")
    artifact = tmp_path / "oversized.tdr"
    artifact.write_bytes(encrypted.getvalue())
    monkeypatch.setattr(recovery_archive, "MAX_PLAINTEXT_BYTES", 8)
    with pytest.raises(RecoveryArchiveError, match="16 GiB"):
        decrypt_file(artifact, tmp_path / "restored.dump", key=key, label="database")


@pytest.mark.parametrize("failure", ("wrong_key", "wrong_label", "nonce", "ciphertext", "tag", "truncated", "magic"))
@pytest.mark.parametrize("existing_destination", (False, True))
def test_rejected_archive_preserves_destination_and_removes_plaintext(tmp_path, failure, existing_destination):
    key = os.urandom(32)
    encrypted = io.BytesIO()
    encrypt_stream(io.BytesIO(b"private recovery fixture"), encrypted, key=key, label="database")
    data = bytearray(encrypted.getvalue())
    label = "database"
    expected_error = InvalidTag
    if failure == "wrong_key":
        key = os.urandom(32)
    elif failure == "wrong_label":
        label = "media"
    elif failure == "nonce":
        data[len(recovery_archive.MAGIC)] ^= 1
    elif failure == "ciphertext":
        data[len(recovery_archive.MAGIC) + recovery_archive.NONCE_SIZE] ^= 1
    elif failure == "tag":
        data[-1] ^= 1
    elif failure == "truncated":
        del data[-1]
    else:
        data[0] ^= 1
        expected_error = RecoveryArchiveError
    artifact = tmp_path / "database.tdr"
    artifact.write_bytes(data)
    destination_directory = tmp_path / "output"
    destination_directory.mkdir()
    destination = destination_directory / "database.dump"
    if existing_destination:
        destination.write_bytes(b"existing destination")

    with pytest.raises(expected_error):
        decrypt_file(artifact, destination, key=key, label=label)

    assert list(destination_directory.iterdir()) == ([destination] if existing_destination else [])
    if existing_destination:
        assert destination.read_bytes() == b"existing destination"


@pytest.mark.parametrize("failure", (None, "changed_manifest", "wrong_key", "wrong_mac"))
def test_manifest_cli_authentication_rejects_changed_inputs(tmp_path, monkeypatch, capsys, failure):
    key = os.urandom(32)
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(b'{"format":"tekdocs-recovery-v2","artifacts":{}}\n')
    expected_mac = manifest_mac(manifest, key=key)
    if failure == "changed_manifest":
        manifest.write_bytes(b'{"format":"tekdocs-recovery-v2","artifacts":{"changed":true}}\n')
    elif failure == "wrong_key":
        key = os.urandom(32)
    elif failure == "wrong_mac":
        expected_mac = "0" * 64
    key_file = tmp_path / "recovery.key"
    key_file.write_bytes(base64.urlsafe_b64encode(key))
    key_file.chmod(0o600)
    monkeypatch.setattr(
        recovery_archive.sys,
        "argv",
        ["recovery_archive", "verify-manifest", "--key-file", str(key_file),
         "--input", str(manifest), "--expected-mac", expected_mac],
    )

    assert recovery_archive.main() == (2 if failure else 0)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ("The recovery manifest authentication failed.\n" if failure else "")
