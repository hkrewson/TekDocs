import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from apps.core.models import AuditEvent, Tenant


@pytest.mark.django_db
def test_audit_model_rejects_instance_update_and_delete():
    tenant = Tenant.objects.create(name="Audit MSP", slug="audit-msp")
    event = AuditEvent.objects.create(tenant=tenant, action="audit.created", metadata={})
    event.action = "audit.rewritten"

    with pytest.raises(ValidationError, match="append-only"):
        event.save()
    with pytest.raises(ValidationError, match="append-only"):
        event.delete()


@pytest.mark.django_db
def test_postgres_rejects_queryset_and_raw_sql_audit_mutation_but_allows_inserts():
    if connection.vendor != "postgresql":
        pytest.skip("Database audit immutability requires PostgreSQL")
    tenant = Tenant.objects.create(name="Immutable Audit MSP", slug="immutable-audit")
    event = AuditEvent.objects.create(tenant=tenant, action="audit.original", metadata={})

    with pytest.raises(DatabaseError, match="insert-only"):
        with transaction.atomic():
            AuditEvent.objects.filter(id=event.id).update(action="audit.changed")
    with pytest.raises(DatabaseError, match="insert-only"):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("DELETE FROM core_auditevent WHERE id = %s", [event.id])
    event.refresh_from_db()
    assert event.action == "audit.original"
    inserted = AuditEvent.objects.create(
        tenant=tenant,
        action="audit.followup",
        request_id=uuid.uuid4(),
        metadata={},
    )
    assert AuditEvent.objects.filter(id=inserted.id).exists()
