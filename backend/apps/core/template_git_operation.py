"""Private, exact-document lease for verified template graph/cache synchronization."""

from __future__ import annotations

import sys
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from uuid import UUID

from django.db import DatabaseError, connection

from .models import Document, WorkspaceRepository


@dataclass(slots=True)
class TemplateGitOperation:
    document_id: UUID
    workspace_id: UUID
    repository_id: UUID
    source_document_id: UUID
    thread_id: int = field(default_factory=threading.get_ident)
    active: bool = True
    changes: dict[str, bytes] | None = None


_operation: ContextVar[TemplateGitOperation | None] = ContextVar("tekdocs_template_git_operation", default=None)


def current_template_operation() -> TemplateGitOperation | None:
    active = _operation.get()
    return (
        active
        if (
            active is not None
            and active.active
            and active.thread_id == threading.get_ident()
            and connection.in_atomic_block
        )
        else None
    )


def permits_template_document(document: Document) -> bool:
    active = current_template_operation()
    return active is not None and (active.document_id, active.workspace_id) == (
        document.id,
        document.entity.workspace_id,
    )


def permits_template_reference(document: Document, source_document_id: UUID | None) -> bool:
    active = current_template_operation()
    return (
        permits_template_document(document) and active is not None and active.source_document_id == source_document_id
    )


def permits_template_repository_write(repository: WorkspaceRepository, changes: Mapping[str, bytes | None]) -> bool:
    active = current_template_operation()
    return (
        active is not None
        and active.repository_id == repository.id
        and active.changes is not None
        and dict(changes) == active.changes
    )


@contextmanager
def template_git_operation(
    document: Document, repository: WorkspaceRepository, source_document_id: UUID
) -> Iterator[TemplateGitOperation]:
    if current_template_operation() is not None or not connection.in_atomic_block:
        raise ValueError("Template synchronization requires one exact operation")
    active = TemplateGitOperation(document.id, repository.workspace_id, repository.id, source_document_id)
    token = _operation.set(active)
    previous: str | None = None
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COALESCE(current_setting('tekdocs.template_document_write', true), '')")
            previous = cursor.fetchone()[0]
            cursor.execute("SELECT set_config('tekdocs.template_document_write', %s, true)", [str(document.id)])
        yield active
    finally:
        primary_error = sys.exception()
        active.active = False
        _operation.reset(token)
        if previous is not None and not connection.needs_rollback:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('tekdocs.template_document_write', %s, true)", [previous])
            except DatabaseError:
                if primary_error is None:
                    raise
