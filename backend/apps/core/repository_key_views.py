"""Read native key configuration; writes use protected Git authoring, never SQL bindings."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import DataAudience, PermissionKey, context_has_permission, entity_visible_to_audience

from .content_authoring import read_authored_content
from .content_authoring_views import _locked_attachment_repository, _workspace
from .document_key_fields import addressable_fields
from .document_key_freeze import expand_rendered_content_keys
from .document_key_resolution import KeyResolutionKind, ResolutionState, audience_for, resolve_markdown_keys
from .models import ContentNode, Document, Entity
from .relationships import visible_entities_for_workspace
from .repository_key_context import canonical_key_bindings, key_context_for_node, native_fragment_nodes


class RepositoryKeyQuery(serializers.Serializer):
    q = serializers.CharField(required=False, default='', allow_blank=True, max_length=120)
    target_id = serializers.ListField(child=serializers.UUIDField(), required=False, default=list, max_length=64)


class RepositoryKeyTargetSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    kind = serializers.ChoiceField(choices=['entity', 'fragment'])
    entity_type = serializers.CharField()
    fields = serializers.ListField(child=serializers.CharField())


class RepositoryKeyReportRowSerializer(serializers.Serializer):
    expression = serializers.CharField()
    state = serializers.CharField()
    label = serializers.CharField()
    reason = serializers.CharField(allow_null=True)


class RepositoryKeyStateSerializer(serializers.Serializer):
    source_blob = serializers.CharField()
    accepted_commit = serializers.CharField()
    read_only = serializers.BooleanField()
    key_bindings = serializers.DictField(child=serializers.UUIDField())
    targets = RepositoryKeyTargetSerializer(many=True)
    bound_targets = RepositoryKeyTargetSerializer(many=True)
    has_more = serializers.BooleanField()
    report = RepositoryKeyReportRowSerializer(many=True)
    report_has_more = serializers.BooleanField()


def _entity_target(entity: Entity) -> dict[str, Any]:
    return {'id': str(entity.id), 'title': entity.display_name, 'kind': 'entity',
            'entity_type': entity.entity_type, 'fields': addressable_fields(entity.entity_type)}


def _fragment_target(node: ContentNode) -> dict[str, Any]:
    return {'id': str(node.content_id), 'title': node.title, 'kind': 'fragment',
            'entity_type': 'repository_fragment', 'fields': ['content']}


@transaction.atomic
def _keys(request: Request, content_id: UUID, organization_entity_id: UUID | None = None) -> Response:
    workspace = _workspace(request, organization_entity_id, PermissionKey.DOCUMENTS_VIEW)
    repository = _locked_attachment_repository(workspace, content_id)
    node = ContentNode.objects.get(repository=repository, content_id=content_id)
    authored = read_authored_content(repository=repository, content_id=content_id)
    query = RepositoryKeyQuery(data=request.query_params)
    query.is_valid(raise_exception=True)
    term = query.validated_data['q']
    entities = visible_entities_for_workspace(workspace=workspace, include_reference_organizations=False).filter(
        workspace=repository.workspace, organization=workspace.organization,
    ).exclude(entity_type='document_block')
    fragments = native_fragment_nodes(repository)
    fragments = fragments.exclude(content_id__in=Entity.objects.filter(
        tenant_id=repository.tenant_id, workspace_id=repository.workspace_id,
        organization=workspace.organization,
    ).values('id'))
    selected_entities = list(entities.filter(display_name__icontains=term).order_by('display_name', 'id')[:26])
    selected_fragments = list(fragments.filter(title__icontains=term).order_by('title', 'content_id')[:26])

    def visible(entity: Entity) -> bool:
        return entity_visible_to_audience(
            workspace.member, entity, audience=DataAudience.MSP_STAFF, organization=workspace.organization,
        )

    targets = [_entity_target(entity) for entity in selected_entities[:25] if visible(entity)]
    targets += [_fragment_target(fragment) for fragment in selected_fragments[:25]]
    bindings = canonical_key_bindings(node.frontmatter.get('key_bindings', {}))
    target_ids = set(bindings.values()) | {str(value) for value in query.validated_data['target_id']}
    bound_targets = [_entity_target(entity) for entity in entities.filter(id__in=target_ids) if visible(entity)]
    bound_targets += [_fragment_target(fragment) for fragment in fragments.filter(content_id__in=target_ids)]
    document = Document.objects.filter(
        id=content_id, tenant_id=repository.tenant_id, organization=workspace.organization,
        entity__workspace=repository.workspace,
    ).first()
    context = key_context_for_node(repository=repository, node=node, document=document)
    # Context-free reports show explicit missing bindings rather than reading a sibling owner.
    variant = node.composition_variants.get('all', {})
    markdown = variant.get('markdown', node.markdown)
    resolutions = resolve_markdown_keys(
        markdown, document=context, context=workspace.member,
        audience=audience_for(workspace.member), organization=workspace.organization,
        content_repository=repository,
    )
    expanded = expand_rendered_content_keys(
        workspace=workspace, document=context, markdown=markdown, content_repository=repository,
    )
    if expanded != markdown:
        resolutions.update(resolve_markdown_keys(
            expanded, document=context, context=workspace.member,
            audience=audience_for(workspace.member), organization=workspace.organization,
            content_repository=repository,
        ))
    report = []
    for result in list(resolutions.values())[:200]:
        unavailable_content = result.kind == KeyResolutionKind.CONTENT and expanded == markdown
        report.append({
            'expression': result.expression,
            'state': ResolutionState.UNRESOLVABLE.value if unavailable_content else result.state.value,
            'label': result.label,
            'reason': 'content_unavailable' if unavailable_content else result.reason,
        })
    response = Response(RepositoryKeyStateSerializer({
        'source_blob': authored.source_blob, 'accepted_commit': authored.accepted_commit,
        'read_only': document is not None or not context_has_permission(
            workspace.member, PermissionKey.DOCUMENTS_EDIT, organization=workspace.organization,
        ), 'key_bindings': bindings,
        'targets': targets, 'bound_targets': bound_targets,
        'has_more': len(selected_entities) > 25 or len(selected_fragments) > 25,
        'report': report, 'report_has_more': len(resolutions) > 200,
    }).data)
    response['Cache-Control'] = 'private, no-store'
    return response


class MSPRepositoryKeysView(APIView):
    @extend_schema(
        operation_id='content_authoring_msp_keys', parameters=[RepositoryKeyQuery],
        responses={200: RepositoryKeyStateSerializer,
                   409: OpenApiResponse(description='Saved source/index unavailable')},
    )
    def get(self, request, content_id):  # type: ignore[no-untyped-def]
        return _keys(request, content_id)


class OrganizationRepositoryKeysView(APIView):
    @extend_schema(
        operation_id='content_authoring_organization_keys', parameters=[RepositoryKeyQuery],
        responses={200: RepositoryKeyStateSerializer,
                   409: OpenApiResponse(description='Saved source/index unavailable')},
    )
    def get(self, request, organization_entity_id, content_id):  # type: ignore[no-untyped-def]
        return _keys(request, content_id, organization_entity_id)
