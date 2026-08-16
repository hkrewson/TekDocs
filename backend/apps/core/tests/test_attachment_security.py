from __future__ import annotations

import io
import secrets
import stat
import struct
import zipfile

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.attachment_security import (
    MAX_STORED_ATTACHMENT_BYTES,
    AttachmentSecurityError,
    ClamAVAttachmentScanner,
    DjangoAttachmentStorageProvider,
    StrictAttachmentScanner,
)
from apps.core.document_attachments import validate_attachment_upload
from apps.core.models import DocumentAttachment, InstallationState
from apps.core.tests.test_documents import organization


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Attachment MSP",
        owner_email="attachment-owner@example.invalid",
        owner_display_name="Attachment Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    client = Client()
    client.force_login(installation.owner)
    return client


def _zip(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def _encrypted_zip() -> bytes:
    content = bytearray(_zip({"private.txt": b"encrypted marker"}))
    local_header = content.find(b"PK\x03\x04")
    central_header = content.find(b"PK\x01\x02")
    for offset in (local_header + 6, central_header + 8):
        flags = int.from_bytes(content[offset : offset + 2], "little") | 0x1
        content[offset : offset + 2] = flags.to_bytes(2, "little")
    return bytes(content)


def _symlink_zip() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        entry = zipfile.ZipInfo("link")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(entry, "target")
    return output.getvalue()


def _crc_corrupt_zip() -> bytes:
    content = bytearray(_zip({"evidence.txt": b"retained evidence"}))
    central_header = content.find(b"PK\x01\x02")
    assert central_header >= 0
    declared_crc = struct.unpack_from("<I", content, central_header + 16)[0]
    struct.pack_into("<I", content, central_header + 16, declared_crc ^ 0xFFFFFFFF)
    return bytes(content)


def _duplicate_path_zip() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("Evidence.txt", b"first")
        archive.writestr("evidence.txt", b"second")
    return output.getvalue()


def test_strict_scanner_rejects_active_polyglot_and_unsafe_archive_content():
    scanner = StrictAttachmentScanner()
    assert scanner.scan(filename="notes.txt", media_type="text/plain", content=b"safe notes\n").engine

    rejected = (
        ("test.txt", "text/plain", b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"),
        ("renamed.txt", "text/plain", b"MZnot really text"),
        ("active.pdf", "application/pdf", b"%PDF-1.7\n/JavaScript\n%%EOF"),
        ("traversal.zip", "application/zip", _zip({"../outside.txt": b"no"})),
        ("encrypted.zip", "application/zip", _encrypted_zip()),
        ("symlink.zip", "application/zip", _symlink_zip()),
        ("nested.zip", "application/zip", _zip({"payload.tar": b"nested"})),
        ("bomb.zip", "application/zip", _zip({"large.txt": b"A" * 100_000})),
        ("many.zip", "application/zip", _zip({f"{index}.txt": b"x" for index in range(101)})),
        ("crc.zip", "application/zip", _crc_corrupt_zip()),
        ("duplicate.zip", "application/zip", _duplicate_path_zip()),
        ("controls.txt", "text/plain", b"value\x07"),
        ("trailing.png", "image/png", b"\x89PNG\r\n\x1a\nIEND\xaeB`\x82trailing"),
    )
    for filename, media_type, content in rejected:
        with pytest.raises(AttachmentSecurityError):
            scanner.scan(filename=filename, media_type=media_type, content=content)


class FakeClamAVConnection:
    def __init__(self, response: bytes):
        self.response = response
        self.sent = bytearray()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def settimeout(self, _timeout):
        return None

    def sendall(self, content: bytes):
        self.sent.extend(content)

    def recv(self, _size: int) -> bytes:
        return self.response


@override_settings(TEKDOCS_CLAMAV_HOST="clamav.internal", TEKDOCS_CLAMAV_PORT=3310, TEKDOCS_CLAMAV_TIMEOUT=4)
def test_clamav_provider_streams_content_and_fails_closed(monkeypatch):
    clean = FakeClamAVConnection(b"stream: OK\0")
    monkeypatch.setattr(
        "apps.core.attachment_security.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("10.20.30.40", 3310))],
    )
    destinations = []
    monkeypatch.setattr(
        "apps.core.attachment_security.socket.create_connection",
        lambda destination, **_kwargs: destinations.append(destination) or clean,
    )
    result = ClamAVAttachmentScanner().scan(filename="notes.txt", media_type="text/plain", content=b"safe")
    assert result.engine == "clamav/instream"
    assert destinations == [("10.20.30.40", 3310)]
    assert clean.sent.startswith(b"zINSTREAM\0")

    with pytest.raises(AttachmentSecurityError):
        ClamAVAttachmentScanner().scan(
            filename="active.pdf", media_type="application/pdf", content=b"%PDF-1.7\n/JavaScript\n%%EOF"
        )

    infected = FakeClamAVConnection(b"stream: Eicar-Test-Signature FOUND\0")
    monkeypatch.setattr(
        "apps.core.attachment_security.socket.create_connection", lambda *_args, **_kwargs: infected
    )
    with pytest.raises(AttachmentSecurityError, match="antivirus"):
        ClamAVAttachmentScanner().scan(filename="notes.txt", media_type="text/plain", content=b"unsafe")

    monkeypatch.setattr(
        "apps.core.attachment_security.socket.create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
    )
    with pytest.raises(AttachmentSecurityError, match="unavailable"):
        ClamAVAttachmentScanner().scan(filename="notes.txt", media_type="text/plain", content=b"safe")


@override_settings(TEKDOCS_CLAMAV_HOST="scanner.example", TEKDOCS_CLAMAV_PORT=3310)
def test_clamav_provider_rejects_public_and_mixed_resolution(monkeypatch):
    for addresses in (("8.8.8.8",), ("192.0.2.10",), ("10.20.30.40", "1.1.1.1")):
        monkeypatch.setattr(
            "apps.core.attachment_security.socket.getaddrinfo",
            lambda *_args, addresses=addresses, **_kwargs: [
                (2, 1, 6, "", (address, 3310)) for address in addresses
            ],
        )
        with pytest.raises(AttachmentSecurityError, match="private addresses"):
            ClamAVAttachmentScanner().scan(filename="notes.txt", media_type="text/plain", content=b"safe")


def test_storage_provider_quarantines_promotes_and_verifies_bytes(tmp_path):
    from hashlib import sha256

    provider = DjangoAttachmentStorageProvider(FileSystemStorage(location=tmp_path))
    content = b"managed attachment"
    quarantined = provider.quarantine(intake_id="intake", content=content)
    assert quarantined.startswith("attachment-quarantine/")
    promoted = provider.promote(
        quarantine_key=quarantined,
        clean_key="document-attachments/tenant/document/attachment",
        expected_checksum=sha256(content).hexdigest(),
    )
    assert provider.read(key=promoted, maximum_bytes=1024) == content
    assert not (tmp_path / quarantined).exists()


def test_attachment_intake_reads_only_the_bounded_limit():
    oversized = SimpleUploadedFile("oversized.txt", b"A" * (MAX_STORED_ATTACHMENT_BYTES + 1))
    with pytest.raises(ValidationError, match="10 MiB"):
        validate_attachment_upload(oversized)


class RejectingScanner:
    def scan(self, **_kwargs):  # type: ignore[no-untyped-def]
        raise AttachmentSecurityError("The attachment was rejected by content scanning.")


@pytest.mark.django_db
def test_rejected_upload_never_enters_managed_storage(owner_client, installation, tmp_path):
    client = organization(installation.tenant, "Scanner client")
    document = owner_client.post(
        reverse("organization-document-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"title": "Scanner boundary", "markdown": ""},
        content_type="application/json",
    ).json()
    with override_settings(
        MEDIA_ROOT=tmp_path,
        TEKDOCS_ATTACHMENT_SCANNER="apps.core.tests.test_attachment_security.RejectingScanner",
    ):
        response = owner_client.post(
            reverse(
                "organization-document-attachment-list-create",
                kwargs={"organization_entity_id": client.entity_id, "document_entity_id": document["id"]},
            ),
            {"file": SimpleUploadedFile("notes.txt", b"not promoted")},
        )
    assert response.status_code == 400
    assert DocumentAttachment.objects.count() == 0
    assert not any(path.is_file() for path in tmp_path.rglob("*"))
