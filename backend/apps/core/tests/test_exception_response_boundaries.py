"""Caught implementation exceptions must not supply public response text."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core import (
    asset_csv,
    commercial,
    commercial_views,
    content_authoring_views,
    custom_field_views,
    data_flow_views,
    document_views,
    inventory,
    invoicing,
    network_endpoint_views,
    network_inventory_views,
    recurring_invoice_views,
    recurring_invoices,
    rendering_views,
    repository_publication_views,
    software_inventory,
    software_inventory_views,
    stock,
)
from apps.core.asset_csv import AssetCsvError
from apps.core.catalogs import CatalogError, StaleCatalogRevision
from apps.core.certificate_monitoring import CertificateMonitoringError
from apps.core.commercial import CommercialError
from apps.core.compliance_bundles import ComplianceBundleError
from apps.core.compliance_catalogs import ComplianceCatalogError
from apps.core.compliance_evidence import ComplianceEvidenceError
from apps.core.compliance_operations import ComplianceOperationError
from apps.core.compliance_risks import ComplianceRiskError
from apps.core.content_authoring import ContentAuthoringError
from apps.core.custom_fields import (
    CustomFieldConfigurationError,
    CustomFieldValueError,
    validate_custom_field_value,
)
from apps.core.data_flows import DataFlowError
from apps.core.diagram_exports import DiagramRenderError
from apps.core.document_attachments import RepositoryPrimaryFileConflict
from apps.core.document_exports import ExportConflict
from apps.core.document_key_freeze import KeyFreezeConflict
from apps.core.document_operations import DocumentOperationsError
from apps.core.documents import PlacementConflict
from apps.core.domains import DomainError
from apps.core.inventory import InventoryError
from apps.core.invoice_recurrence import RecurrenceError
from apps.core.invoicing import InvoiceError
from apps.core.money import MoneyError
from apps.core.netbox_reconciliation import NetBoxReferenceError
from apps.core.network_endpoints import NetworkAssignmentConflict
from apps.core.network_inventory import NetworkInventoryConflict, NetworkInventoryError
from apps.core.network_services import NetworkServiceConflict, NetworkServiceError
from apps.core.publications import PublicationConflict
from apps.core.recycle_bin import RecoveryConflict
from apps.core.relationships import EntityRelationshipError
from apps.core.reminders import ReminderError
from apps.core.repository_editable_bundles import RepositoryEditableBundleError
from apps.core.repository_package_authorization import RepositoryPackageAuthorizationError
from apps.core.repository_publication_packages import RepositoryPublicationPackageError
from apps.core.repository_service import RepositoryInputError
from apps.core.repository_source_exports import RepositorySourceExportError
from apps.core.repository_static_controls import RepositoryStaticControlError
from apps.core.repository_static_delivery import RepositoryStaticDeliveryError
from apps.core.repository_static_publications import RepositoryStaticPublicationError
from apps.core.sites import SiteHierarchyError
from apps.core.software_inventory import SoftwareInventoryError
from apps.core.stock import StockError
from apps.core.taxonomies import TaxonomyError

VIEW_ROOT = Path(__file__).parents[1]

GENERIC_TRANSLATORS = (
    ("data_flow_views.py", "_refuse"),
    ("netbox_reconciliation_views.py", "_error"),
    ("network_addressing_views.py", "_error"),
    ("network_circuit_views.py", "_error"),
    ("network_endpoint_views.py", "_error"),
    ("network_service_views.py", "_error"),
)

RISKY_HANDLERS = {
    "catalog_views.py": {"CatalogError", "InventoryError", "StaleCatalogRevision"},
    "commercial_views.py": {"CommercialError", "InventoryError"},
    "compliance_bundle_views.py": {"ComplianceBundleError"},
    "compliance_catalog_views.py": {"ComplianceCatalogError", "ComplianceOperationError"},
    "compliance_evidence_views.py": {"ComplianceEvidenceError"},
    "compliance_risk_views.py": {"ComplianceRiskError"},
    "content_authoring_views.py": {
        "ContentAuthoringError",
        "RepositoryEditableBundleError",
        "RepositoryInputError",
        "RepositoryPrimaryFileConflict",
        "RepositorySourceExportError",
    },
    "content_graph_views.py": {"ContentIndexError"},
    "custom_field_views.py": {"CustomFieldConfigurationError", "CustomFieldValueError"},
    "document_views.py": {
        "DocumentOperationsError",
        "ExportConflict",
        "PlacementConflict",
        "PublicationConflict",
        "RevisionConflict",
    },
    "domain_hierarchy_views.py": {"DomainError"},
    "domain_views.py": {"CertificateMonitoringError", "DomainError"},
    "document_source_views.py": {"PlacementConflict"},
    "inventory_views.py": {
        "AssetCsvError",
        "DjangoValidationError",
        "InventoryError",
        "PublicationConflict",
        "SoftwareInventoryError",
    },
    "invoice_views.py": {"DjangoValidationError", "InvoiceError"},
    "invoicing.py": {"StockError", "ValidationError"},
    "integrations.py": {"NetBoxReferenceError"},
    "rendering_views.py": {"DiagramRenderError"},
    "network_circuits.py": {"ValidationError"},
    "netbox_reconciliation_views.py": {"InventoryError"},
    "network_addressing_views.py": {"InventoryError"},
    "network_circuit_views.py": {"InventoryError"},
    "network_endpoint_views.py": {"InventoryError", "NetworkAssignmentConflict"},
    "network_inventory_views.py": {
        "InventoryError",
        "NetworkInventoryConflict",
        "NetworkInventoryError",
    },
    "network_service_views.py": {"InventoryError", "NetworkServiceConflict"},
    "portal_views.py": {"PublicationConflict"},
    "recycle_views.py": {"RecoveryConflict"},
    "relationship_views.py": {"EntityRelationshipError"},
    "reminder_views.py": {"ReminderError"},
    "repository_publication_views.py": {
        "RepositoryPackageAuthorizationError",
        "RepositoryPublicationPackageError",
        "RepositoryServiceError",
        "RepositoryStaticControlError",
        "RepositoryStaticDeliveryError",
        "RepositoryStaticPublicationError",
    },
    "site_views.py": {"SiteHierarchyError"},
    "recurring_invoice_views.py": {"InvoiceError", "MoneyError", "RecurrenceError"},
    "stock_views.py": {"DjangoValidationError", "StockError"},
    "software_inventory_views.py": {"InventoryError", "SoftwareInventoryError"},
    "taxonomy_views.py": {"TaxonomyError"},
}


def _tree(filename: str) -> ast.Module:
    return ast.parse((VIEW_ROOT / filename).read_text())


def _exception_text_reads(node: ast.AST, name: str) -> list[ast.AST]:
    reads: list[ast.AST] = []
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "str"
            and any(isinstance(arg, ast.Name) and arg.id == name for arg in child.args)
        ):
            reads.append(child)
        if (
            isinstance(child, ast.Attribute)
            and isinstance(child.value, ast.Name)
            and child.value.id == name
            and child.attr in {"args", "detail", "message", "messages"}
        ):
            reads.append(child)
    return reads


@pytest.mark.parametrize(("filename", "function_name"), GENERIC_TRANSLATORS)
def test_generic_exception_translators_do_not_derive_public_text(filename, function_name):
    functions = [
        node
        for node in ast.walk(_tree(filename))
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    ]
    assert len(functions) == 1
    function = functions[0]
    assert function.args.args
    parameter = function.args.args[0].arg
    assert not _exception_text_reads(function, parameter)


@pytest.mark.parametrize("filename", tuple(RISKY_HANDLERS))
def test_risky_exception_handlers_do_not_derive_public_text(filename):
    risky_types = RISKY_HANDLERS[filename]
    matched = 0
    for handler in (node for node in ast.walk(_tree(filename)) if isinstance(node, ast.ExceptHandler)):
        if handler.type is None:
            continue
        names = {node.id for node in ast.walk(handler.type) if isinstance(node, ast.Name)}
        if not names & risky_types:
            continue
        matched += 1
        if handler.name is not None:
            assert not _exception_text_reads(handler, handler.name)
    assert matched


def test_data_flow_model_validation_translation_is_literal():
    translated = data_flow_views._refuse(DjangoValidationError("private model detail"))
    assert translated.status_code == 400
    assert str(translated.detail["detail"]) == "The data flow request is invalid."
    assert "private" not in str(translated.detail)


def test_data_flow_domain_refusal_uses_its_explicit_public_contract():
    translated = data_flow_views._refuse(DataFlowError("The selected source is unavailable in this workspace."))
    assert translated.status_code == 400
    assert str(translated.detail["detail"]) == "The selected source is unavailable in this workspace."


def test_invoice_model_validation_does_not_become_public():
    class InvalidInvoice:
        def full_clean(self):
            raise DjangoValidationError("private invoice model detail")

    with pytest.raises(InvoiceError) as caught:
        invoicing._validate(InvalidInvoice())

    assert caught.value.public_detail == "The invoice record is invalid."
    assert "private" not in caught.value.public_detail


def test_invoice_stock_failure_does_not_become_public(monkeypatch):
    class InvoiceLine:
        stock_item_id = 1
        stock_item = object()
        stock_quantity_consumed = 0
        organization = None

        def save(self, **kwargs):
            raise AssertionError("The failed allocation must not be saved")

    def refuse_stock_change(**kwargs):
        raise StockError("Only 1000.000 foot are on hand")

    monkeypatch.setattr(invoicing, "change_stock", refuse_stock_change)

    with pytest.raises(InvoiceError) as caught:
        invoicing._sync_stock_consumption(line=InvoiceLine(), actor_id=object(), desired_quantity=1)

    assert caught.value.public_detail == "Only 1000.000 foot are on hand"


def test_invoice_domain_refusal_retains_its_explicit_public_detail():
    refusal = InvoiceError("Only draft invoices can be edited")
    assert refusal.public_detail == "Only draft invoices can be edited"
    assert str(refusal) == "Only draft invoices can be edited"


def test_stock_model_validation_does_not_become_public():
    class InvalidStockRecord:
        def full_clean(self):
            raise DjangoValidationError("private stock model detail")

    with pytest.raises(StockError) as caught:
        stock._validate(InvalidStockRecord())

    assert caught.value.public_detail == "The stock record is invalid."
    assert "private" not in caught.value.public_detail


def test_inventory_model_validation_does_not_become_public():
    class InvalidHardwareProfile:
        def full_clean(self):
            raise DjangoValidationError("private hardware model detail")

    with pytest.raises(InventoryError) as caught:
        inventory._validate_profile(InvalidHardwareProfile())

    assert str(caught.value) == "private hardware model detail"
    assert caught.value.public_detail == "The hardware profile is invalid."


def test_software_inventory_model_validation_does_not_become_public():
    class InvalidSoftwareRecord:
        def full_clean(self):
            raise DjangoValidationError("private software model detail")

    with pytest.raises(SoftwareInventoryError) as caught:
        software_inventory._validate(InvalidSoftwareRecord())

    assert str(caught.value) == "private software model detail"
    assert caught.value.public_detail == "The software inventory record is invalid."


@pytest.mark.parametrize(
    "error",
    (
        InventoryError("private inventory diagnostic", public_detail="The inventory request is invalid."),
        AssetCsvError("private CSV diagnostic", public_detail="The asset CSV request is invalid."),
        SoftwareInventoryError(
            "private software diagnostic",
            public_detail="The software inventory request is invalid.",
        ),
    ),
)
def test_inventory_domain_errors_separate_internal_and_public_details(error):
    assert str(error).startswith("private")
    assert "private" not in error.public_detail


def test_software_inventory_domain_refusal_retains_its_public_message():
    error = SoftwareInventoryError("No seats are available on this license.")
    assert str(error) == "No seats are available on this license."
    assert error.public_detail == "No seats are available on this license."


def test_software_inventory_response_exposes_only_public_detail(monkeypatch):
    workspace = SimpleNamespace()
    monkeypatch.setattr(software_inventory_views, "_workspace", lambda *args, **kwargs: workspace)
    monkeypatch.setattr(software_inventory_views, "_asset", lambda *args, **kwargs: object())

    def refuse_update(**kwargs):
        raise SoftwareInventoryError(
            "private software database diagnostic",
            public_detail="The software inventory request is invalid.",
        )

    monkeypatch.setattr(software_inventory_views, "update_installation", refuse_update)
    request = APIRequestFactory().patch("/software/", {"status": "installed"}, format="json")
    force_authenticate(request, user=SimpleNamespace(pk=uuid4(), is_authenticated=True))
    response = software_inventory_views.ClientSoftwareInstallationDetailView.as_view()(
        request,
        organization_entity_id=uuid4(),
        asset_entity_id=uuid4(),
    )

    assert response.status_code == 400
    assert str(response.data["error"]["detail"]["detail"]) == "The software inventory request is invalid."
    assert "private software database diagnostic" not in str(response.data)


def test_software_inventory_workspace_denial_exposes_only_public_detail(monkeypatch):
    workspace = SimpleNamespace(organization=object())
    monkeypatch.setattr(
        software_inventory_views,
        "resolve_organization_workspace",
        lambda *args, **kwargs: workspace,
    )
    monkeypatch.setattr(software_inventory_views, "require_permission", lambda *args, **kwargs: None)

    def refuse_owner(organization):
        raise InventoryError(
            "private ownership database diagnostic",
            public_detail="This workspace cannot own inventory.",
        )

    monkeypatch.setattr(software_inventory_views, "require_operational_owner", refuse_owner)
    request = APIRequestFactory().get("/software-licenses/")
    force_authenticate(request, user=SimpleNamespace(pk=uuid4(), is_authenticated=True))
    response = software_inventory_views.SoftwareLicenseListCreateView.as_view()(
        request,
        organization_entity_id=uuid4(),
    )

    assert response.status_code == 403
    assert str(response.data["error"]["detail"]["detail"]) == "This workspace cannot own inventory."
    assert "private ownership database diagnostic" not in str(response.data)


def test_commercial_model_validation_does_not_become_public():
    class InvalidCommercialRecord:
        def full_clean(self):
            raise DjangoValidationError("private commercial model detail")

    with pytest.raises(CommercialError) as caught:
        commercial._validate(InvalidCommercialRecord())

    assert str(caught.value) == "private commercial model detail"
    assert caught.value.public_detail == "The commercial record is invalid."


def test_commercial_domain_refusal_retains_its_public_message():
    error = CommercialError("The cost entry is unavailable.")
    assert str(error) == "The cost entry is unavailable."
    assert error.public_detail == "The cost entry is unavailable."


def test_commercial_response_exposes_only_public_detail(monkeypatch):
    workspace = SimpleNamespace()
    monkeypatch.setattr(commercial_views, "_workspace", lambda *args, **kwargs: workspace)
    monkeypatch.setattr(commercial_views, "_record", lambda *args, **kwargs: object())

    def refuse_archive(**kwargs):
        raise CommercialError(
            "private commercial database diagnostic",
            public_detail="The commercial request is invalid.",
        )

    monkeypatch.setattr(commercial_views, "archive_contract", refuse_archive)
    request = APIRequestFactory().delete("/contracts/")
    force_authenticate(request, user=SimpleNamespace(pk=uuid4(), is_authenticated=True))
    response = commercial_views.CommercialContractDetailView.as_view()(
        request,
        organization_entity_id=uuid4(),
        contract_entity_id=uuid4(),
    )

    assert response.status_code == 400
    assert str(response.data["error"]["detail"]["detail"]) == "The commercial request is invalid."
    assert "private commercial database diagnostic" not in str(response.data)


def test_commercial_workspace_denial_exposes_only_public_detail(monkeypatch):
    workspace = SimpleNamespace(organization=object())
    monkeypatch.setattr(commercial_views, "resolve_organization_workspace", lambda *args, **kwargs: workspace)
    monkeypatch.setattr(commercial_views, "require_permission", lambda *args, **kwargs: None)

    def refuse_owner(organization):
        raise InventoryError(
            "private commercial ownership diagnostic",
            public_detail="This workspace cannot own commercial records.",
        )

    monkeypatch.setattr(commercial_views, "require_operational_owner", refuse_owner)
    request = APIRequestFactory().get("/contracts/")
    force_authenticate(request, user=SimpleNamespace(pk=uuid4(), is_authenticated=True))
    response = commercial_views.CommercialContractListCreateView.as_view()(
        request,
        organization_entity_id=uuid4(),
    )

    assert response.status_code == 403
    assert (
        str(response.data["error"]["detail"]["detail"])
        == "This workspace cannot own commercial records."
    )
    assert "private commercial ownership diagnostic" not in str(response.data)


def test_network_endpoint_workspace_denial_exposes_only_public_detail(monkeypatch):
    workspace = SimpleNamespace(organization=object())
    monkeypatch.setattr(network_endpoint_views, "resolve_msp_workspace", lambda *args, **kwargs: workspace)
    monkeypatch.setattr(network_endpoint_views, "require_permission", lambda *args, **kwargs: None)

    def refuse_owner(organization):
        raise InventoryError(
            "private network ownership diagnostic",
            public_detail="This workspace cannot own network endpoints.",
        )

    monkeypatch.setattr(network_endpoint_views, "require_operational_owner", refuse_owner)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))

    with pytest.raises(PermissionDenied) as caught:
        network_endpoint_views._workspace(request, None, network_endpoint_views.PermissionKey.NETWORKS_VIEW)

    assert str(caught.value.detail) == "This workspace cannot own network endpoints."
    assert "private network ownership diagnostic" not in str(caught.value.detail)


def test_network_assignment_conflict_exposes_only_its_public_contract():
    error = NetworkAssignmentConflict(
        "private assignment diagnostic",
        public_detail="The assignment changed. Reload before trying again.",
    )

    response = network_endpoint_views._assignment_conflict(error)

    assert response.status_code == 409
    assert response.data["detail"] == "The assignment changed. Reload before trying again."
    assert "private assignment diagnostic" not in str(response.data)


def test_network_assignment_domain_refusal_retains_its_public_message():
    error = NetworkAssignmentConflict("Choose a different interface.")

    assert str(error) == "Choose a different interface."
    assert error.public_detail == "Choose a different interface."


def test_network_inventory_workspace_denial_exposes_only_public_detail(monkeypatch):
    workspace = SimpleNamespace(organization=object())
    monkeypatch.setattr(network_inventory_views, "resolve_msp_workspace", lambda *args, **kwargs: workspace)
    monkeypatch.setattr(network_inventory_views, "require_permission", lambda *args, **kwargs: None)

    def refuse_owner(organization):
        raise InventoryError(
            "private network inventory ownership diagnostic",
            public_detail="This workspace cannot own network inventory.",
        )

    monkeypatch.setattr(network_inventory_views, "require_operational_owner", refuse_owner)
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))

    with pytest.raises(PermissionDenied) as caught:
        network_inventory_views._workspace(request, None, network_inventory_views.PermissionKey.NETWORKS_VIEW)

    assert str(caught.value.detail) == "This workspace cannot own network inventory."
    assert "private network inventory ownership diagnostic" not in str(caught.value.detail)


def test_network_inventory_service_error_exposes_only_its_public_contract():
    error = NetworkInventoryError(
        "private rack diagnostic",
        public_detail="The network inventory request is invalid.",
    )

    translated = network_inventory_views._service_error(error)

    assert translated.status_code == 400
    assert str(translated.detail["detail"]) == "The network inventory request is invalid."
    assert "private rack diagnostic" not in str(translated.detail)


def test_network_inventory_conflict_exposes_only_its_public_contract():
    error = NetworkInventoryConflict(
        "private hardware binding diagnostic",
        public_detail="The hardware binding changed. Reload before trying again.",
    )

    response = network_inventory_views._service_conflict(error)

    assert response.status_code == 409
    assert response.data["detail"] == "The hardware binding changed. Reload before trying again."
    assert "private hardware binding diagnostic" not in str(response.data)


def test_network_inventory_domain_refusal_retains_its_public_message():
    error = NetworkInventoryError("Those rack units overlap an existing device placement.")

    assert str(error) == "Those rack units overlap an existing device placement."
    assert error.public_detail == "Those rack units overlap an existing device placement."


def test_network_service_conflict_exposes_only_its_public_contract():
    error = NetworkServiceConflict(
        "private DNS conflict diagnostic",
        public_detail="The DNS record changed. Reload before trying again.",
    )

    assert str(error) == "private DNS conflict diagnostic"
    assert error.public_detail == "The DNS record changed. Reload before trying again."


@pytest.mark.parametrize("error_type", (NetworkServiceError, NetworkServiceConflict))
def test_network_service_refusals_retain_their_public_messages(error_type):
    error = error_type("The DNS record is invalid.")

    assert str(error) == "The DNS record is invalid."
    assert error.public_detail == "The DNS record is invalid."


def test_netbox_reference_error_exposes_only_its_public_contract():
    error = NetBoxReferenceError(
        "private NetBox reconciliation diagnostic",
        public_detail="The NetBox record could not be linked.",
    )

    translated = serializers.ValidationError({"detail": error.public_detail})

    assert translated.status_code == 400
    assert str(translated.detail["detail"]) == "The NetBox record could not be linked."
    assert "private NetBox reconciliation diagnostic" not in str(translated.detail)


def test_netbox_reference_refusal_retains_its_public_message():
    error = NetBoxReferenceError("That NetBox object is already linked inside this Workspace.")

    assert str(error) == "That NetBox object is already linked inside this Workspace."
    assert error.public_detail == "That NetBox object is already linked inside this Workspace."


@pytest.mark.parametrize(
    ("error_type", "public_detail"),
    (
        (ReminderError, "The selected source is unavailable in this workspace."),
        (EntityRelationshipError, "That relationship already exists."),
        (RecoveryConflict, "Restore the parent record before restoring this record."),
    ),
)
def test_remaining_response_errors_expose_only_their_public_contract(error_type, public_detail):
    error = error_type("private domain diagnostic", public_detail=public_detail)

    assert str(error) == "private domain diagnostic"
    assert error.public_detail == public_detail


@pytest.mark.parametrize(
    ("error_type", "message"),
    (
        (ReminderError, "The selected owner is unavailable."),
        (EntityRelationshipError, "A record cannot be related to itself."),
        (RecoveryConflict, "Restore the site before restoring this location."),
    ),
)
def test_remaining_response_errors_retain_their_bounded_default_message(error_type, message):
    error = error_type(message)

    assert str(error) == message
    assert error.public_detail == message


@pytest.mark.parametrize(
    ("error_type", "field", "public_detail"),
    (
        (CustomFieldConfigurationError, "entity_type", "The custom-field configuration is invalid."),
        (CustomFieldValueError, "value", "The custom-field value does not satisfy its configured rules."),
    ),
)
def test_custom_field_errors_expose_only_their_public_contract(error_type, field, public_detail):
    error = error_type("private custom-field diagnostic", public_detail=public_detail)

    translated = custom_field_views._custom_field_error(error, field=field)

    assert translated.status_code == 400
    assert str(translated.detail[field]) == public_detail
    assert "private custom-field diagnostic" not in str(translated.detail)


def test_json_schema_diagnostic_is_not_the_custom_field_public_contract():
    with pytest.raises(CustomFieldValueError) as caught:
        validate_custom_field_value(schema={"type": "integer"}, value="private custom-field value")

    assert "private custom-field value" in str(caught.value)
    assert caught.value.public_detail == "The custom-field value does not satisfy its configured rules."
    assert "private custom-field value" not in caught.value.public_detail


def test_recurring_model_validation_diagnostic_is_not_the_public_contract():
    class InvalidRecurringRecord:
        def full_clean(self):
            raise DjangoValidationError("private recurring model diagnostic")

        def save(self):
            raise AssertionError("invalid record must not be saved")

    with pytest.raises(RecurrenceError) as caught:
        recurring_invoices._save(InvalidRecurringRecord())

    assert "private recurring model diagnostic" in str(caught.value)
    assert caught.value.public_detail == "The recurring invoice record is invalid."
    assert "private recurring model diagnostic" not in caught.value.public_detail


def test_recurring_conflict_exposes_only_its_public_contract():
    def refuse():
        raise RecurrenceError(
            "private recurring diagnostic",
            public_detail="The recurring schedule changed; review it again.",
        )

    with pytest.raises(recurring_invoice_views.RecurringConflict) as caught:
        recurring_invoice_views._call(refuse)

    assert caught.value.status_code == 409
    assert str(caught.value.detail) == "The recurring schedule changed; review it again."
    assert "private recurring diagnostic" not in str(caught.value.detail)


def test_recurring_money_error_exposes_only_its_public_contract():
    def refuse():
        raise MoneyError(
            "private money diagnostic",
            public_detail="The recurring monetary values are invalid.",
        )

    with pytest.raises(serializers.ValidationError) as caught:
        recurring_invoice_views._call(refuse)

    assert caught.value.status_code == 400
    assert str(caught.value.detail["detail"]) == "The recurring monetary values are invalid."
    assert "private money diagnostic" not in str(caught.value.detail)


@pytest.mark.parametrize(
    ("error_type", "message"),
    (
        (CustomFieldConfigurationError, "Unsupported target record type."),
        (CustomFieldValueError, "The value is invalid."),
        (RecurrenceError, "The approved terms changed; review the schedule again"),
        (MoneyError, "Amount cannot be negative"),
    ),
)
def test_framework_boundary_domain_errors_retain_their_default_public_message(error_type, message):
    error = error_type(message)

    assert str(error) == message
    assert error.public_detail == message


@pytest.mark.parametrize(
    "error_type",
    (
        ComplianceBundleError,
        ComplianceCatalogError,
        ComplianceEvidenceError,
        ComplianceOperationError,
        ComplianceRiskError,
    ),
)
def test_compliance_errors_expose_only_their_public_contract(error_type):
    error = error_type(
        "private compliance diagnostic",
        public_detail="The compliance request is invalid.",
    )

    translated = serializers.ValidationError({"detail": error.public_detail})

    assert translated.status_code == 400
    assert str(translated.detail["detail"]) == "The compliance request is invalid."
    assert "private compliance diagnostic" not in str(translated.detail)


@pytest.mark.parametrize(
    "error_type",
    (
        ComplianceBundleError,
        ComplianceCatalogError,
        ComplianceEvidenceError,
        ComplianceOperationError,
        ComplianceRiskError,
    ),
)
def test_compliance_domain_refusals_retain_their_public_messages(error_type):
    error = error_type("The selected compliance record is unavailable.")

    assert str(error) == "The selected compliance record is unavailable."
    assert error.public_detail == "The selected compliance record is unavailable."


@pytest.mark.parametrize("error_type", (DomainError, CertificateMonitoringError))
def test_domain_errors_expose_only_their_public_contract(error_type):
    error = error_type(
        "private domain diagnostic",
        public_detail="The domain request is invalid.",
    )

    translated = serializers.ValidationError({"detail": error.public_detail})

    assert translated.status_code == 400
    assert str(translated.detail["detail"]) == "The domain request is invalid."
    assert "private domain diagnostic" not in str(translated.detail)


@pytest.mark.parametrize("error_type", (DomainError, CertificateMonitoringError))
def test_domain_refusals_retain_their_public_messages(error_type):
    error = error_type("The selected domain record is unavailable.")

    assert str(error) == "The selected domain record is unavailable."
    assert error.public_detail == "The selected domain record is unavailable."


def test_site_hierarchy_error_exposes_only_its_public_contract():
    error = SiteHierarchyError(
        "private location hierarchy diagnostic",
        public_detail="The selected parent location is unavailable.",
    )

    translated = serializers.ValidationError({"parent_id": error.public_detail})

    assert translated.status_code == 400
    assert str(translated.detail["parent_id"]) == "The selected parent location is unavailable."
    assert "private location hierarchy diagnostic" not in str(translated.detail)


def test_site_hierarchy_refusal_retains_its_public_message():
    error = SiteHierarchyError("A location cannot be moved beneath itself.")

    assert str(error) == "A location cannot be moved beneath itself."
    assert error.public_detail == "A location cannot be moved beneath itself."


@pytest.mark.parametrize("error_type", (ContentAuthoringError, RepositoryInputError))
def test_content_authoring_input_errors_expose_only_their_public_contract(error_type):
    error = error_type(
        "private authoring diagnostic",
        public_detail="The content authoring request is invalid.",
    )

    response = content_authoring_views._authoring_input_error(error)

    assert response.status_code == 400
    assert response.data["detail"] == "The content authoring request is invalid."
    assert "private authoring diagnostic" not in str(response.data)


@pytest.mark.parametrize(
    "error_type",
    (RepositoryPrimaryFileConflict, RepositorySourceExportError, RepositoryEditableBundleError),
)
def test_content_authoring_conflicts_expose_only_their_public_contract(error_type):
    error = error_type(
        "private authoring conflict diagnostic",
        public_detail="The repository content changed.",
    )

    response = content_authoring_views._authoring_conflict(error)

    assert response.status_code == 409
    assert response.data["detail"] == "The repository content changed."
    assert "private authoring conflict diagnostic" not in str(response.data)


@pytest.mark.parametrize(
    "error_type",
    (
        ContentAuthoringError,
        RepositoryInputError,
        RepositoryPrimaryFileConflict,
        RepositorySourceExportError,
        RepositoryEditableBundleError,
    ),
)
def test_content_authoring_domain_refusals_retain_their_public_messages(error_type):
    error = error_type("The repository content is unavailable.")

    assert str(error) == "The repository content is unavailable."
    assert error.public_detail == "The repository content is unavailable."


@pytest.mark.parametrize(
    "error_type",
    (
        RepositoryPublicationPackageError,
        RepositoryPackageAuthorizationError,
        RepositoryStaticPublicationError,
        RepositoryStaticControlError,
        RepositoryStaticDeliveryError,
    ),
)
def test_repository_publication_conflicts_expose_only_their_public_contract(error_type):
    error = error_type(
        "private repository diagnostic",
        public_detail="The repository publication request conflicts with its retained state.",
    )

    response = repository_publication_views._publication_conflict(error)

    assert response.status_code == 409
    assert response.data["detail"] == "The repository publication request conflicts with its retained state."
    assert "private repository diagnostic" not in str(response.data)


@pytest.mark.parametrize(
    "error_type",
    (
        RepositoryPublicationPackageError,
        RepositoryPackageAuthorizationError,
        RepositoryStaticPublicationError,
        RepositoryStaticControlError,
        RepositoryStaticDeliveryError,
    ),
)
def test_repository_publication_domain_refusals_retain_their_public_messages(error_type):
    error = error_type("The retained publication record is unavailable.")

    assert str(error) == "The retained publication record is unavailable."
    assert error.public_detail == "The retained publication record is unavailable."


def test_asset_csv_row_wrapper_propagates_only_the_nested_public_detail():
    wrapped = asset_csv._row_error(
        7,
        InventoryError("private hardware diagnostic", public_detail="The hardware profile is invalid."),
    )
    assert str(wrapped) == "Row 7: private hardware diagnostic"
    assert wrapped.public_detail == "Row 7: The hardware profile is invalid."


def test_catalog_error_separates_internal_and_public_details():
    error = CatalogError("private catalog diagnostic", public_detail="The catalog request is invalid.")
    assert str(error) == "private catalog diagnostic"
    assert error.public_detail == "The catalog request is invalid."


def test_stale_catalog_revision_has_a_fixed_public_detail():
    error = StaleCatalogRevision(object())  # type: ignore[arg-type]
    assert str(error) == "The model changed after this edit began."
    assert error.public_detail == "The model changed after this edit began."


@pytest.mark.parametrize(
    ("error_type", "message"),
    (
        (DocumentOperationsError, "The selected person is unavailable."),
        (PlacementConflict, "The selected placement is unavailable."),
        (ExportConflict, "The document cannot be exported."),
        (KeyFreezeConflict, "A referenced key is unavailable."),
        (PublicationConflict, "The document cannot be published."),
        (TaxonomyError, "The selected taxonomy term is invalid."),
    ),
)
def test_document_domain_errors_expose_only_their_explicit_public_contract(error_type, message):
    error = error_type("private diagnostic", public_detail=message)
    assert str(error) == "private diagnostic"
    assert error.public_detail == message


def test_diagram_render_error_exposes_only_its_explicit_public_contract():
    error = DiagramRenderError(
        "private renderer diagnostic",
        code="diagram.renderer.timeout",
        public_detail="The isolated diagram renderer timed out.",
    )
    assert str(error) == "private renderer diagnostic"
    assert error.public_detail == "The isolated diagram renderer timed out."


def test_diagram_render_error_retains_its_safe_default_message():
    error = DiagramRenderError(
        "The isolated diagram renderer timed out.",
        code="diagram.renderer.timeout",
    )
    assert str(error) == "The isolated diagram renderer timed out."
    assert error.public_detail == "The isolated diagram renderer timed out."


def test_diagram_preview_response_exposes_only_the_public_detail(monkeypatch):
    monkeypatch.setattr(rendering_views, "require_installation_member", lambda _user: None)
    monkeypatch.setattr(rendering_views.DiagramPreviewView, "throttle_classes", [])

    def fail_render(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise DiagramRenderError(
            "private renderer path /srv/renderer/jobs/example",
            code="diagram.renderer.unavailable",
            public_detail="The isolated diagram renderer is unavailable.",
        )

    monkeypatch.setattr(rendering_views, "render_diagram_exports", fail_render)
    request = APIRequestFactory().post(
        "/api/v1/render/diagram-preview",
        {"source": "flowchart LR\nA-->B"},
        format="json",
    )
    force_authenticate(request, user=SimpleNamespace(is_authenticated=True))

    response = rendering_views.DiagramPreviewView.as_view()(request)

    assert response.status_code == 503
    assert response.data == {
        "code": "diagram.renderer.unavailable",
        "detail": "The isolated diagram renderer is unavailable.",
    }
    assert "private renderer path" not in str(response.data)


def test_document_conflict_response_uses_only_the_explicit_public_contract():
    translated = document_views._placement_conflict(
        PlacementConflict("private composition diagnostic", public_detail="The composition is unavailable.")
    )
    assert translated.status_code == 409
    assert translated.data["detail"] == "The composition is unavailable."
    assert "private" not in str(translated.data)


@pytest.mark.parametrize(
    ("filename", "function_name"),
    (
        ("publications.py", "publish_document"),
        ("document_git_publications.py", "_validated_git_publication_content"),
    ),
)
def test_publication_renderer_translates_only_its_explicit_safe_error(filename, function_name):
    functions = [
        node
        for node in ast.walk(_tree(filename))
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    ]
    assert len(functions) == 1
    renderer_guards = [
        node
        for node in ast.walk(functions[0])
        if isinstance(node, ast.Try)
        and any(
            isinstance(statement, ast.Assign)
            and any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "render_diagram_exports"
                for call in ast.walk(statement)
            )
            for statement in node.body
        )
    ]
    assert len(renderer_guards) == 1
    caught_names = {
        name.id
        for handler in renderer_guards[0].handlers
        if handler.type is not None
        for name in ast.walk(handler.type)
        if isinstance(name, ast.Name)
    }
    assert caught_names == {"DiagramRenderError"}
