import re
import secrets
import uuid

import psycopg
import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.conf import settings
from django.db import DatabaseError, DataError, IntegrityError, connection, transaction

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.document_keys import (
    BINDING_NAME_PATTERN,
    KEY_TARGET_SCHEME,
    DocumentKey,
    keys_in_markdown,
    parse_key_expression,
    parse_key_target,
)
from apps.core.documents import create_document
from apps.core.models import (
    DocumentKeyBinding,
    Entity,
    InstallationState,
    Organization,
    OrganizationClassification,
    Tenant,
    workspace_for_owner,
)
from apps.core.rls_contract import RUNTIME_ROLE


def test_key_expression_accepts_a_binding_and_bounded_field_path():
    assert parse_key_expression("subject.gateway") == DocumentKey(binding="subject", path=("gateway",))
    assert parse_key_expression("subject.site.gateway") == DocumentKey(binding="subject", path=("site", "gateway"))
    assert parse_key_expression("subject.a.b.c") == DocumentKey(binding="subject", path=("a", "b", "c"))


def test_key_expression_rejects_shapes_that_would_widen_the_dialect():
    # A binding with no field would name a record rather than a value.
    assert parse_key_expression("subject") is None
    # Traversal is bounded so one key cannot walk arbitrarily far through relations.
    assert parse_key_expression("subject.a.b.c.d") is None
    # One spelling per key: the stored form is permanent.
    assert parse_key_expression("Subject.Gateway") is None
    # Separator and character discipline.
    assert parse_key_expression("subject..gateway") is None
    assert parse_key_expression("subject.gateway.") is None
    assert parse_key_expression(".subject.gateway") is None
    assert parse_key_expression("subject.gate-way") is None
    assert parse_key_expression("1subject.gateway") is None
    assert parse_key_expression("") is None


def test_key_target_round_trips_through_its_canonical_form():
    key = parse_key_target(f"{KEY_TARGET_SCHEME}subject.site.gateway")
    assert key is not None
    assert key.expression == "subject.site.gateway"
    assert key.target == "tekdocs://key/subject.site.gateway"
    assert parse_key_target(key.target) == key


def test_non_key_targets_are_not_keys():
    assert parse_key_target("tekdocs://entity/2f8d2e50-6a1f-4a55-9f0e-6c2b7b1d0a11") is None
    assert parse_key_target("https://example.invalid/subject.gateway") is None
    assert parse_key_target("tekdocs://keyring/subject.gateway") is None


def test_keys_are_collected_from_prose_and_deduplicated():
    markdown = (
        "Connect to <tekdocs://key/subject.gateway> from <tekdocs://key/subject.site.name>.\n\n"
        "The gateway is still <tekdocs://key/subject.gateway>.\n"
    )
    keys, unresolvable = keys_in_markdown(markdown)

    assert [key.expression for key in keys] == ["subject.gateway", "subject.site.name"]
    assert unresolvable == []


def test_code_regions_are_literal_because_commonmark_does_not_parse_them():
    markdown = (
        "Prose resolves <tekdocs://key/subject.gateway>.\n\n"
        "```mermaid\n"
        "graph TD\n"
        "  A{decision} --> B[<tekdocs://key/subject.gateway>]\n"
        "```\n\n"
        "```bash\n"
        'echo "<tekdocs://key/subject.gateway>"\n'
        "```\n\n"
        "Inline `<tekdocs://key/subject.gateway>` stays literal.\n\n"
        "    <tekdocs://key/subject.gateway>\n"
    )
    keys, unresolvable = keys_in_markdown(markdown)

    # One occurrence resolves: the one in prose. The Mermaid fence, the shell fence,
    # the code span, and the indented block are all literal text.
    assert [key.expression for key in keys] == ["subject.gateway"]
    assert unresolvable == []


def test_a_malformed_key_is_reported_rather_than_dropped():
    markdown = "Value is <tekdocs://key/subject> and <tekdocs://key/subject.a.b.c.d>.\n"
    keys, unresolvable = keys_in_markdown(markdown)

    assert keys == []
    assert unresolvable == ["tekdocs://key/subject", "tekdocs://key/subject.a.b.c.d"]


def test_the_binding_name_grammar_is_the_key_binding_grammar():
    """The database constraint and the key parser must accept the same names.

    A binding whose name cannot appear on the left of a key expression would be
    unreachable: no key could ever name it. Keeping one grammar in both places is
    what makes that impossible, so this test pins the two together.
    """
    for name in ("subject", "s", "site_gateway", "a1", "a" * 40):
        assert re.fullmatch(BINDING_NAME_PATTERN, name) is not None
        assert parse_key_expression(f"{name}.field") == DocumentKey(binding=name, path=("field",))
    for name in ("Subject", "gate-way", "1subject", "", "_subject", "a" * 41):
        assert re.fullmatch(BINDING_NAME_PATTERN, name) is None
        assert parse_key_expression(f"{name}.field") is None


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Keyref MSP",
        owner_email=f"keyref-{uuid.uuid4()}@example.invalid",
        owner_display_name="Keyref Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


def _organization(tenant: Tenant, name: str) -> Organization:
    anchor = Entity.objects.create_owned(tenant=tenant, entity_type="organization", display_name=name)
    record = Organization.objects.create(tenant=tenant, entity=anchor)
    OrganizationClassification.objects.create(tenant=tenant, organization=record, kind="client")
    return record


def _asset_entity(tenant: Tenant, organization: Organization | None, name: str) -> Entity:
    return Entity.objects.create(
        tenant=tenant,
        workspace=workspace_for_owner(tenant=tenant, organization=organization),
        organization=organization,
        entity_type="client_asset",
        display_name=name,
    )


def _document(installation, organization: Organization | None, title: str):
    return create_document(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        title=title,
        markdown="Reach the gateway at <tekdocs://key/subject.gateway>.",
    )


def _binding(installation, *, document, target, name="subject", organization=None) -> DocumentKeyBinding:
    return DocumentKeyBinding.objects.create(
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=organization),
        organization=organization,
        document=document,
        name=name,
        target_entity=target,
        created_by=installation.owner,
    )


@pytest.mark.django_db
def test_a_binding_records_the_record_its_keys_resolve_against(installation):
    client = _organization(installation.tenant, "Keyref client")
    document = _document(installation, client, "Client firewall runbook")
    firewall = _asset_entity(installation.tenant, client, "Edge firewall")

    binding = _binding(installation, document=document, target=firewall, organization=client)

    keys, unresolvable = keys_in_markdown("Reach the gateway at <tekdocs://key/subject.gateway>.")
    assert unresolvable == []
    assert [key.binding for key in keys] == [binding.name]
    assert document.key_bindings.get().target_entity_id == firewall.id


@pytest.mark.django_db
def test_a_binding_name_that_could_never_appear_in_a_key_is_refused_by_the_database(installation):
    client = _organization(installation.tenant, "Grammar client")
    document = _document(installation, client, "Grammar runbook")
    target = _asset_entity(installation.tenant, client, "Grammar asset")

    for rejected in ("Subject", "gate-way", "1subject", "subject.gateway", "_subject", ""):
        assert re.fullmatch(BINDING_NAME_PATTERN, rejected) is None
        with pytest.raises(IntegrityError, match="document_key_binding_name_valid"), transaction.atomic():
            _binding(installation, document=document, target=target, name=rejected, organization=client)

    # The grammar caps a segment at 40 characters and so does the column, so an
    # over-long name is refused by the column width before the check runs.
    with pytest.raises(DataError), transaction.atomic():
        _binding(installation, document=document, target=target, name="a" * 41, organization=client)


@pytest.mark.django_db
def test_a_binding_name_is_declared_once_per_document(installation):
    client = _organization(installation.tenant, "Unique client")
    document = _document(installation, client, "Unique runbook")
    first = _asset_entity(installation.tenant, client, "First asset")
    second = _asset_entity(installation.tenant, client, "Second asset")
    _binding(installation, document=document, target=first, organization=client)

    # Two targets for one name would make `subject.gateway` ambiguous within a document.
    with pytest.raises(IntegrityError, match="document_key_binding_name_unique"), transaction.atomic():
        _binding(installation, document=document, target=second, organization=client)

    # The same name in a different document is a different binding, not a conflict.
    sibling = _document(installation, client, "Sibling runbook")
    assert _binding(installation, document=sibling, target=second, organization=client).name == "subject"


@pytest.mark.django_db
def test_a_binding_cannot_reach_a_record_outside_its_workspace(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Trigger validation requires PostgreSQL")

    client = _organization(installation.tenant, "Bound client")
    other_client = _organization(installation.tenant, "Other client")
    document = _document(installation, client, "Bound runbook")
    foreign_asset = _asset_entity(installation.tenant, other_client, "Other client firewall")

    # Resolution reads fields from the target, so a cross-workspace target would be a
    # disclosure path that never passes through the reader's own scope.
    with pytest.raises(DatabaseError, match="target workspace mismatch"), transaction.atomic():
        _binding(installation, document=document, target=foreign_asset, organization=client)


@pytest.mark.django_db
def test_a_binding_cannot_be_attached_to_a_document_in_another_scope(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Trigger validation requires PostgreSQL")

    client = _organization(installation.tenant, "Attached client")
    msp_document = _document(installation, None, "MSP procedure")
    client_asset = _asset_entity(installation.tenant, client, "Attached client firewall")

    with pytest.raises(DatabaseError, match="document scope mismatch"), transaction.atomic():
        _binding(installation, document=msp_document, target=client_asset, organization=client)


@pytest.mark.django_db(transaction=True)
def test_a_binding_row_only_exists_for_its_own_workspace_under_the_runtime_role(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")

    client = _organization(installation.tenant, "Isolated client")
    sibling = _organization(installation.tenant, "Sibling client")
    document = _document(installation, client, "Isolated runbook")
    target = _asset_entity(installation.tenant, client, "Isolated firewall")
    binding = _binding(installation, document=document, target=target, organization=client)

    with (
        psycopg.connect(
            dbname=connection.settings_dict["NAME"],
            user=RUNTIME_ROLE,
            password=settings.TEKDOCS_DATABASE_RUNTIME_PASSWORD,
            host=connection.settings_dict["HOST"],
            port=connection.settings_dict["PORT"],
        ) as runtime,
        runtime.cursor() as cursor,
    ):
        for organization, expected in ((client, [(binding.id,)]), (sibling, [])):
            workspace = workspace_for_owner(tenant=installation.tenant, organization=organization)
            cursor.execute("SELECT set_config('tekdocs.tenant_id', %s, true)", [str(installation.tenant.id)])
            cursor.execute("SELECT set_config('tekdocs.workspace_id', %s, true)", [str(workspace.id)])
            cursor.execute("SELECT set_config('tekdocs.organization_id', %s, true)", [str(organization.id)])
            cursor.execute("SELECT set_config('tekdocs.organization_mode', 'organization', true)")
            cursor.execute("SELECT set_config('tekdocs.user_id', %s, true)", [str(installation.owner.id)])
            cursor.execute("SELECT set_config('tekdocs.principal_mode', 'user', true)")
            cursor.execute("SELECT id FROM core_documentkeybinding")
            assert cursor.fetchall() == expected
            runtime.commit()
