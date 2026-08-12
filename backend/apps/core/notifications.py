from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.utils import timezone

from apps.accounts.models import BuiltInRole, Invitation, TenantMembership, User
from apps.accounts.policy import (
    InstallationMemberContext,
    PermissionKey,
    context_has_permission,
    require_installation_member,
)

from .models import (
    DocumentPublication,
    DocumentPublicationControlEvent,
    InboxNotification,
    NotificationEmailDelivery,
    NotificationSurface,
    OutboxEvent,
    PublicationControlAction,
)
from .outbox import OutboxDeliveryFailure, OutboxTopic
from .portal_views import _reference_projection_safe
from .rls import OrganizationRLSMode, bind_local_rls_scope
from .scoping import DataScope

INBOX_SCAN_LIMIT = 200


@dataclass(frozen=True, slots=True)
class NotificationTarget:
    kind: str
    organization_id: UUID | None = None
    publication_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class NotificationProjection:
    notification: InboxNotification
    title: str
    message: str
    target: NotificationTarget | None


def _msp_users_for_event(event: OutboxEvent, permission: PermissionKey) -> list[User]:
    installation_owner = event.tenant.installation_state.owner if hasattr(event.tenant, "installation_state") else None
    user_ids = list(
        TenantMembership.scoped.for_tenant(event.tenant)
        .filter(organization__isnull=True)
        .values_list("user_id", flat=True)
    )
    if installation_owner is not None:
        user_ids.append(installation_owner.id)
    recipients: list[User] = []
    for user in User.objects.filter(id__in=user_ids, is_active=True):
        context = require_installation_member(user)
        if context.tenant.id == event.tenant_id and context_has_permission(
            context,
            permission,
            organization=event.organization,
        ):
            recipients.append(user)
    return recipients


def _client_users_for_event(event: OutboxEvent) -> list[User]:
    memberships = TenantMembership.scoped.for_tenant(event.tenant).filter(
        organization=event.organization,
        role__in=(BuiltInRole.CLIENT_ADMINISTRATOR, BuiltInRole.CLIENT_USER),
        user__is_active=True,
    )
    return list(User.objects.filter(tenant_memberships__in=memberships).distinct())


def _accepted_client_user(event: OutboxEvent) -> User | None:
    invitation = Invitation.scoped.for_tenant(event.tenant).filter(
        id=event.subject_id,
        organization=event.organization,
        accepted_by__isnull=False,
    ).select_related("accepted_by").first()
    accepted_by = invitation.accepted_by if invitation is not None else None
    return accepted_by if accepted_by is not None and accepted_by.is_active else None


def project_inbox_notifications(event: OutboxEvent) -> None:
    """Materialize only recipient edges; display values remain read-time projections."""

    topic = OutboxTopic(event.topic)
    if event.organization is None:
        raise OutboxDeliveryFailure("delivery_failed")
    bind_local_rls_scope(
        DataScope.organization(event.tenant, event.organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    )
    if topic in {OutboxTopic.INVITATION_ISSUED, OutboxTopic.INVITATION_ACCEPTED}:
        if not Invitation.scoped.for_tenant(event.tenant).filter(
            id=event.subject_id,
            organization=event.organization,
        ).exists():
            raise OutboxDeliveryFailure("delivery_failed")
        msp_permission = PermissionKey.INVITATIONS_VIEW
    else:
        if not DocumentPublication.objects.filter(
            id=event.subject_id,
            tenant=event.tenant,
            organization=event.organization,
        ).exists():
            raise OutboxDeliveryFailure("delivery_failed")
        msp_permission = PermissionKey.DOCUMENTS_VIEW

    rows = [
        InboxNotification(
            tenant=event.tenant,
            organization=event.organization,
            event=event,
            recipient=user,
            surface=NotificationSurface.MSP,
        )
        for user in _msp_users_for_event(event, msp_permission)
    ]
    if topic in {OutboxTopic.PUBLICATION_AVAILABLE, OutboxTopic.PUBLICATION_WITHDRAWN}:
        rows.extend(
            InboxNotification(
                tenant=event.tenant,
                organization=event.organization,
                event=event,
                recipient=user,
                surface=NotificationSurface.CLIENT_PORTAL,
            )
            for user in _client_users_for_event(event)
        )
    elif topic == OutboxTopic.INVITATION_ACCEPTED:
        accepted_user = _accepted_client_user(event)
        if accepted_user is not None:
            rows.append(
                InboxNotification(
                    tenant=event.tenant,
                    organization=event.organization,
                    event=event,
                    recipient=accepted_user,
                    surface=NotificationSurface.CLIENT_PORTAL,
                )
            )
    InboxNotification.objects.bulk_create(rows, ignore_conflicts=True)
    notifications = InboxNotification.objects.filter(event=event).select_related("organization")
    NotificationEmailDelivery.objects.bulk_create(
        [
            NotificationEmailDelivery(
                tenant=notification.tenant,
                organization=notification.organization,
                notification=notification,
                recipient=notification.recipient,
                surface=notification.surface,
            )
            for notification in notifications
        ],
        ignore_conflicts=True,
    )


def _publication_for_notification(
    notification: InboxNotification,
    context: InstallationMemberContext,
) -> DocumentPublication | None:
    organization = notification.organization
    if context.surface == NotificationSurface.MSP and not context_has_permission(
        context,
        PermissionKey.DOCUMENTS_VIEW,
        organization=organization,
    ):
        return None
    if context.surface == NotificationSurface.CLIENT_PORTAL and (
        context.organization is None or context.organization.id != organization.id
    ):
        return None
    bind_local_rls_scope(
        DataScope.organization(context.tenant, organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    )
    return DocumentPublication.objects.filter(
        tenant=context.tenant,
        organization=organization,
        id=notification.event.subject_id,
    ).select_related("entity", "document", "organization__entity").first()


def _client_publication_available(publication: DocumentPublication) -> bool:
    actions = set(
        DocumentPublicationControlEvent.objects.filter(publication=publication).values_list("action", flat=True)
    )
    if PublicationControlAction.APPROVED not in actions or PublicationControlAction.WITHDRAWN in actions:
        return False
    if DocumentPublicationControlEvent.objects.filter(
        publication__supersedes=publication,
        action=PublicationControlAction.APPROVED,
    ).exists():
        return False
    return _reference_projection_safe(publication)


def authorize_notification(
    notification: InboxNotification,
    context: InstallationMemberContext,
) -> NotificationProjection | None:
    if (
        notification.tenant_id != context.tenant.id
        or notification.recipient_id != context.user.id
        or notification.surface != context.surface
    ):
        return None
    topic = OutboxTopic(notification.event.topic)
    organization = notification.organization
    bind_local_rls_scope(
        DataScope.organization(context.tenant, organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    )
    organization_target = NotificationTarget(kind="organization_overview", organization_id=organization.entity_id)

    if topic in {OutboxTopic.INVITATION_ISSUED, OutboxTopic.INVITATION_ACCEPTED}:
        invitation = Invitation.scoped.for_tenant(context.tenant).filter(
            id=notification.event.subject_id,
            organization=organization,
        ).first()
        if invitation is None:
            return None
        if context.surface == NotificationSurface.CLIENT_PORTAL:
            if topic != OutboxTopic.INVITATION_ACCEPTED or invitation.accepted_by_id != context.user.id:
                return None
            return NotificationProjection(
                notification,
                "Portal access ready",
                "Your client portal invitation was accepted.",
                NotificationTarget(kind="portal_documents"),
            )
        if not context_has_permission(context, PermissionKey.INVITATIONS_VIEW, organization=organization):
            return None
        role = "client administrator" if invitation.role == BuiltInRole.CLIENT_ADMINISTRATOR else "client user"
        action = "accepted" if topic == OutboxTopic.INVITATION_ACCEPTED else "issued"
        return NotificationProjection(
            notification,
            f"Client invitation {action}",
            f"A {role} invitation for {organization.entity.display_name} was {action}.",
            organization_target,
        )

    publication = _publication_for_notification(notification, context)
    if publication is None:
        return None
    if context.surface == NotificationSurface.CLIENT_PORTAL:
        if topic == OutboxTopic.PUBLICATION_WITHDRAWN:
            return NotificationProjection(
                notification,
                "Documentation access changed",
                "A previously available publication was withdrawn.",
                None,
            )
        if not _client_publication_available(publication):
            return None
        return NotificationProjection(
            notification,
            "Documentation published",
            f"{publication.title} is now available.",
            NotificationTarget(kind="portal_document", publication_id=publication.entity_id),
        )
    action = "withdrawn" if topic == OutboxTopic.PUBLICATION_WITHDRAWN else "published"
    return NotificationProjection(
        notification,
        f"Documentation {action}",
        f"{publication.title} was {action} for {organization.entity.display_name}.",
        NotificationTarget(kind="organization_documentation", organization_id=organization.entity_id),
    )


def notification_candidates(context: InstallationMemberContext) -> list[InboxNotification]:
    return list(
        InboxNotification.scoped.for_tenant(context.tenant)
        .filter(recipient=context.user, surface=context.surface)
        .select_related("event", "organization")
        .order_by("-created_at", "-id")[:INBOX_SCAN_LIMIT]
    )


def set_notification_read(notification: InboxNotification, *, read: bool) -> None:
    read_at = timezone.now() if read else None
    InboxNotification.objects.filter(pk=notification.pk).update(read_at=read_at)
    notification.read_at = read_at
