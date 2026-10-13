from types import SimpleNamespace
from unittest.mock import Mock

from urllib3.exceptions import ReadTimeoutError

from apps.core import document_sources


def test_remote_document_read_failure_closes_response_and_retains_only_safe_error(monkeypatch):
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
    source = SimpleNamespace(
        url="https://example.invalid/fixture", tenant=None, organization=None,
        observations=Mock(), check_interval_minutes=60, save=Mock(),
    )
    source.observations.exclude.return_value.first.return_value = None
    monkeypatch.setattr(
        document_sources.DocumentRemoteObservation.objects, "create", lambda **values: SimpleNamespace(**values)
    )
    # Exercise the transport body; database transaction/row behavior is covered by test_documents.
    observation = document_sources.fetch_remote_document.__wrapped__(source)
    assert observation.state == "failed"
    assert observation.error_code == "remote_connection_failed"
    assert observation.canonical_markdown == ""
    response.close.assert_called_once_with()
    pool.close.assert_called_once_with()
