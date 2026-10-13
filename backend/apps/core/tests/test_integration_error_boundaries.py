"""Integration adoption exposes domain guidance, not internal diagnostics."""

from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError

from apps.core import integrations
from apps.core.netbox_reconciliation import NetBoxReferenceError


@pytest.mark.parametrize("failure", ("remote_id", "internal", "domain"))
def test_netbox_adoption_error_boundary(failure):
    private_message = "synthetic private integration diagnostic"
    public_message = "That NetBox object is already linked inside this Workspace."
    workspace = SimpleNamespace(
        data_scope=SimpleNamespace(workspace_id=uuid4()),
        member=SimpleNamespace(tenant=object()),
        organization=object(),
    )
    conflict = SimpleNamespace(
        connection=SimpleNamespace(provider=integrations.IntegrationProvider.NETBOX),
        difference="unmatched",
        observation=object(),
        remote_type="ipam.prefix",
        remote_id=private_message if failure == "remote_id" else "42",
        remote_fingerprint="fixture-fingerprint",
        save=Mock(),
    )
    error = NetBoxReferenceError(public_message) if failure == "domain" else ValueError(private_message)
    with (
        patch.object(integrations.IntegrationConflict.scoped, "for_scope") as conflicts,
        patch.object(integrations.NetworkSubnet.scoped, "for_scope") as subnets,
        patch("apps.core.netbox_reconciliation.set_reference", side_effect=error) as set_reference,
    ):
        conflicts.return_value.select_for_update.return_value.select_related.return_value.get.return_value = conflict
        subnets.return_value.filter.return_value.exists.return_value = True
        # Exercise only the error translation; database/transaction behavior is
        # covered separately by the integration service suite.
        with pytest.raises(ValidationError) as caught:
            integrations.adopt_netbox_conflict.__wrapped__(
                workspace=workspace, conflict_id=uuid4(), actor=SimpleNamespace(pk=uuid4()), entity_id=uuid4(),
            )
        expected = public_message if failure == "domain" else "The NetBox record could not be linked."
        assert str(caught.value.detail["detail"]) == expected
        assert private_message not in str(caught.value.detail)
        conflict.save.assert_not_called()
        if failure == "remote_id":
            set_reference.assert_not_called()
        else:
            set_reference.assert_called_once()
            assert set_reference.call_args.kwargs["object_id"] == 42
