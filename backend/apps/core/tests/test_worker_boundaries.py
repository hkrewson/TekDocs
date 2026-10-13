from __future__ import annotations

from uuid import uuid4

import pytest
from django.db import connection

from apps.core import tasks

WORKERS = (
    ("process_integration_sync_job", "process_sync_job", "job_id"),
    ("process_domain_monitoring", "process_domain_monitoring_run", "run_id"),
    ("process_certificate_monitoring", "process_certificate_monitoring_run", "run_id"),
)


def current_scope():
    names = (
        "tenant_id", "workspace_id", "organization_id", "organization_mode", "user_id", "principal_mode",
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT " + ", ".join("COALESCE(current_setting(%s, true), '')" for _ in names),
            [f"tekdocs.{name}" for name in names],
        )
        return cursor.fetchone()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(("worker", "service", "identifier"), WORKERS)
@pytest.mark.parametrize("organization", (False, True))
@pytest.mark.parametrize("fails", (False, True))
def test_worker_binds_exact_scope_and_clears_it_after_completion(
    monkeypatch, worker, service, identifier, organization, fails
):
    record_id, tenant_id, workspace_id = uuid4(), uuid4(), uuid4()
    organization_id = uuid4() if organization else None
    before = current_scope()
    calls = []

    def process(**kwargs):
        calls.append(kwargs)
        assert current_scope() == (
            str(tenant_id), str(workspace_id), str(organization_id) if organization else "",
            "organization" if organization else "msp", "", "system",
        )
        if fails:
            raise RuntimeError("Injected worker failure")

    monkeypatch.setattr(tasks, service, process)
    arguments = (str(record_id), str(tenant_id), str(workspace_id), str(organization_id) if organization else None)
    if fails:
        with pytest.raises(RuntimeError, match="Injected worker failure"):
            getattr(tasks, worker)(*arguments)
    else:
        getattr(tasks, worker)(*arguments)
    assert calls == [{identifier: record_id}]
    assert current_scope() == before


@pytest.mark.parametrize(("worker", "service", "identifier"), WORKERS)
@pytest.mark.parametrize("invalid_position", (1, 2, 3))
def test_worker_rejects_malformed_scope_before_database_or_service(
    monkeypatch, worker, service, identifier, invalid_position
):
    def unexpected(**kwargs):
        pytest.fail("Malformed scope reached the provider service")

    monkeypatch.setattr(tasks, service, unexpected)
    arguments = [str(uuid4()) for _ in range(4)]
    arguments[invalid_position] = "invalid-uuid"
    with pytest.raises(ValueError):
        getattr(tasks, worker)(*arguments)
