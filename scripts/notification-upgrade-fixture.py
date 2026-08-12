import os


def _invitation(*, tenant, organization, owner, email):  # type: ignore[no-untyped-def]
    from datetime import timedelta

    from django.utils import timezone

    from apps.accounts.models import BuiltInRole, Invitation

    return Invitation.objects.create(
        tenant=tenant,
        organization=organization,
        role=BuiltInRole.CLIENT_USER,
        email=email,
        token_digest=Invitation.digest_token(f"fixture-{email}"),
        invited_by=owner,
        expires_at=timezone.now() + timedelta(days=7),
    )


def create_fixture():
    from django.db import transaction

    from apps.accounts.bootstrap import bootstrap_owner
    from apps.core.models import NotificationEmailDelivery, NotificationEmailState
    from apps.core.organizations import create_organization
    from apps.core.outbox import OutboxTopic, dispatch_due_outbox_events, enqueue_outbox_event
    from apps.core.rls import OrganizationRLSMode, rls_scope
    from apps.core.scoping import DataScope

    result = bootstrap_owner(
        tenant_name="Notification Upgrade MSP",
        owner_email="notification-upgrade@example.invalid",
        owner_display_name="Notification Upgrade Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    with rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        organization = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Notification Upgrade Client",
            legal_name="Notification Upgrade Client LLC",
            website="https://notification-upgrade.example.invalid",
            classifications=["client"],
        )
        invitation = _invitation(
            tenant=result.tenant,
            organization=organization,
            owner=result.owner,
            email="historical-client@example.invalid",
        )
        with transaction.atomic():
            enqueue_outbox_event(
                tenant=result.tenant,
                organization=organization,
                topic=OutboxTopic.INVITATION_ISSUED,
                subject_id=invitation.id,
                idempotency_key="historical-invitation",
                payload={"role": "client_user"},
            )
        assert dispatch_due_outbox_events(tenant=result.tenant) == 1
        delivery = NotificationEmailDelivery.scoped.for_tenant(result.tenant).get()
        assert delivery.state == NotificationEmailState.PENDING
    print("Historical 0.5.6 SMTP delivery queued")


def verify_fixture():
    from django.db import transaction

    from apps.core.models import (
        InboxNotification,
        InstallationState,
        NotificationEmailDelivery,
        NotificationEmailState,
        Organization,
    )
    from apps.core.notification_email import dispatch_due_notification_emails
    from apps.core.outbox import OutboxTopic, dispatch_due_outbox_events, enqueue_outbox_event
    from apps.core.rls import OrganizationRLSMode, rls_scope
    from apps.core.scoping import DataScope

    state = InstallationState.objects.select_related("tenant", "owner").get(pk=InstallationState.SINGLETON_ID)
    assert state.tenant is not None and state.owner is not None
    with rls_scope(DataScope.tenant(state.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        organization = Organization.scoped.for_tenant(state.tenant).get(
            entity__display_name="Notification Upgrade Client"
        )
        assert InboxNotification.scoped.for_tenant(state.tenant).count() == 1
        historical = NotificationEmailDelivery.scoped.for_tenant(state.tenant).get()
        assert historical.state == NotificationEmailState.PENDING
        assert historical.retry_generation == 0
        assert historical.last_attempt_at is None
        invitation = _invitation(
            tenant=state.tenant,
            organization=organization,
            owner=state.owner,
            email="current-client@example.invalid",
        )
        with transaction.atomic():
            enqueue_outbox_event(
                tenant=state.tenant,
                organization=organization,
                topic=OutboxTopic.INVITATION_ISSUED,
                subject_id=invitation.id,
                idempotency_key="current-invitation",
                payload={"role": "client_user"},
            )
        assert dispatch_due_outbox_events(tenant=state.tenant) == 1
        assert InboxNotification.scoped.for_tenant(state.tenant).count() == 2
        notification = InboxNotification.scoped.for_tenant(state.tenant).order_by("-created_at").first()
        assert notification is not None
        assert notification.recipient_id == state.owner.id
        assert notification.surface == "msp"
        assert NotificationEmailDelivery.scoped.for_tenant(state.tenant).count() == 2
        assert dispatch_due_notification_emails(tenant=state.tenant) == 2
        assert (
            not NotificationEmailDelivery.scoped.for_tenant(state.tenant)
            .exclude(state=NotificationEmailState.DELIVERED)
            .exists()
        )
    print("Historical 0.5.6 queue retained; old and new items delivered through the 0.5.7 batch path")


mode = os.environ.get("TEKDOCS_FIXTURE_MODE")
if mode == "create":
    create_fixture()
elif mode == "verify":
    verify_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create or verify")
