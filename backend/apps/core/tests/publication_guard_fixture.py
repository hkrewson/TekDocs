"""Exercise certificate SQL guards without running today's app on an old schema."""

import pytest
from django.db import IntegrityError, transaction

from apps.core.models import DocumentPublication


def reinsert_signed_publication(publication: DocumentPublication) -> None:
    """Keep every signed byte and identity; validation runs before uniqueness."""
    candidate = DocumentPublication(**{
        field.attname: getattr(publication, field.attname) for field in publication._meta.concrete_fields
    })
    candidate.save(force_insert=True)


def assert_current_guard_accepts(publication: DocumentPublication) -> None:
    """Prove format validation succeeds before the duplicate identity is denied."""
    with pytest.raises(IntegrityError, match="duplicate key value"), transaction.atomic():
        reinsert_signed_publication(publication)
