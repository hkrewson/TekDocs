from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from django.conf import settings
from django.db import connection

from apps.core.rls_contract import RUNTIME_ROLE


@pytest.fixture
def django_runtime_role():  # type: ignore[no-untyped-def]
    """Temporarily reconnect Django through the constrained production database role.

    Tests using this fixture must request transactional database access so no outer
    test transaction is attached to the owner connection when it is replaced.
    """

    @contextmanager
    def switch() -> Iterator[None]:
        if connection.vendor != "postgresql":
            pytest.skip("Runtime-role validation requires PostgreSQL")
        if connection.in_atomic_block:
            raise RuntimeError("Runtime-role tests require transaction=True database access")
        original_user = connection.settings_dict["USER"]
        original_password = connection.settings_dict["PASSWORD"]
        connection.close()
        connection.settings_dict["USER"] = RUNTIME_ROLE
        connection.settings_dict["PASSWORD"] = settings.TEKDOCS_DATABASE_RUNTIME_PASSWORD
        try:
            yield
        finally:
            connection.close()
            connection.settings_dict["USER"] = original_user
            connection.settings_dict["PASSWORD"] = original_password

    return switch
