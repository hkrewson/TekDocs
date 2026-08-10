from __future__ import annotations

import os
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from tekdocs.settings.secret_files import MAX_SECRET_BYTES, read_secret


def write_secret(root: Path, name: str, value: bytes = b"safe-runtime-value\n", mode: int = 0o600) -> Path:
    path = root / name
    path.write_bytes(value)
    path.chmod(mode)
    return path


def test_direct_value_and_file_value_are_mutually_exclusive(tmp_path):
    path = write_secret(tmp_path, "django")
    with pytest.raises(ImproperlyConfigured, match="not both") as caught:
        read_secret(
            "DJANGO_SECRET_KEY",
            environment={"DJANGO_SECRET_KEY": "direct-value", "DJANGO_SECRET_KEY_FILE": str(path)},
            secret_root=tmp_path,
        )
    assert "direct-value" not in str(caught.value)
    assert str(path) not in str(caught.value)


def test_file_value_is_read_with_one_terminal_newline_removed(tmp_path):
    path = write_secret(tmp_path, "master-key", b"printable-secret-value\n")
    assert (
        read_secret(
            "TEKDOCS_MASTER_KEY",
            environment={"TEKDOCS_MASTER_KEY_FILE": str(path)},
            secret_root=tmp_path,
        )
        == "printable-secret-value"
    )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (b"", "1-4096 bytes"),
        (b"x" * (MAX_SECRET_BYTES + 1), "1-4096 bytes"),
        (b"two\nlines", "one non-empty printable value"),
        (b" outer-whitespace ", "one non-empty printable value"),
        (b"\xff\xfe", "readable UTF-8"),
    ],
)
def test_empty_oversized_multiline_whitespace_and_non_utf8_values_fail_without_disclosure(tmp_path, value, message):
    path = write_secret(tmp_path, "invalid", value)
    with pytest.raises(ImproperlyConfigured, match=message) as caught:
        read_secret("DJANGO_SECRET_KEY", environment={"DJANGO_SECRET_KEY_FILE": str(path)}, secret_root=tmp_path)
    assert str(path) not in str(caught.value)
    printable_value = value[:32].decode("utf-8", errors="ignore")
    if printable_value:
        assert printable_value not in str(caught.value)


def test_relative_outside_and_world_readable_sources_fail_without_path_disclosure(tmp_path):
    outside = write_secret(tmp_path.parent, "outside-secret")
    world_readable = write_secret(tmp_path, "world-readable", mode=0o644)
    cases = [
        "relative-secret",
        str(outside),
        str(world_readable),
    ]
    for configured_path in cases:
        with pytest.raises(ImproperlyConfigured) as caught:
            read_secret(
                "DJANGO_SECRET_KEY",
                environment={"DJANGO_SECRET_KEY_FILE": configured_path},
                secret_root=tmp_path,
            )
        assert configured_path not in str(caught.value)
    outside.unlink()


def test_symlink_cannot_escape_the_approved_secret_root(tmp_path):
    outside = write_secret(tmp_path.parent, "outside-symlink-target")
    link = tmp_path / "escaped"
    os.symlink(outside, link)
    with pytest.raises(ImproperlyConfigured, match="outside the approved secret root") as caught:
        read_secret("DJANGO_SECRET_KEY", environment={"DJANGO_SECRET_KEY_FILE": str(link)}, secret_root=tmp_path)
    assert str(outside) not in str(caught.value)
    assert str(link) not in str(caught.value)
    outside.unlink()
