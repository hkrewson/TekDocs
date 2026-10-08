import hashlib
import io
import json
import uuid
import zipfile

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.repository_source_validation import RepositorySourceValidationError, verify_repository_source_snapshot


def _archive(*, change: str = "") -> bytes:
    current_id, historical_id = (
        uuid.UUID("11111111-1111-4111-8111-111111111111"),
        uuid.UUID("22222222-2222-4222-8222-222222222222"),
    )
    commit = "a" * 40
    old_commit = "b" * 40
    current_frontmatter = f"---\nschema: tekdocs.content/v1\nid: {current_id}\n"
    current = (current_frontmatter + "kind: document\ntitle: Guide\n---\nCurrent guide.\n").encode()
    historical = (
        f"---\nschema: tekdocs.content/v1\nid: {historical_id}\nkind: fragment\n"
        "title: Original\n---\nOriginal fragment.\n"
    ).encode()
    historical_path = f"pinned/{old_commit}/fragments/original.md"
    manifest = {
        "format": "tekdocs-repository-source-snapshot/v3",
        "workspace_id": "33333333-3333-4333-8333-333333333333",
        "accepted_commit": commit,
        "object_format": "sha1",
        "scope": "current-files-and-reachable-markdown-dependencies",
        "exclusions": ["attachment_bytes", "database_records", "git_history"],
        "files": [
            {
                "path": "repository/docs/guide.md",
                "content_id": str(current_id),
                "kind": "document",
                "sha256": hashlib.sha256(current).hexdigest(),
            }
        ],
        "historical_files": [
            {
                "path": historical_path,
                "source_path": "fragments/original.md",
                "commit": old_commit,
                "content_id": str(historical_id),
                "kind": "fragment",
                "sha256": hashlib.sha256(historical).hexdigest(),
                "roles": ["derived_from", "template_source"],
            }
        ],
    }
    if change == "wrong_identity":
        manifest["files"][0]["content_id"] = str(uuid.uuid4())
    if change == "unsafe_path":
        manifest["files"][0]["path"] = "repository/../docs/guide.md"
    if change == "bad_roles":
        manifest["historical_files"][0]["roles"] = ["template_source", "derived_from"]
    if change == "unsupported_format":
        manifest["format"] = "tekdocs-repository-source-snapshot/v2"
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        files = {
            "README.md": b"Source snapshot, not a backup.\n",
            "tekdocs-source.json": (json.dumps(manifest) + "\n").encode(),
            "repository/docs/guide.md": current + (b"changed" if change == "wrong_hash" else b""),
            historical_path: historical,
        }
        if change == "unlisted":
            files["extra.txt"] = b"extra"
        if change == "missing":
            del files[historical_path]
        for path, content in files.items():
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o120777 if change == "symlink" and path == historical_path else 0o100644) << 16
            info.create_system = 3
            archive.writestr(info, content)
        if change == "duplicate":
            archive.writestr(info, historical)
    return target.getvalue()


def test_offline_source_snapshot_check_accepts_exact_manifest_and_cli(tmp_path, capsys):
    content = _archive()
    manifest = verify_repository_source_snapshot(content)
    assert len(manifest["files"]) == 1
    assert len(manifest["historical_files"]) == 1
    path = tmp_path / "source.zip"
    path.write_bytes(content)
    call_command("verify_repository_source_snapshot", path)
    assert "internally consistent" in capsys.readouterr().out


@pytest.mark.parametrize(
    "change",
    [
        "wrong_hash",
        "wrong_identity",
        "unsafe_path",
        "bad_roles",
        "unlisted",
        "missing",
        "duplicate",
        "symlink",
        "unsupported_format",
    ],
)
def test_offline_source_snapshot_check_rejects_tampering(change):
    with pytest.raises(RepositorySourceValidationError):
        verify_repository_source_snapshot(_archive(change=change))


def test_offline_source_snapshot_command_refuses_missing_file(tmp_path):
    with pytest.raises(CommandError, match="cannot be read"):
        call_command("verify_repository_source_snapshot", tmp_path / "missing.zip")
