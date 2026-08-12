import os


def create_fixture():
    from django.utils import timezone

    from apps.accounts.bootstrap import bootstrap_owner
    from apps.accounts.models import BuiltInRole, TenantMembership, User
    from apps.core.documents import create_document
    from apps.core.models import NotificationPreference, PublicationAudience, PublicationRetention
    from apps.core.notification_email import preference_for
    from apps.core.organizations import create_organization
    from apps.core.outbox import dispatch_due_outbox_events
    from apps.core.publications import approve_publication, publish_document
    from apps.core.rls import OrganizationRLSMode, rls_scope
    from apps.core.scoping import DataScope
    from apps.core.workspaces import resolve_organization_workspace

    result = bootstrap_owner(
        tenant_name="Portal Notification Recovery MSP",
        owner_email="portal-notification-recovery@example.invalid",
        owner_display_name="Portal Notification Recovery Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    with rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        organization = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Portal Notification Recovery Client",
            legal_name="Portal Notification Recovery Client LLC",
            website="",
            classifications=["client"],
        )
        approver = User.objects.create_user(
            email="portal-notification-approver@example.invalid",
            display_name="Portal Notification Recovery Approver",
        )
        TenantMembership.objects.create(tenant=result.tenant, user=approver, role=BuiltInRole.ADMINISTRATOR)
        portal_user = User.objects.create_user(
            email="portal-notification-reader@example.invalid",
            display_name="Portal Notification Recovery Reader",
        )
        TenantMembership.objects.create(
            tenant=result.tenant,
            user=portal_user,
            role=BuiltInRole.CLIENT_USER,
            organization=organization,
        )
    with rls_scope(
        DataScope.organization(result.tenant, organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    ):
        document = create_document(
            tenant=result.tenant,
            organization=organization,
            actor_id=result.owner.id,
            title="Portal notification recovery guide",
            markdown="# Recovery guide\n\nRetained portal publication and notification evidence.\n",
        )
        publication = publish_document(
            workspace=resolve_organization_workspace(result.owner, entity_id=organization.entity_id),
            document=document,
            actor_id=result.owner.id,
            reason="Portal notification recovery fixture",
            audience=PublicationAudience.CLIENT_VISIBLE,
            retention=PublicationRetention.PERMANENT,
            retention_review_on=None,
        )
        approve_publication(publication=publication, actor_id=approver.id, reason="Approved recovery fixture")
        while dispatch_due_outbox_events(tenant=result.tenant):
            pass
        portal_notification = portal_user.inbox_notifications.get(surface="client_portal")
        portal_notification.read_at = timezone.now()
        portal_notification.save(update_fields=("read_at",))
        preference = preference_for(tenant=result.tenant, user_id=portal_user.id, surface="client_portal")
        preference.delivery_mode = "daily"
        preference.timezone = "America/Chicago"
        preference.quiet_start = "22:00"
        preference.quiet_end = "07:00"
        preference.daily_digest_hour = 8
        preference.save()
        assert NotificationPreference.objects.filter(pk=preference.pk).exists()
    print("Portal, publication, outbox, inbox, email queue, preference, and retained PDF fixture created")


def verify_fixture():
    from apps.core.models import (
        DocumentPublication,
        DocumentPublicationArtifact,
        DocumentPublicationControlEvent,
        InboxNotification,
        InstallationState,
        NotificationEmailDelivery,
        NotificationPreference,
        OutboxDeliveryReceipt,
        OutboxEvent,
        Organization,
    )
    from apps.core.publications import verify_publication
    from apps.core.rls import OrganizationRLSMode, rls_scope
    from apps.core.scoping import DataScope

    state = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    assert state.tenant is not None
    with rls_scope(DataScope.tenant(state.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        organization = Organization.scoped.for_tenant(state.tenant).get(
            entity__display_name="Portal Notification Recovery Client"
        )
    with rls_scope(
        DataScope.organization(state.tenant, organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    ):
        publication = DocumentPublication.objects.get(title="Portal notification recovery guide")
        assert verify_publication(publication)["valid"] is True
        assert list(
            DocumentPublicationControlEvent.objects.filter(publication=publication)
            .order_by("occurred_at")
            .values_list("action", flat=True)
        ) == ["submitted", "approved"]
        artifact = DocumentPublicationArtifact.objects.get(publication=publication, kind="pdf")
        with artifact.file.storage.open(artifact.file.name, "rb") as stored:
            assert stored.read(5) == b"%PDF-"
        assert OutboxEvent.objects.filter(subject_id=publication.id, state="delivered").count() == 1
        assert OutboxDeliveryReceipt.objects.filter(event__subject_id=publication.id).count() == 1
        portal_notification = InboxNotification.objects.get(
            event__subject_id=publication.id,
            surface="client_portal",
        )
        assert portal_notification.read_at is not None
        assert NotificationEmailDelivery.objects.filter(notification__event__subject_id=publication.id).count() >= 2
        preference = NotificationPreference.objects.get(user=portal_notification.recipient, surface="client_portal")
        assert (preference.delivery_mode, preference.timezone, preference.daily_digest_hour) == (
            "daily",
            "America/Chicago",
            8,
        )
        assert str(preference.quiet_start) == "22:00:00"
        assert str(preference.quiet_end) == "07:00:00"
    print("Portal and notification identities, state, preferences, outbox evidence, manifest, and PDF verified")


mode = os.environ.get("TEKDOCS_FIXTURE_MODE")
if mode == "create":
    create_fixture()
elif mode == "verify":
    verify_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create or verify")
