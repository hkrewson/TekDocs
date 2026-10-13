from __future__ import annotations

import io
import tarfile

import pytest

from tekdocs.recovery_preflight import (
    OPTIONAL_SECRETS,
    REQUIRED_SECRETS,
    validate_media_archive,
    validate_secret_archive,
)


@pytest.mark.parametrize("invalid", (
    None, "symlink", "hardlink", "fifo", "device", "absolute", "parent", "inner_parent",
    "duplicate", "alias", "file_parent", "late_file_parent", "truncated", "backslash",
))
def test_media_archive_preflight(tmp_path, invalid):
    path = tmp_path / "media.tar"
    with tarfile.open(path, "w") as archive:
        root = tarfile.TarInfo(".")
        root.type = tarfile.DIRTYPE
        archive.addfile(root)
        names = ["./documents", "./documents/synthetic.txt", "./empty.txt"]
        if invalid == "late_file_parent":
            names = ["./documents/synthetic.txt", "./documents"]
        if invalid in {"duplicate", "alias"}:
            names.append("./documents/synthetic.txt" if invalid == "duplicate" else "documents/synthetic.txt")
        for name in names:
            member = tarfile.TarInfo(name)
            body = b"synthetic-media-fixture" if name != "./empty.txt" else b""
            if name == "./documents" and invalid not in {"file_parent", "late_file_parent"}:
                member.type = tarfile.DIRTYPE
            if name == "./documents/synthetic.txt":
                if invalid in {"symlink", "hardlink", "fifo", "device"}:
                    member.type = {"symlink": tarfile.SYMTYPE, "hardlink": tarfile.LNKTYPE,
                                   "fifo": tarfile.FIFOTYPE, "device": tarfile.CHRTYPE}[invalid]
                    member.linkname = "/outside-fixture"
                member.name = {
                    "absolute": "/outside-fixture", "parent": "../outside-fixture",
                    "inner_parent": "documents/../outside-fixture", "backslash": "documents\\outside-fixture",
                }.get(invalid, member.name)
            member.size = len(body) if member.isfile() else 0
            archive.addfile(member, io.BytesIO(body) if member.isfile() else None)
    if invalid == "truncated":
        path.write_bytes(path.read_bytes()[:1540])
    if invalid:
        with pytest.raises(ValueError) as caught:
            validate_media_archive(path)
        assert "synthetic-media-fixture" not in str(caught.value)
        assert str(path) not in str(caught.value)
    else:
        validate_media_archive(path)
    assert list(tmp_path.iterdir()) == [path]


def test_empty_media_directory_is_supported(tmp_path):
    path = tmp_path / "media.tar"
    with tarfile.open(path, "w") as archive:
        member = tarfile.TarInfo(".")
        member.type = tarfile.DIRTYPE
        archive.addfile(member)
    validate_media_archive(path)


@pytest.mark.parametrize(
    "invalid",
    (None, "symlink", "hardlink", "directory", "fifo", "duplicate", "missing", "path", "empty", "large", "truncated"),
)
def test_secret_archive_preflight(tmp_path, invalid):
    path = tmp_path / "secrets.tar"
    names = sorted(REQUIRED_SECRETS | OPTIONAL_SECRETS)
    if invalid == "missing":
        names.remove("django_secret_key")
    if invalid == "duplicate":
        names.append("django_secret_key")
    with tarfile.open(path, "w") as archive:
        for name in names:
            member = tarfile.TarInfo(name)
            body = b"synthetic-secret-fixture"
            if name == "django_secret_key":
                if invalid in {"symlink", "hardlink", "directory", "fifo"}:
                    member.type = {"symlink": tarfile.SYMTYPE, "hardlink": tarfile.LNKTYPE,
                                   "directory": tarfile.DIRTYPE, "fifo": tarfile.FIFOTYPE}[invalid]
                    member.linkname = "/outside-fixture"
                elif invalid == "path":
                    member.name = "../django_secret_key"
                elif invalid == "empty":
                    body = b""
                elif invalid == "large":
                    body = b"x" * 4097
            member.size = len(body) if member.isfile() else 0
            archive.addfile(member, io.BytesIO(body) if member.isfile() else None)
    if invalid == "truncated":
        path.write_bytes(path.read_bytes()[:520])

    if invalid:
        with pytest.raises(ValueError) as caught:
            validate_secret_archive(path)
        assert "synthetic-secret-fixture" not in str(caught.value)
        assert str(path) not in str(caught.value)
    else:
        validate_secret_archive(path)
    assert list(tmp_path.iterdir()) == [path]
