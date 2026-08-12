from __future__ import annotations

from django.http import HttpRequest
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .api_tokens import authenticate_bearer_token


class BearerTokenAuthentication(BaseAuthentication):
    keyword = b"bearer"

    def authenticate(self, request):  # type: ignore[no-untyped-def]
        prepared = getattr(request._request, "api_token", None)
        if prepared is not None:
            request.api_token = prepared
            return prepared.subject, prepared
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword:
            return None
        raise AuthenticationFailed("The API token is invalid or unavailable.")

    def authenticate_header(self, request) -> str:  # type: ignore[no-untyped-def]
        header = get_authorization_header(request).split()
        return "Bearer" if header and header[0].lower() == self.keyword else ""


class APITokenAuthenticationMiddleware:
    """Resolve bearer credentials before request-wide PostgreSQL RLS binding."""

    def __init__(self, get_response):  # type: ignore[no-untyped-def]
        self.get_response = get_response

    def __call__(self, request: HttpRequest):  # type: ignore[no-untyped-def]
        authorization = request.headers.get("Authorization", "")
        if authorization:
            parts = authorization.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                try:
                    token = authenticate_bearer_token(parts[1])
                except AuthenticationFailed:
                    request.api_token_invalid = True  # type: ignore[attr-defined]
                else:
                    request.api_token = token  # type: ignore[attr-defined]
                    request.user = token.subject
                    token.subject.tekdocs_api_token = token  # type: ignore[attr-defined]
            elif parts and parts[0].lower() == "bearer":
                request.api_token_invalid = True  # type: ignore[attr-defined]
        return self.get_response(request)
