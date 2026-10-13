"""Requests compatibility for allauth over TekDocs' approved outbound boundary."""

import socket
from typing import Any

import requests
import urllib3
from django.core.exceptions import ValidationError
from urllib3.exceptions import HTTPError

from apps.core.approved_egress import ApprovedEgressError, pinned_https_pool, resolve_public_https_target

MAX_OIDC_RESPONSE_BYTES = 1024 * 1024


class OIDCEgressAdapter(requests.adapters.HTTPAdapter):
    def send(self, request: requests.PreparedRequest, *args: Any, **kwargs: Any) -> requests.Response:
        # Never delegate to Requests' proxy, DNS, redirect or unbounded read path.
        if request.method not in {"GET", "POST"}:
            raise requests.ConnectionError("oidc_method_not_allowed")
        try:
            target = resolve_public_https_target(
                str(request.url), resolver=socket.getaddrinfo, label="OIDC", allow_query=True
            )
            pool = pinned_https_pool(
                target, connect_timeout=3.0, read_timeout=10.0, pool_factory=urllib3.HTTPSConnectionPool
            )
            try:
                response = pool.urlopen(
                    request.method,
                    target.path,
                    body=request.body,
                    headers={**request.headers, "Host": target.hostname, "Accept-Encoding": "identity"},
                    redirect=False,
                    assert_same_host=False,
                    preload_content=False,
                )
                try:
                    if response.status not in {200, 201}:
                        raise ApprovedEgressError("oidc_http_error")
                    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                        raise ApprovedEgressError("oidc_response_encoding_invalid")
                    body = response.read(MAX_OIDC_RESPONSE_BYTES + 1, decode_content=False)
                    if len(body) > MAX_OIDC_RESPONSE_BYTES:
                        raise ApprovedEgressError("oidc_response_too_large")
                    result = requests.Response()
                    result.status_code = response.status
                    result.headers = requests.structures.CaseInsensitiveDict(response.headers)
                    result._content = body
                    result.encoding = "utf-8"
                    return result
                finally:
                    response.close()
            finally:
                pool.close()
        except (ApprovedEgressError, ValidationError, HTTPError, OSError, ValueError):
            # Provider errors can contain credentials or query values. Do not
            # attach the request/response or chain a value-bearing exception.
            raise requests.ConnectionError("oidc_egress_failed") from None


def oidc_requests_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.mount("https://", OIDCEgressAdapter())
    session.mount("http://", OIDCEgressAdapter())
    return session
