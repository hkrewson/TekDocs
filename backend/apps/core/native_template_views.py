"""Exact-Workspace native template declarations and reviewed enrollment API."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission

from .content_authoring import AuthoredContent, ContentAuthoringConflict, ContentAuthoringError
from .content_authoring_views import ContentAuthoringSourceSerializer, _workspace
from .models import WorkspaceRepository
from .native_templates import (
    NativeTemplateConflict,
    apply_native_template,
    configure_native_template,
    detach_native_template,
    enroll_native_template,
    native_template_library,
    native_template_state,
)
from .repository_service import RepositoryFileNotFoundError, RepositoryServiceError
from .workspaces import ResolvedWorkspace


def _control_repository(workspace: ResolvedWorkspace) -> WorkspaceRepository:
    # Reviews must remain reachable when a previously granted source is removed.
    from .models import WorkspaceRepository, workspace_for_owner

    owner = workspace_for_owner(tenant=workspace.member.tenant, organization=workspace.organization)
    return WorkspaceRepository.objects.select_related("accepted_commit", "indexed_commit", "workspace").get(
        workspace=owner
    )


class NativeTemplateMutationSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["configure", "apply", "detach"])
    base_commit = serializers.CharField(max_length=64)
    base_blob = serializers.CharField(max_length=64)
    enabled = serializers.BooleanField(required=False)
    library_visible = serializers.BooleanField(required=False)
    fragment_ids = serializers.ListField(child=serializers.UUIDField(), max_length=128, required=False)
    expected_applied_revision_id = serializers.UUIDField(required=False)
    expected_available_revision_id = serializers.UUIDField(required=False)
    rules = serializers.DictField(
        child=serializers.ChoiceField(choices=["copy", "live", "pinned", "keep"]), required=False
    )
    section_id = serializers.UUIDField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        required = (
            {"enabled", "library_visible", "fragment_ids"}
            if attrs["action"] == "configure"
            else {
                "expected_applied_revision_id",
                "expected_available_revision_id",
                "section_id" if attrs["action"] == "detach" else "rules",
            }
        )
        if required - set(attrs):
            raise serializers.ValidationError("Required template operation fields are missing")
        return attrs


class NativeTemplateEnrollmentSerializer(serializers.Serializer):
    source_content_id = serializers.UUIDField()
    definition_sha256 = serializers.RegexField(r"^[0-9a-f]{64}$")
    title = serializers.CharField(max_length=240)
    rules = serializers.DictField(child=serializers.ChoiceField(choices=["copy", "live", "pinned"]))


class NativeTemplateSectionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    markdown = serializers.CharField(allow_blank=True)


class NativeTemplateSourceSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    library_visible = serializers.BooleanField()
    fragments = NativeTemplateSectionSerializer(many=True)
    selected_fragment_ids = serializers.ListField(child=serializers.UUIDField())


class NativeTemplateChangeSerializer(NativeTemplateSectionSerializer):
    mode = serializers.ChoiceField(choices=["copy", "live", "pinned"])
    state = serializers.ChoiceField(choices=["unchanged", "updated", "added", "removed", "conflict"])
    current_markdown = serializers.CharField(required=False, allow_blank=True)


class NativeTemplateReviewSerializer(serializers.Serializer):
    source_title = serializers.CharField()
    applied_revision_id = serializers.UUIDField()
    available_revision_id = serializers.UUIDField()
    expected_base = serializers.CharField()
    expected_blob = serializers.CharField()
    changes = NativeTemplateChangeSerializer(many=True)
    can_apply = serializers.BooleanField()


class NativeTemplateStatusSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["source", "enrolled", "none"])
    read_only = serializers.BooleanField()
    source = NativeTemplateSourceSerializer(required=False)
    enrollment = NativeTemplateReviewSerializer(required=False)


class NativeTemplateLibraryItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    definition_sha256 = serializers.CharField()
    sections = NativeTemplateSectionSerializer(many=True)


class NativeTemplateLibraryPageSerializer(serializers.Serializer):
    results = NativeTemplateLibraryItemSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_more = serializers.BooleanField()


class NativeTemplateView(APIView):
    @extend_schema(responses=NativeTemplateStatusSerializer)
    def get(self, request: Request, content_id: UUID, organization_entity_id: UUID | None = None) -> Response:
        workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
        repository = _control_repository(workspace)
        try:
            result = native_template_state(
                repository=repository,
                content_id=content_id,
                read_only=not context_has_permission(
                    workspace.member, PermissionKey.DOCUMENTS_EDIT, organization=workspace.organization
                ),
            )
        except RepositoryFileNotFoundError:
            return Response({"detail": "Content does not exist"}, status=404)
        except (ContentAuthoringError, RepositoryServiceError) as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(result)

    @extend_schema(request=NativeTemplateMutationSerializer, responses=ContentAuthoringSourceSerializer)
    def post(self, request: Request, content_id: UUID, organization_entity_id: UUID | None = None) -> Response:
        workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT)
        repository = _control_repository(workspace)
        serializer = NativeTemplateMutationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        action = values.pop("action")
        functions: dict[str, Callable[..., AuthoredContent]] = {
            "configure": configure_native_template,
            "apply": apply_native_template,
            "detach": detach_native_template,
        }
        function = functions[action]
        permitted = (
            {"enabled", "library_visible", "fragment_ids"}
            if action == "configure"
            else {
                "expected_applied_revision_id",
                "expected_available_revision_id",
                "section_id" if action == "detach" else "rules",
            }
        ) | {"base_commit", "base_blob"}
        if set(values) - permitted:
            raise serializers.ValidationError("Unexpected template operation fields")
        try:
            result = function(
                repository=repository,
                actor_id=request.user.id,
                request_id=getattr(request, "request_id", None),
                content_id=content_id,
                **values,
            )
        except ContentAuthoringConflict as exc:
            return Response(exc.payload, status=409)
        except (NativeTemplateConflict, ContentAuthoringError, RepositoryServiceError) as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(ContentAuthoringSourceSerializer(result).data)


class NativeTemplateLibraryView(APIView):
    @extend_schema(responses=NativeTemplateLibraryPageSerializer)
    def get(self, request: Request, organization_entity_id: UUID) -> Response:
        workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
        items = native_template_library(_control_repository(workspace))
        query = request.query_params.get("q", "").strip().casefold()
        items = [item for item in items if query in item["title"].casefold()]
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except ValueError:
            raise serializers.ValidationError("Page must be an integer") from None
        start = (page - 1) * 25
        return Response(
            {
                "results": items[start : start + 25],
                "count": len(items),
                "page": page,
                "page_size": 25,
                "has_more": start + 25 < len(items),
            }
        )


class NativeTemplateEnrollmentsView(APIView):
    @extend_schema(request=NativeTemplateEnrollmentSerializer, responses={201: ContentAuthoringSourceSerializer})
    def post(self, request: Request, organization_entity_id: UUID) -> Response:
        workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_EDIT)
        serializer = NativeTemplateEnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = enroll_native_template(
                repository=_control_repository(workspace),
                actor_id=request.user.id,
                request_id=getattr(request, "request_id", None),
                **serializer.validated_data,
            )
        except (ContentAuthoringError, RepositoryServiceError) as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(ContentAuthoringSourceSerializer(result).data, status=201)
