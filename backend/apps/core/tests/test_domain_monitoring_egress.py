import json

import pytest
from django.test import override_settings

from apps.core.approved_egress import ApprovedTarget
from apps.core.domain_monitoring_egress import (
    MAX_MONITOR_RESPONSE_BYTES,
    DomainCollectionError,
    _get_json,
    collect_domain_evidence,
)


class FakeResponse:
    def __init__(self, body=b"{}", *, status=200, content_type="application/json"):
        self.body = body
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.closed = False

    def read(self, _amount):  # type: ignore[no-untyped-def]
        return self.body

    def close(self):  # type: ignore[no-untyped-def]
        self.closed = True


class FakePool:
    response = FakeResponse()
    requests = []

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.args = args
        self.kwargs = kwargs

    def urlopen(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.requests.append((args, kwargs))
        return self.response

    def close(self):  # type: ignore[no-untyped-def]
        return None


def _pin(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr("apps.core.domain_monitoring_egress.urllib3.HTTPSConnectionPool", FakePool)
    monkeypatch.setattr(
        "apps.core.domain_monitoring_egress.resolve_public_https_target",
        lambda url, **_kwargs: ApprovedTarget(url, "monitor.example", "203.0.113.10", "/query"),
    )


@pytest.mark.parametrize(
    ("response", "error"),
    (
        (FakeResponse(status=302), "monitor_http_error"),
        (FakeResponse(content_type="text/html"), "monitor_content_type_invalid"),
        (FakeResponse(body=b"x" * (MAX_MONITOR_RESPONSE_BYTES + 1)), "monitor_response_too_large"),
        (FakeResponse(body=b"[]"), "monitor_response_invalid"),
    ),
)
def test_monitor_egress_rejects_redirect_content_type_size_and_non_object(monkeypatch, response, error):
    _pin(monkeypatch)
    FakePool.response = response
    with pytest.raises(DomainCollectionError, match=error):
        _get_json("https://monitor.example/query", accept="application/json")
    assert response.closed


@override_settings(
    TEKDOCS_RDAP_BOOTSTRAP_URL="https://iana.example/rdap/dns.json",
    TEKDOCS_DOH_URL="https://doh.example/dns-query",
)
def test_domain_collector_normalizes_expiration_registrar_dns_and_dnssec(monkeypatch):
    calls = []

    def fake_get(url, *, accept):  # type: ignore[no-untyped-def]
        calls.append((url, accept))
        if "iana.example" in url:
            return {"services": [[["com"], ["https://rdap.example"]]]}
        if "rdap.example" in url:
            return {
                "events": [{"eventAction": "expiration", "eventDate": "2027-09-01T00:00:00Z"}],
                "entities": [{"roles": ["registrar"], "vcardArray": ["vcard", [["fn", {}, "text", "Registrar Inc"]]]}],
            }
        return {"AD": True, "Answer": [{"data": "192.0.2.10", "TTL": 300}]}

    monkeypatch.setattr("apps.core.domain_monitoring_egress._get_json", fake_get)
    evidence = collect_domain_evidence("example.com")

    assert evidence.expiration_date.isoformat() == "2027-09-01"
    assert evidence.registrar == "Registrar Inc"
    assert evidence.dnssec_validated is True
    assert len(evidence.dns_answers) == 5
    assert len(json.dumps(calls)) < 2_000
