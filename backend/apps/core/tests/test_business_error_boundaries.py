"""Domain validation wrappers must not relabel raw database failures."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.core import commercial, inventory, software_inventory, stock


@pytest.mark.parametrize("validate,error_type", (
    (commercial._validate, commercial.CommercialError),
    (inventory._validate_profile, inventory.InventoryError),
    (software_inventory._validate, software_inventory.SoftwareInventoryError),
    (stock._validate, stock.StockError),
))
@pytest.mark.parametrize("database_failure", (False, True))
def test_business_validation_only_converts_field_validation(validate, error_type, database_failure):
    public_message = "Choose a valid value for this field."
    error = (
        IntegrityError("synthetic private database diagnostic")
        if database_failure else ValidationError({"field": [public_message]})
    )
    record = SimpleNamespace(full_clean=Mock(side_effect=error))
    with pytest.raises(IntegrityError if database_failure else error_type) as caught:
        validate(record)
    if database_failure:
        # Leave database failures for the API's separate safe failure boundary.
        assert caught.value is error
    else:
        assert str(caught.value) == public_message
    record.full_clean.assert_called_once_with()
