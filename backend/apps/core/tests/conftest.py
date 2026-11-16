import pytest
from django.core.management import call_command
from django.db import DatabaseError, connection


@pytest.fixture
def migration_head_restored(transactional_db):
    """Return the shared test database to migration head however the test ends.

    A reversal test downgrades the schema of the database every later test in the
    session shares. Restoring it only on the success path means one failed assertion
    between the downgrade and the restore leaves the whole session on a stale schema,
    which then surfaces as unrelated ``UndefinedColumn`` errors far from the real
    failure. Requesting ``transactional_db`` here orders this teardown ahead of the
    flush pytest-django performs when the test finishes.

    Reversing and reapplying the whole migration set dirties thousands of relation
    files. Left to PostgreSQL's own timing, that checkpoint lands in the middle of a
    later test and stalls one request long enough to fail a latency budget that has
    nothing to do with migrations. Forcing the checkpoint here pays that cost inside
    the test that caused it.
    """
    try:
        yield
    finally:
        call_command("migrate", "core", verbosity=0, interactive=False)
        call_command("migrate", "accounts", verbosity=0, interactive=False)
        if connection.vendor == "postgresql":
            try:
                with connection.cursor() as cursor:
                    cursor.execute("CHECKPOINT")
            except DatabaseError:  # pragma: no cover - requires a non-superuser test role
                pass
