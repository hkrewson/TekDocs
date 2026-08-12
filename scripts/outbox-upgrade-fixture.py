import os


def create_fixture():
    from apps.accounts.bootstrap import bootstrap_owner
    from apps.core.organizations import create_organization
    from apps.core.rls import OrganizationRLSMode, rls_scope
    from apps.core.scoping import DataScope

    result = bootstrap_owner(
        tenant_name="Outbox Upgrade MSP",
        owner_email="outbox-upgrade@example.invalid",
        owner_display_name="Outbox Upgrade Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    with rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        organization = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Outbox Upgrade Client",
            legal_name="Outbox Upgrade Client LLC",
            website="https://outbox-upgrade.example.invalid",
            classifications=["client"],
        )
    print(result.tenant.id, organization.id)


def verify_fixture():
    from django.db import transaction

    from apps.core.models import InstallationState, Organization, OutboxDeliveryReceipt, OutboxEventState
    from apps.core.outbox import OutboxTopic, dispatch_due_outbox_events, enqueue_outbox_event
    from apps.core.rls import OrganizationRLSMode, rls_scope
    from apps.core.scoping import DataScope

    state = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    assert state.tenant is not None
    with rls_scope(DataScope.tenant(state.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        organization = Organization.scoped.for_tenant(state.tenant).get(
            entity__display_name="Outbox Upgrade Client"
        )
        with transaction.atomic():
            event = enqueue_outbox_event(
                tenant=state.tenant,
                organization=organization,
                topic=OutboxTopic.INVITATION_ISSUED,
                subject_id=organization.id,
                idempotency_key="upgrade-fixture-event",
                payload={"role": "client_user"},
            )
        assert dispatch_due_outbox_events(tenant=state.tenant) == 1
        event.refresh_from_db()
        assert event.state == OutboxEventState.DELIVERED
        assert OutboxDeliveryReceipt.objects.filter(event=event).count() == 1
    print("Historical organization retained and current outbox delivered exactly once")


mode = os.environ.get("TEKDOCS_FIXTURE_MODE")
if mode == "create":
    create_fixture()
elif mode == "verify":
    verify_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create or verify")
