from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from urllib3.exceptions import ReadTimeoutError

from apps.core import document_sources
from apps.core.document_source_models import DocumentRemoteSource

pytest_plugins = ("apps.core.tests.test_document_migration_publications",)


@pytest.mark.django_db(transaction=True)
def test_remote_document_read_failure_closes_response_and_retains_only_safe_error(monkeypatch, published_context):
    response = SimpleNamespace(
        status=200, headers={"Content-Type": "text/plain"},
        read=Mock(side_effect=ReadTimeoutError(None, "/fixture", "synthetic private upstream detail")),
        close=Mock(),
    )
    pool = SimpleNamespace(urlopen=Mock(return_value=response), close=Mock())
    monkeypatch.setattr(document_sources, "resolve_public_https_target", lambda *args, **kwargs: SimpleNamespace(
        path="/fixture", hostname="example.invalid",
    ))
    monkeypatch.setattr(document_sources, "pinned_https_pool", lambda *args, **kwargs: pool)
    installation, _workspace, document, _publication = published_context
    source = DocumentRemoteSource.objects.create(
        tenant=installation.tenant, organization=None, document=document, created_by=installation.owner,
        url="https://example.invalid/fixture", check_interval_minutes=60,
    )
    observation = document_sources.fetch_remote_document(source)
    source.refresh_from_db()
    assert source.observations.get().id == observation.id
    assert source.last_checked_at is not None
    assert observation.state == "failed"
    assert observation.error_code == "remote_connection_failed"
    assert observation.canonical_markdown == ""
    response.close.assert_called_once_with()
    pool.close.assert_called_once_with()
