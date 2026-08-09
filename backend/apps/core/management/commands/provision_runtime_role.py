import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg import sql

from apps.core.rls_contract import RUNTIME_ROLE


class Command(BaseCommand):
    help = "Provision the fixed non-owner PostgreSQL runtime login before migrations."

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        if connection.vendor != "postgresql":
            raise CommandError("Runtime-role provisioning requires PostgreSQL.")
        configured_role = settings.TEKDOCS_DATABASE_RUNTIME_ROLE
        password = settings.TEKDOCS_DATABASE_RUNTIME_PASSWORD
        if configured_role != RUNTIME_ROLE or re.fullmatch(r"[a-z_][a-z0-9_]{2,62}", configured_role) is None:
            raise CommandError(f"The runtime role must be {RUNTIME_ROLE}.")
        if len(password) < 32:
            raise CommandError("The runtime database password must contain at least 32 characters.")

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [configured_role])
            statement = "ALTER ROLE {}" if cursor.fetchone() else "CREATE ROLE {}"
            role_options = " WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %s"
            cursor.execute(
                sql.SQL(statement + role_options).format(sql.Identifier(configured_role)),
                [password],
            )
            cursor.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(connection.settings_dict["NAME"]),
                    sql.Identifier(configured_role),
                )
            )
        self.stdout.write("PostgreSQL runtime role provisioned without exposing its credential.")
