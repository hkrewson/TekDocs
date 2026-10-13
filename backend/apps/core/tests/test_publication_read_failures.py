"""A failed retained-file read must not look like a valid empty attachment."""

import hashlib
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from apps.core import repository_publication_views as views


@pytest.mark.parametrize("failure", (None, OSError, ValueError, TypeError))
def test_empty_evidence_attachment_requires_successful_storage_read(failure):
    artifact_id, source_id = uuid4(), uuid4()
    storage = Mock()
    if failure is None:
        storage.open.return_value = BytesIO(b"")
    else:
        storage.open.side_effect = failure("synthetic private storage diagnostic")
    artifact = SimpleNamespace(
        id=artifact_id, size=0, source_attachment_id=source_id,
        source_attachment=SimpleNamespace(entity_id=uuid4()),
        file=SimpleNamespace(storage=storage, name="fixture-empty-file"),
    )
    evidence = SimpleNamespace(
        workspace=object(), tenant=object(), organization=object(),
        manifest={"attachments": [{
            "id": str(artifact_id), "source_id": str(source_id), "size": 0,
            "checksum": hashlib.sha256(b"").hexdigest(),
        }]},
    )
    with (
        patch.object(views, "require_permission"),
        patch.object(views, "_evidence", return_value=evidence),
        patch.object(views, "get_object_or_404", return_value=artifact),
        patch.object(views, "verify_repository_publication_evidence", return_value={"valid": True}),
    ):
        # Simulate storage becoming unavailable after signed-evidence verification.
        # Authorization, signatures and database behavior have separate suites.
        response = views._review_attachment(
            SimpleNamespace(user=object()), SimpleNamespace(organization=evidence.organization),
            uuid4(), artifact_id,
        )
    assert response.status_code == (200 if failure is None else 409)
    assert response.content == (
        b"" if failure is None else b"Retained publication attachment failed verification"
    )
    assert response["Cache-Control"] == "private, no-store"
    assert response["X-Content-Type-Options"] == "nosniff"
    storage.open.assert_called_once_with("fixture-empty-file", "rb")
