"""Value-free custody fingerprints for retained monitored-source workflow state."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder

from .approved_egress import ApprovedEgressError
from .document_source_models import DocumentRemoteSource, DocumentSourceKind
from .models import Document


class MonitoredSourceStateError(ValueError):
    def __init__(self) -> None:
        super().__init__("monitored_source_history_unavailable")


class _CustodyJSONEncoder(DjangoJSONEncoder):
    def default(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return super().default(value)


def monitored_source_fingerprint(document: Document) -> str | None:
    """Validate exact ownership and actual observation bytes, including archived sources.

    This is SQL workflow custody, not authored Git content. Stream history in a
    stable order so a long-running source does not require loading all bodies.
    Callers performing a handoff or write hold the source row lock.
    """
    source = DocumentRemoteSource.objects.filter(document_id=document.id).first()
    if source is None:
        return None
    if (
        source.tenant_id != document.tenant_id or source.organization_id != document.organization_id
        or source.source_kind not in DocumentSourceKind.values
        or not 15 <= source.check_interval_minutes <= 10080
    ):
        raise MonitoredSourceStateError()
    from .document_sources import validate_remote_source_url

    try:
        validate_remote_source_url(source.url)
    except (ApprovedEgressError, ValidationError, ValueError) as exc:
        raise MonitoredSourceStateError() from exc
    digest = hashlib.sha256()

    def retain(values: dict[str, Any]) -> None:
        digest.update(json.dumps(values, cls=_CustodyJSONEncoder, sort_keys=True, separators=(",", ":")).encode())
        digest.update(b"\n")

    retain({field.attname: getattr(source, field.attname) for field in source._meta.concrete_fields})
    applied_found = source.last_applied_observation_id is None
    # A retained body can be multi-megabyte; do not buffer a hundred of them.
    for observation in source.observations.order_by("id").iterator(chunk_size=4):
        body = observation.canonical_markdown.encode()
        successful = observation.state in {"changed", "unchanged"}
        if (
            observation.tenant_id != source.tenant_id or observation.organization_id != source.organization_id
            or observation.state not in {"changed", "unchanged", "failed"}
            or (hashlib.sha256(body).hexdigest() if body else "") != observation.content_digest
            or (successful and (not body or observation.error_code or observation.status_code != 200))
            or (not successful and not observation.error_code)
        ):
            raise MonitoredSourceStateError()
        if observation.id == source.last_applied_observation_id:
            if not successful:
                raise MonitoredSourceStateError()
            applied_found = True
        retain({field.attname: getattr(observation, field.attname) for field in observation._meta.concrete_fields})
    if not applied_found:
        raise MonitoredSourceStateError()
    return digest.hexdigest()
