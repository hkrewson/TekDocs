import json
import secrets
import socket
from unittest.mock import Mock

import pytest
import requests
from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from django.test import RequestFactory

from apps.accounts.oidc_egress import MAX_OIDC_RESPONSE_BYTES


@pytest.mark.parametrize(
    "url", ["http://identity.example.com/token", "https://127.0.0.1/token", "https://identity.example.com/token"]
)
def test_oidc_transport_rejects_unsafe_destinations(monkeypatch, url):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
    )
    response = requests.Response()
    response.status_code = 200
    response._content = b"{}"
    unguarded_send = Mock(return_value=response)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", unguarded_send)
    with get_adapter().get_requests_session() as session:
        with pytest.raises(requests.RequestException):
            session.get(url)
    unguarded_send.assert_not_called()


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    )
    response = Mock(status=200, headers={"Content-Type": "application/json"})
    response.read.return_value = b'{"issuer":"https://identity.example.com"}'
    pool = Mock()
    pool.urlopen.return_value = response
    factory = Mock(return_value=pool)
    monkeypatch.setattr("apps.accounts.oidc_egress.urllib3.HTTPSConnectionPool", factory)
    return factory, pool, response


def test_oidc_public_discovery_is_pinned_bounded_and_closed(transport):
    factory, pool, response = transport
    with get_adapter().get_requests_session() as session:
        assert session.trust_env is False
        result = session.get("https://identity.example.com/discovery")
        result.raise_for_status()
        assert result.json()["issuer"] == "https://identity.example.com"
    assert factory.call_args.args == ("8.8.8.8",)
    options = factory.call_args.kwargs
    assert options["assert_hostname"] == options["server_hostname"] == "identity.example.com"
    assert options["timeout"].connect_timeout == 3
    assert options["timeout"].read_timeout == 10
    assert options["retries"] is False
    request = pool.urlopen.call_args
    assert request.args == ("GET", "/discovery")
    assert request.kwargs["redirect"] is False
    assert request.kwargs["preload_content"] is False
    assert request.kwargs["headers"]["Host"] == "identity.example.com"
    response.read.assert_called_once_with(MAX_OIDC_RESPONSE_BYTES + 1, decode_content=False)
    response.close.assert_called_once()
    pool.close.assert_called_once()


@pytest.mark.parametrize("status", [301, 302, 307, 308, 400, 401, 500])
def test_oidc_redirects_and_errors_never_forward_or_expose_credentials(transport, status):
    _, pool, response = transport
    response.status = status
    secret = secrets.token_urlsafe(24)
    response.headers["Location"] = "https://other.example.com/token"
    response.read.return_value = secret.encode()
    with get_adapter().get_requests_session() as session:
        with pytest.raises(requests.RequestException) as error:
            session.post("https://identity.example.com/token", data={"client_secret": secret})
    assert str(error.value) == "oidc_egress_failed"
    assert error.value.request is None
    assert error.value.response is None
    response.read.assert_not_called()
    pool.urlopen.assert_called_once()
    response.close.assert_called_once()
    pool.close.assert_called_once()


@pytest.mark.parametrize("compressed", [False, True])
def test_oidc_response_size_and_encoding_are_bounded(transport, compressed):
    _, pool, response = transport
    if compressed:
        response.headers["Content-Encoding"] = "gzip"
    else:
        response.read.return_value = b"x" * (MAX_OIDC_RESPONSE_BYTES + 1)
    with get_adapter().get_requests_session() as session:
        with pytest.raises(requests.RequestException):
            session.get("https://identity.example.com/discovery")
    response.close.assert_called_once()
    pool.close.assert_called_once()


@pytest.mark.parametrize("basic_auth", [False, True])
def test_allauth_token_exchange_preserves_form_and_basic_auth(transport, basic_auth):
    _, pool, response = transport
    token = secrets.token_urlsafe(24)
    response.read.return_value = json.dumps({"access_token": token}).encode()
    client = OAuth2Client(
        RequestFactory().get("/"),
        "client-id",
        secrets.token_urlsafe(24),
        "POST",
        "https://identity.example.com/token",
        "https://docs.example.com/callback",
        basic_auth=basic_auth,
    )
    assert client.get_access_token("authorization-code")["access_token"] == token
    request = pool.urlopen.call_args
    assert request.args == ("POST", "/token")
    assert "grant_type=authorization_code" in request.kwargs["body"]
    if basic_auth:
        assert request.kwargs["headers"]["Authorization"].startswith("Basic ")
        assert "client_secret" not in request.kwargs["body"]
    else:
        assert "client_secret=" in request.kwargs["body"]


def test_oidc_mixed_public_private_dns_never_connects(transport, monkeypatch):
    factory, _, _ = transport
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in ("8.8.8.8", "10.0.0.1")
        ],
    )
    with get_adapter().get_requests_session() as session:
        with pytest.raises(requests.RequestException):
            session.get("https://identity.example.com/discovery")
    factory.assert_not_called()


def test_oidc_failed_read_closes_pool_and_hides_error_values(transport):
    from urllib3.exceptions import ReadTimeoutError

    _, pool, response = transport
    secret = secrets.token_urlsafe(24)
    response.read.side_effect = ReadTimeoutError(pool, "/token", secret)
    with get_adapter().get_requests_session() as session:
        with pytest.raises(requests.RequestException) as error:
            session.get("https://identity.example.com/discovery")
    assert str(error.value) == "oidc_egress_failed"
    response.close.assert_called_once()
    pool.close.assert_called_once()
