from __future__ import annotations

import ast
from pathlib import Path

import pytest


def database_handlers():
    for path in sorted(Path(__file__).parents[1].glob("*views.py")):
        for handler in ast.walk(ast.parse(path.read_text())):
            if not isinstance(handler, ast.ExceptHandler) or handler.type is None:
                continue
            names = {node.id for node in ast.walk(handler.type) if isinstance(node, ast.Name)}
            if names & {"IntegrityError", "DatabaseError"}:
                yield pytest.param(handler, id=f"{path.name}:{handler.lineno}")


@pytest.mark.parametrize("handler", list(database_handlers()))
def test_database_handlers_do_not_render_raw_exception_text(handler):
    for call in ast.walk(handler):
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "str":
            assert not any(isinstance(arg, ast.Name) and arg.id == handler.name for arg in call.args)


@pytest.mark.parametrize("module,error_name", (
    ("repository_publication_packages", "RepositoryPublicationPackageError"),
    ("repository_package_authorization", "RepositoryPackageAuthorizationError"),
    ("repository_static_publications", "RepositoryStaticPublicationError"),
    ("repository_static_controls", "RepositoryStaticControlError"),
    ("repository_static_delivery", "RepositoryStaticDeliveryError"),
))
def test_publication_workflow_errors_have_literal_public_messages(module, error_name):
    tree = ast.parse((Path(__file__).parents[1] / f"{module}.py").read_text())
    constructors = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == error_name
    ]
    assert constructors
    for call in constructors:
        assert len(call.args) == 1
        assert isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str)
