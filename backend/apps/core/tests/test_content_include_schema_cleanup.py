import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_content_include_schema_cleanup_removes_obsolete_column(migration_head_restored):
    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0225_document_remote_application")])
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE core_contentinclude ADD COLUMN IF NOT EXISTS resolved_markdown text NOT NULL DEFAULT ''"
            )
        MigrationExecutor(connection).migrate([("core", "0226_remove_obsolete_content_include_markdown")])
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(cursor, "core_contentinclude")
        assert "resolved_markdown" not in {column.name for column in columns}
    finally:
        MigrationExecutor(connection).migrate(head)
