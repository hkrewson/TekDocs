from __future__ import annotations

import io
import re
import socket
import struct
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol, cast

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage
from django.utils.module_loading import import_string

MAX_ARCHIVE_ENTRIES = 100
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_RATIO = 100
MAX_STORED_ATTACHMENT_BYTES = 10 * 1024 * 1024

_ACTIVE_PDF_TOKENS = (b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile", b"/RichMedia")
_EXECUTABLE_MAGICS = (
    b"MZ",
    b"\x7fELF",
    b"\xca\xfe\xba\xbe",
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
)
_EICAR_MARKER = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
_TEXT_CONTROL = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_NESTED_ARCHIVE_SUFFIXES = {".7z", ".bz2", ".gz", ".rar", ".tar", ".tgz", ".xz", ".zip"}


class AttachmentSecurityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ScanResult:
    engine: str


class AttachmentScanner(Protocol):
    def scan(self, *, filename: str, media_type: str, content: bytes) -> ScanResult: ...


class AttachmentStorageProvider(Protocol):
    provider_id: str

    def quarantine(self, *, intake_id: str, content: bytes) -> str: ...

    def promote(self, *, quarantine_key: str, clean_key: str, expected_checksum: str) -> str: ...

    def read(self, *, key: str, maximum_bytes: int) -> bytes: ...

    def delete(self, *, key: str) -> None: ...


class StrictAttachmentScanner:
    """Conservative built-in scanner and structural validator.

    This boundary is replaceable with an external malware engine. The built-in
    scanner deliberately rejects active PDF features, executable/polyglot
    signatures, unsafe archives, malformed images, and the standard AV test
    marker; it does not claim signature coverage equivalent to ClamAV.
    """

    engine = "tekdocs-strict-content/1"

    def scan(self, *, filename: str, media_type: str, content: bytes) -> ScanResult:
        if _EICAR_MARKER in content:
            raise AttachmentSecurityError("The attachment was rejected by content scanning.")
        if content.startswith(_EXECUTABLE_MAGICS):
            raise AttachmentSecurityError("Executable content is not accepted as an attachment.")
        if media_type.startswith("text/") or media_type in {"application/json", "application/yaml"}:
            if _TEXT_CONTROL.search(content):
                raise AttachmentSecurityError("Text attachments contain unsupported control bytes.")
        elif media_type == "application/pdf":
            if not content.rstrip().endswith(b"%%EOF") or any(token in content for token in _ACTIVE_PDF_TOKENS):
                raise AttachmentSecurityError("The PDF is malformed or contains unsupported active features.")
        elif media_type == "application/zip":
            self._validate_zip(content)
        elif media_type == "image/png":
            if not content.endswith(b"IEND\xaeB`\x82"):
                raise AttachmentSecurityError("The PNG is incomplete or contains trailing content.")
        elif media_type == "image/jpeg":
            if not content.endswith(b"\xff\xd9"):
                raise AttachmentSecurityError("The JPEG is incomplete or contains trailing content.")
        elif media_type == "image/gif":
            if not content.endswith(b";"):
                raise AttachmentSecurityError("The GIF is incomplete or contains trailing content.")
        elif media_type == "image/webp":
            declared_size = int.from_bytes(content[4:8], "little") + 8
            if declared_size != len(content):
                raise AttachmentSecurityError("The WebP size does not match its container header.")
        return ScanResult(engine=self.engine)

    def _validate_zip(self, content: bytes) -> None:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                entries = archive.infolist()
                if not entries or len(entries) > MAX_ARCHIVE_ENTRIES:
                    raise AttachmentSecurityError("ZIP attachments must contain 1 to 100 entries.")
                total_uncompressed = 0
                for entry in entries:
                    path = PurePosixPath(entry.filename.replace("\\", "/"))
                    if path.is_absolute() or ".." in path.parts or any(ord(char) < 32 for char in entry.filename):
                        raise AttachmentSecurityError("ZIP attachments contain an unsafe member path.")
                    if entry.flag_bits & 0x1:
                        raise AttachmentSecurityError("Encrypted ZIP attachments are not accepted.")
                    if ((entry.external_attr >> 16) & 0o170000) == 0o120000:
                        raise AttachmentSecurityError("ZIP attachments may not contain symbolic links.")
                    if not entry.is_dir() and path.suffix.lower() in _NESTED_ARCHIVE_SUFFIXES:
                        raise AttachmentSecurityError("Nested archives are not accepted.")
                    total_uncompressed += entry.file_size
                    if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                        raise AttachmentSecurityError("The expanded ZIP size exceeds the safety limit.")
                    if entry.file_size > max(1, entry.compress_size) * MAX_ARCHIVE_RATIO:
                        raise AttachmentSecurityError("The ZIP compression ratio exceeds the safety limit.")
        except (zipfile.BadZipFile, UnicodeError) as exc:
            raise AttachmentSecurityError("The ZIP attachment is malformed.") from exc


class ClamAVAttachmentScanner:
    """Stream structurally validated content to a separately operated clamd service."""

    engine = "clamav/instream"

    def scan(self, *, filename: str, media_type: str, content: bytes) -> ScanResult:
        StrictAttachmentScanner().scan(filename=filename, media_type=media_type, content=content)
        host = str(getattr(settings, "TEKDOCS_CLAMAV_HOST", "")).strip()
        port = int(getattr(settings, "TEKDOCS_CLAMAV_PORT", 3310))
        timeout = float(getattr(settings, "TEKDOCS_CLAMAV_TIMEOUT", 10))
        if not host or not 1 <= port <= 65535 or not 1 <= timeout <= 60:
            raise AttachmentSecurityError("The ClamAV scanner configuration is invalid.")
        try:
            with socket.create_connection((host, port), timeout=timeout) as connection:
                connection.settimeout(timeout)
                connection.sendall(b"zINSTREAM\0")
                for offset in range(0, len(content), 64 * 1024):
                    chunk = content[offset : offset + 64 * 1024]
                    connection.sendall(struct.pack("!I", len(chunk)) + chunk)
                connection.sendall(struct.pack("!I", 0))
                response = bytearray()
                while len(response) <= 4096:
                    chunk = connection.recv(4097 - len(response))
                    if not chunk:
                        break
                    response.extend(chunk)
                    if b"\0" in chunk or b"\n" in chunk:
                        break
        except (OSError, TimeoutError, ValueError) as exc:
            raise AttachmentSecurityError("ClamAV scanning is unavailable; the upload was rejected.") from exc
        if len(response) > 4096 or not bytes(response).split(b"\0", 1)[0].rstrip(b"\r\n").endswith(b": OK"):
            raise AttachmentSecurityError("The attachment was rejected by antivirus scanning.")
        return ScanResult(engine=self.engine)


class DjangoAttachmentStorageProvider:
    provider_id = "django-default"

    def __init__(self, storage: Storage | None = None) -> None:
        self.storage = storage or default_storage

    def quarantine(self, *, intake_id: str, content: bytes) -> str:
        return self.storage.save(f"attachment-quarantine/{intake_id}", ContentFile(content))

    def promote(self, *, quarantine_key: str, clean_key: str, expected_checksum: str) -> str:
        from hashlib import sha256

        content = self.read(key=quarantine_key, maximum_bytes=MAX_STORED_ATTACHMENT_BYTES)
        if sha256(content).hexdigest() != expected_checksum:
            raise AttachmentSecurityError("Quarantined attachment integrity verification failed.")
        stored_key = self.storage.save(clean_key, ContentFile(content))
        self.delete(key=quarantine_key)
        return stored_key

    def read(self, *, key: str, maximum_bytes: int) -> bytes:
        with self.storage.open(key, "rb") as handle:
            content = handle.read(maximum_bytes + 1)
        if len(content) > maximum_bytes:
            raise AttachmentSecurityError("Stored attachment exceeds its permitted size.")
        return cast(bytes, content)

    def delete(self, *, key: str) -> None:
        if key:
            self.storage.delete(key)


def attachment_scanner() -> AttachmentScanner:
    scanner_class = import_string(
        getattr(settings, "TEKDOCS_ATTACHMENT_SCANNER", "apps.core.attachment_security.StrictAttachmentScanner")
    )
    scanner = scanner_class()
    if not callable(getattr(scanner, "scan", None)):
        raise AttachmentSecurityError("The configured attachment scanner is invalid.")
    return cast(AttachmentScanner, scanner)


def attachment_storage_provider() -> AttachmentStorageProvider:
    provider_class = import_string(
        getattr(
            settings,
            "TEKDOCS_ATTACHMENT_STORAGE_PROVIDER",
            "apps.core.attachment_security.DjangoAttachmentStorageProvider",
        )
    )
    provider = provider_class()
    for method in ("quarantine", "promote", "read", "delete"):
        if not callable(getattr(provider, method, None)):
            raise AttachmentSecurityError("The configured attachment storage provider is invalid.")
    return cast(AttachmentStorageProvider, provider)
