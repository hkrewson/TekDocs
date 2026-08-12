from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Q
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
from .portal_views import _reference_projection_safe, _safe_portal_publications
from .rls import OrganizationRLSMode, bind_local_rls_scope
from .scoping import DataScope

INBOX_PAGE_SIZE = 50
INBOX_SCAN_LIMIT = 100


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


def authorize_notifications(
    notifications: list[InboxNotification],
    context: InstallationMemberContext,
) -> list[NotificationProjection]:
    """Authorize a bounded history without issuing subject queries for every row."""

    eligible = [
        notification
        for notification in notifications
        if notification.tenant_id == context.tenant.id
        and notification.recipient_id == context.user.id
        and notification.surface == context.surface
    ]
    projections: dict[UUID, NotificationProjection] = {}
    by_organization: dict[UUID, list[InboxNotification]] = {}
    for notification in eligible:
        by_organization.setdefault(notification.organization_id, []).append(notification)

    for organization_notifications in by_organization.values():
        organization = organization_notifications[0].organization
        if context.surface == NotificationSurface.CLIENT_PORTAL and (
            context.organization is None or context.organization.id != organization.id
        ):
            continue
        bind_local_rls_scope(
            DataScope.organization(context.tenant, organization),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
        invitation_notifications = [
            item
            for item in organization_notifications
            if OutboxTopic(item.event.topic) in {OutboxTopic.INVITATION_ISSUED, OutboxTopic.INVITATION_ACCEPTED}
        ]
        publication_notifications = [
            item
            for item in organization_notifications
            if OutboxTopic(item.event.topic)
            not in {OutboxTopic.INVITATION_ISSUED, OutboxTopic.INVITATION_ACCEPTED}
        ]

        invitation_ids = {item.event.subject_id for item in invitation_notifications}
        invitations = {
            invitation.id: invitation
            for invitation in Invitation.scoped.for_tenant(context.tenant).filter(
                id__in=invitation_ids,
                organization=organization,
            )
        }
        can_view_invitations = (
            bool(invitation_notifications)
            and context.surface == NotificationSurface.MSP
            and context_has_permission(
                context,
                PermissionKey.INVITATIONS_VIEW,
                organization=organization,
            )
        )
        for notification in invitation_notifications:
            invitation = invitations.get(notification.event.subject_id)
            if invitation is None:
                continue
            topic = OutboxTopic(notification.event.topic)
            if context.surface == NotificationSurface.CLIENT_PORTAL:
                if topic != OutboxTopic.INVITATION_ACCEPTED or invitation.accepted_by_id != context.user.id:
                    continue
                projections[notification.id] = NotificationProjection(
                    notification,
                    "Portal access ready",
                    "Your client portal invitation was accepted.",
                    NotificationTarget(kind="portal_documents"),
                )
            elif can_view_invitations:
                role = "client administrator" if invitation.role == BuiltInRole.CLIENT_ADMINISTRATOR else "client user"
                action = "accepted" if topic == OutboxTopic.INVITATION_ACCEPTED else "issued"
                projections[notification.id] = NotificationProjection(
                    notification,
                    f"Client invitation {action}",
                    f"A {role} invitation for {organization.entity.display_name} was {action}.",
                    NotificationTarget(kind="organization_overview", organization_id=organization.entity_id),
                )

        publication_ids = {item.event.subject_id for item in publication_notifications}
        publication_records = list(
            DocumentPublication.objects.filter(
                tenant=context.tenant,
                organization=organization,
                id__in=publication_ids,
            ).select_related("entity", "document", "organization__entity")
        )
        publications = {publication.id: publication for publication in publication_records}
        available_client_ids: set[UUID] = set()
        if context.surface == NotificationSurface.CLIENT_PORTAL and publication_records:
            actions_by_publication: dict[UUID, set[str]] = {}
            for publication_id, action in DocumentPublicationControlEvent.objects.filter(
                publication_id__in=publication_ids
            ).values_list("publication_id", "action"):
                actions_by_publication.setdefault(publication_id, set()).add(action)
            superseded_ids = set(
                DocumentPublicationControlEvent.objects.filter(
                    publication__supersedes_id__in=publication_ids,
                    action=PublicationControlAction.APPROVED,
                ).values_list("publication__supersedes_id", flat=True)
            )
            safe_ids = {publication.id for publication in _safe_portal_publications(publication_records)}
            available_client_ids = {
                publication.id
                for publication in publication_records
                if PublicationControlAction.APPROVED in actions_by_publication.get(publication.id, set())
                and PublicationControlAction.WITHDRAWN not in actions_by_publication.get(publication.id, set())
                and publication.id not in superseded_ids
                and publication.id in safe_ids
            }
        can_view_documents = (
            bool(publication_notifications)
            and context.surface == NotificationSurface.MSP
            and context_has_permission(
                context,
                PermissionKey.DOCUMENTS_VIEW,
                organization=organization,
            )
        )
        for notification in publication_notifications:
            publication = publications.get(notification.event.subject_id)
            if publication is None:
                continue
            topic = OutboxTopic(notification.event.topic)
            if context.surface == NotificationSurface.CLIENT_PORTAL:
                if topic == OutboxTopic.PUBLICATION_WITHDRAWN:
                    projections[notification.id] = NotificationProjection(
                        notification,
                        "Documentation access changed",
                        "A previously available publication was withdrawn.",
                        None,
                    )
                elif publication.id in available_client_ids:
                    projections[notification.id] = NotificationProjection(
                        notification,
                        "Documentation published",
                        f"{publication.title} is now available.",
                        NotificationTarget(kind="portal_document", publication_id=publication.entity_id),
                    )
            elif can_view_documents:
                action = "withdrawn" if topic == OutboxTopic.PUBLICATION_WITHDRAWN else "published"
                projections[notification.id] = NotificationProjection(
                    notification,
                    f"Documentation {action}",
                    f"{publication.title} was {action} for {organization.entity.display_name}.",
                    NotificationTarget(
                        kind="organization_documentation",
                        organization_id=organization.entity_id,
                    ),
                )
    return [projections[item.id] for item in eligible if item.id in projections]


def notification_candidates(
    context: InstallationMemberContext,
    *,
    before: tuple[datetime, UUID] | None = None,
) -> list[InboxNotification]:
    queryset = (
        InboxNotification.scoped.for_tenant(context.tenant)
        .filter(recipient=context.user, surface=context.surface)
        .select_related("event", "organization")
        .order_by("-created_at", "-id")
    )
    if before is not None:
        created_at, notification_id = before
        queryset = queryset.filter(
            Q(created_at__lt=created_at) | Q(created_at=created_at, id__lt=notification_id)
        )
    return list(queryset[: INBOX_SCAN_LIMIT + 1])


def set_notification_read(notification: InboxNotification, *, read: bool) -> None:
    read_at = timezone.now() if read else None
    InboxNotification.objects.filter(pk=notification.pk).update(read_at=read_at)
    notification.read_at = read_at
