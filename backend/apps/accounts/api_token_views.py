from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_token_serializers import (
    APITokenCatalogSerializer,
    APITokenRotationSerializer,
    APITokenSerializer,
    APITokenWriteSerializer,
    IssuedAPITokenSerializer,
)
from .api_tokens import (
    api_tokens_for_request,
    issue_api_token,
    revoke_api_token,
    rotate_api_token,
    token_permission_catalog,
)
from .models import APITokenKind, APITokenWorkspaceScope


def _issued_payload(issued) -> dict[str, object]:  # type: ignore[no-untyped-def]
    payload = dict(APITokenSerializer(issued.record).data)
    payload["token"] = issued.plaintext
    return payload


def _private(response: Response) -> Response:
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response


class APITokenListCreateView(APIView):
    authentication_classes = [SessionAuthentication]

    @extend_schema(responses={200: APITokenCatalogSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        return _private(
            Response(
                {
                    "tokens": APITokenSerializer(api_tokens_for_request(request), many=True).data,
                    "permissions": token_permission_catalog(),
                }
            )
        )

    @extend_schema(
        request=APITokenWriteSerializer,
        responses={
            201: IssuedAPITokenSerializer,
            403: OpenApiResponse(description="Recent MFA-backed session and scope authority required"),
        },
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = APITokenWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issued = issue_api_token(
            request=request,
            name=serializer.validated_data["name"],
            kind=APITokenKind(serializer.validated_data["kind"]),
            workspace_scope=APITokenWorkspaceScope(serializer.validated_data["workspace_scope"]),
            organization_entity_id=serializer.validated_data["organization_id"],
            permissions=serializer.validated_data["permissions"],
            expires_in_days=serializer.validated_data["expires_in_days"],
        )
        return _private(Response(_issued_payload(issued), status=201))


class APITokenRotateView(APIView):
    authentication_classes = [SessionAuthentication]

    @extend_schema(
        request=APITokenRotationSerializer,
        responses={
            200: IssuedAPITokenSerializer,
            403: OpenApiResponse(description="Recent MFA-backed session and token ownership required"),
        },
    )
    def post(self, request, token_id):  # type: ignore[no-untyped-def]
        serializer = APITokenRotationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issued = rotate_api_token(
            request=request,
            token_id=token_id,
            expires_in_days=serializer.validated_data["expires_in_days"],
        )
        return _private(Response(_issued_payload(issued)))


class APITokenRevokeView(APIView):
    authentication_classes = [SessionAuthentication]

    @extend_schema(responses={200: APITokenSerializer})
    def delete(self, request, token_id):  # type: ignore[no-untyped-def]
        return _private(Response(APITokenSerializer(revoke_api_token(request=request, token_id=token_id)).data))
