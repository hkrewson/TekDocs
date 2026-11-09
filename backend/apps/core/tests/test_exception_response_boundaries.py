"""Caught implementation exceptions must not supply public response text."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.core import data_flow_views, invoicing, stock
from apps.core.data_flows import DataFlowError
from apps.core.invoicing import InvoiceError
from apps.core.stock import StockError

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
    "content_graph_views.py": {"ContentIndexError"},
    "inventory_views.py": {"DjangoValidationError"},
    "invoice_views.py": {"DjangoValidationError", "InvoiceError"},
    "invoicing.py": {"StockError", "ValidationError"},
    "network_circuits.py": {"ValidationError"},
    "repository_publication_views.py": {"RepositoryServiceError"},
    "stock.py": {"ValidationError"},
    "stock_views.py": {"DjangoValidationError", "StockError"},
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
