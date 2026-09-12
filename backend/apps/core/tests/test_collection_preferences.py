# ruff: noqa: F811
import pytest
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.models import BuiltInRole, OrganizationAccessAssignment, TenantMembership, User
from apps.accounts.policy import PermissionKey
from apps.core.collection_preferences import COLLECTIONS, CollectionDefinition
from apps.core.models import CollectionPreference, Tenant
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope
from apps.core.tests.test_inventory import _organization, installation, owner_client  # noqa: F401


def url(organization=None):
    if organization:
        return reverse(
            "organization-collection-preferences",
            kwargs={"organization_entity_id": organization.entity_id, "feature": "assets"},
        )
    return reverse("msp-collection-preferences", kwargs={"feature": "assets"})


@pytest.mark.django_db
def test_defaults_save_across_workspaces_and_reset(owner_client, installation):
    client = _organization(installation, "Client", "client")
    result = owner_client.get(url())
    assert result.status_code == 200
    defaults = result.json()
    assert defaults["columns"] == ["name", "model", "status", "assignment", "site", "warranty"]
    assert defaults["page_size"] == 25
    assert result["Cache-Control"] == "private, no-store"
    assert not CollectionPreference.objects.exists()  # reads have no persistence side effect
    assert owner_client.get(url(), {"page": 1}).status_code == 400
    assert owner_client.get(url().replace("assets", "unknown")).status_code == 404
    result = owner_client.put(url(), {"columns": ["site", "name"], "page_size": 100}, content_type="application/json")
    assert result.status_code == 200, result.content
    assert result.json()["columns"] == ["name", "site"]
    other_device = Client()
    other_device.force_login(installation.owner)
    assert other_device.get(url(client)).json() == result.json()
    assert owner_client.delete(url(client)).json() == defaults
    assert not CollectionPreference.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body",
    [
        {"columns": ["model"], "page_size": 25},
        {"columns": ["name", "name"], "page_size": 25},
        {"columns": ["name", "secret"], "page_size": 25},
        {"columns": ["name"], "page_size": 10},
        {"columns": ["name"], "page_size": 25, "filters": {"client": "private"}},
        {"columns": ["name"], "page_size": 25, "user": "other"},
        {"columns": ["name"], "page_size": 25, "tenant": "other"},
        [],
        [{}],
    ],
)
def test_rejects_invalid_or_private_state(owner_client, body):
    assert owner_client.put(url(), body, content_type="application/json").status_code == 400
    assert not CollectionPreference.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_runtime_user_tenant_and_workspace_isolation(installation, django_runtime_role, monkeypatch):
    allowed = _organization(installation, "Allowed", "client")
    denied = _organization(installation, "Denied", "client")
    reader = User.objects.create_user(email="preferences-reader@example.invalid", display_name="Reader")
    member = TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)
    access = OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant, organization=allowed, membership=member, created_by=installation.owner
    )
    other_tenant = Tenant.objects.create(name="Other installation")
    CollectionPreference.objects.create(
        tenant=other_tenant, user=reader, feature="assets", columns=["name"], page_size=50
    )
    CollectionPreference.objects.create(
        tenant=installation.tenant, user=installation.owner, feature="assets", columns=["name"], page_size=100
    )
    browser = Client()
    browser.force_login(reader)
    with django_runtime_role():
        assert browser.get(url(allowed)).json()["page_size"] == 25
        saved = browser.put(
            url(allowed), {"columns": ["name", "warranty"], "page_size": 50}, content_type="application/json"
        )
        assert saved.status_code == 200, saved.content
        assert browser.get(url(denied)).status_code in {403, 404}
        # Exercise a column whose policy changed after persistence. Actual Assets
        # columns currently share ASSETS_VIEW; future features can restrict each.
        original = COLLECTIONS["assets"]
        monkeypatch.setitem(
            COLLECTIONS,
            "assets",
            CollectionDefinition(
                original.permission,
                tuple(
                    (key, PermissionKey.ASSETS_EDIT if key == "warranty" else permission)
                    for key, permission in original.columns
                ),
                original.defaults,
            ),
        )
        current = browser.get(url(allowed)).json()
        assert current["columns"] == ["name"]
        assert "warranty" not in current["available_columns"] + current["default_columns"]
        assert (
            browser.put(
                url(allowed), {"columns": ["name", "warranty"], "page_size": 50}, content_type="application/json"
            ).status_code
            == 400
        )
        with transaction.atomic():
            bind_local_rls_scope(
                DataScope.tenant(installation.tenant),
                organization_mode=OrganizationRLSMode.MSP_ONLY,
                actor_user_id=reader.pk,
                principal_mode=RLSPrincipalMode.USER,
            )
            assert list(CollectionPreference.objects.values_list("user_id", flat=True)) == [reader.pk]
            with pytest.raises(DatabaseError), transaction.atomic():
                CollectionPreference.objects.update(user_id=installation.owner.pk)
            with pytest.raises(DatabaseError), transaction.atomic():
                CollectionPreference.objects.update(tenant=other_tenant)
    access.delete()
    with django_runtime_role():
        assert browser.get(url(allowed)).status_code in {403, 404}
    assert Client().get(url()).status_code in {401, 403}


@pytest.mark.django_db(transaction=True)
def test_upgrade_and_preference_restore(installation, tmp_path):
    """Exercise pre-feature upgrade and portable record restore at migration head."""
    from io import StringIO

    from django.core.management import call_command
    from django.db.migrations.executor import MigrationExecutor

    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0148_recurring_invoice_guards")])
        assert "core_collectionpreference" not in connection.introspection.table_names()
        MigrationExecutor(connection).migrate(head)
        preference = CollectionPreference.objects.create(
            tenant=installation.tenant,
            user=installation.owner,
            feature="assets",
            columns=["name", "status"],
            page_size=100,
        )
        output = StringIO()
        call_command("dumpdata", "core.CollectionPreference", stdout=output)
        fixture = tmp_path / "personal-collections.json"
        fixture.write_text(output.getvalue())
        CollectionPreference.objects.all().delete()
        call_command("loaddata", str(fixture), verbosity=0)
        restored = CollectionPreference.objects.get(pk=preference.pk)
        assert (restored.tenant_id, restored.user_id, restored.columns, restored.page_size) == (
            installation.tenant.pk,
            installation.owner.pk,
            ["name", "status"],
            100,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'core_collectionpreference'"
            )
            assert cursor.fetchone() == (True, True)
        with pytest.raises(DatabaseError), transaction.atomic():
            CollectionPreference.objects.filter(pk=preference.pk).update(page_size=10)
    finally:
        MigrationExecutor(connection).migrate(head)
