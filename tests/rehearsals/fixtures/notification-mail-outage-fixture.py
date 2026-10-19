import os
import secrets


def bind_fixture_owner(tenant, owner):  # type: ignore[no-untyped-def]
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    # This rehearsal runs against current runtime RLS, as the bootstrap owner.
    bind_local_rls_scope(
        DataScope.tenant(tenant),
        organization_mode=OrganizationRLSMode.MSP_ONLY,
        actor_user_id=owner.id,
        principal_mode=RLSPrincipalMode.USER,
    )


def load_state():  # type: ignore[no-untyped-def]
    from apps.core.models import InstallationState

    state = InstallationState.objects.select_related("tenant", "owner").get(pk=InstallationState.SINGLETON_ID)
    assert state.tenant is not None and state.owner is not None
    return state


def create_fixture() -> None:
    from datetime import timedelta

    from django.db import transaction
    from django.utils import timezone

    from apps.accounts.bootstrap import bootstrap_owner
    from apps.accounts.models import BuiltInRole, Invitation
    from apps.core.models import NotificationEmailDelivery, Organization
    from apps.core.organizations import create_organization
    from apps.core.outbox import OutboxTopic, dispatch_due_outbox_events, enqueue_outbox_event
    from apps.core.rls import OrganizationRLSMode, rls_scope
    from apps.core.scoping import DataScope

    result = bootstrap_owner(
        tenant_name="Notification Outage MSP",
        owner_email="notification-outage@example.invalid",
        owner_display_name="Notification Outage Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    with rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        organization = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Notification Outage Client",
            legal_name="Notification Outage Client LLC",
            website="",
            classifications=["client"],
        )
        visible_client = Organization.scoped.for_tenant(result.tenant).filter(
            pk=organization.pk, entity__archived_at__isnull=True, classifications__kind="client"
        )
        assert not visible_client.exists(), (
            "Runtime organization reads must fail closed without an explicit principal"
        )
        bind_fixture_owner(result.tenant, result.owner)
        assert visible_client.exists()
        invitation = Invitation.objects.create(
            tenant=result.tenant,
            organization=organization,
            role=BuiltInRole.CLIENT_USER,
            email="outage-client@example.invalid",
            token_digest=Invitation.digest_token(secrets.token_urlsafe(32)),
            invited_by=result.owner,
            expires_at=timezone.now() + timedelta(days=7),
        )
        with transaction.atomic():
            enqueue_outbox_event(
                tenant=result.tenant,
                organization=organization,
                topic=OutboxTopic.INVITATION_ISSUED,
                subject_id=invitation.id,
                idempotency_key="outage-invitation",
                payload={"role": "client_user"},
            )
        assert dispatch_due_outbox_events(tenant=result.tenant) == 1
        assert NotificationEmailDelivery.scoped.for_tenant(result.tenant).count() == 1


def observe_outage() -> None:
    from apps.core.models import NotificationEmailDelivery, NotificationEmailState
    from apps.core.notification_email import dispatch_due_notification_emails
    from apps.core.rls import OrganizationRLSMode, rls_scope
    from apps.core.scoping import DataScope

    state = load_state()
    with rls_scope(DataScope.tenant(state.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        bind_fixture_owner(state.tenant, state.owner)
        assert dispatch_due_notification_emails(tenant=state.tenant) == 0
        delivery = NotificationEmailDelivery.scoped.for_tenant(state.tenant).get()
        assert delivery.state == NotificationEmailState.PENDING
        assert delivery.attempts == 1
        assert delivery.last_error_code == "smtp_unavailable"


def recover() -> None:
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.models import NotificationEmailDelivery, NotificationEmailState
    from apps.core.notification_email import dispatch_due_notification_emails
    from apps.core.rls import OrganizationRLSMode, rls_scope
    from apps.core.scoping import DataScope

    state = load_state()
    with rls_scope(DataScope.tenant(state.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        bind_fixture_owner(state.tenant, state.owner)
        assert dispatch_due_notification_emails(
            tenant=state.tenant,
            now=timezone.now() + timedelta(hours=1),
        ) == 1
        delivery = NotificationEmailDelivery.scoped.for_tenant(state.tenant).get()
        assert delivery.state == NotificationEmailState.DELIVERED
        assert delivery.attempts == 2


mode = os.environ.get("TEKDOCS_FIXTURE_MODE")
if mode == "create":
    create_fixture()
elif mode == "outage":
    observe_outage()
elif mode == "recover":
    recover()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create, outage, or recover")
