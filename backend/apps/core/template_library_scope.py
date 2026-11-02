"""Temporary exact-Workspace scopes for an explicitly authorized template operation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from .document_migration_publications import publication_migration_actor_allowed
from .document_template_migration import TemplateMigrationError
from .models import Workspace
from .workspace_scope import editable_workspace_scope


@contextmanager
def editable_template_workspace_scope(workspace: Workspace, actor_id: UUID) -> Iterator[None]:
    if not publication_migration_actor_allowed(workspace=workspace, actor_id=actor_id):
        raise TemplateMigrationError("template_migration_not_authorized")
    with editable_workspace_scope(workspace, actor_id):
        yield
