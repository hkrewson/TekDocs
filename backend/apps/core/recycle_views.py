from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .recycle_bin import (
    RecoverableRecordType,
    RecoveryConflict,
    recycle_bin_items,
    restore_recycle_bin_item,
)
from .recycle_serializers import RecycleBinQuerySerializer, RecycleBinResultSerializer
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


def _workspace(request, organization_entity_id: UUID | None) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    if organization_entity_id is None:
        workspace = resolve_msp_workspace(request.user)
    else:
        workspace = resolve_organization_workspace(request.user, entity_id=organization_entity_id)
    require_permission(request.user, PermissionKey.RECYCLE_BIN_VIEW, organization=workspace.organization)
    return workspace


def _not_found() -> NotFound:
    return NotFound("The archived record is not available in this workspace.")


class RecycleBinListView(APIView):
    @extend_schema(
        parameters=[RecycleBinQuerySerializer],
        responses={
            200: RecycleBinResultSerializer,
            403: OpenApiResponse(description="Recycle-bin view permission required"),
            404: OpenApiResponse(description="Organization workspace not found"),
        },
    )
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        query = RecycleBinQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        items = recycle_bin_items(workspace)
        if values["record_type"]:
            items = [item for item in items if item.record_type == values["record_type"]]
        if values["q"]:
            needle = values["q"].casefold()
            items = [item for item in items if needle in item.label.casefold()]
        count = len(items)
        offset = (values["page"] - 1) * values["page_size"]
        selected = items[offset : offset + values["page_size"]]
        payload = {
            "results": selected,
            "page": values["page"],
            "page_size": values["page_size"],
            "count": count,
            "has_more": offset + len(selected) < count,
        }
        return Response(RecycleBinResultSerializer(payload).data)


class RecycleBinRestoreView(APIView):
    @extend_schema(
        request=None,
        responses={
            204: OpenApiResponse(description="Archived record restored"),
            403: OpenApiResponse(description="Recovery and domain permission plus MFA required"),
            404: OpenApiResponse(description="Archived record not found"),
            409: OpenApiResponse(description="Archived dependencies must be recovered first"),
        },
    )
    def post(self, request, record_type, record_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        try:
            selected_type = RecoverableRecordType(record_type)
            restore_recycle_bin_item(
                workspace=workspace,
                user=request.user,
                record_type=selected_type,
                record_id=record_id,
            )
        except RecoveryConflict as exc:
            return Response({"detail": str(exc)}, status=409)
        except (ValueError, ObjectDoesNotExist):
            raise _not_found() from None
        return Response(status=204)


@extend_schema_view(get=extend_schema(operation_id="recycle_bin_msp_list"))
class MSPRecycleBinListView(RecycleBinListView):
    pass


@extend_schema_view(post=extend_schema(operation_id="recycle_bin_msp_restore"))
class MSPRecycleBinRestoreView(RecycleBinRestoreView):
    pass


@extend_schema_view(get=extend_schema(operation_id="recycle_bin_organization_list"))
class OrganizationRecycleBinListView(RecycleBinListView):
    pass


@extend_schema_view(post=extend_schema(operation_id="recycle_bin_organization_restore"))
class OrganizationRecycleBinRestoreView(RecycleBinRestoreView):
    pass
