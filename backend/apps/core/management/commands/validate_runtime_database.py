from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.core.certification import CONTROL_PLANE_GUARD_TRIGGERS
from apps.core.rls_contract import RLS_TABLES, RUNTIME_ROLE


class Command(BaseCommand):
    help = "Fail unless the current PostgreSQL connection is the constrained TekDocs runtime role."

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        if connection.vendor != "postgresql":
            raise CommandError("The supported runtime database is PostgreSQL.")
        if settings.TEKDOCS_DATABASE_RUNTIME_ROLE != RUNTIME_ROLE:
            raise CommandError(f"The configured runtime role must be {RUNTIME_ROLE}.")

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
            role = cursor.fetchone()
            if role is None:
                raise CommandError("The current PostgreSQL role is unavailable.")
            current_user, is_superuser, bypasses_rls = role
            if current_user != RUNTIME_ROLE or is_superuser or bypasses_rls:
                raise CommandError("The application must use the constrained TekDocs runtime role.")

            cursor.execute(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r' AND pg_get_userbyid(c.relowner) = current_user"
            )
            if cursor.fetchall():
                raise CommandError("The runtime role must not own application tables.")
            cursor.execute("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            if cursor.fetchone() != (False,):
                raise CommandError("The runtime role must not have schema-creation authority.")

            cursor.execute(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = ANY(%s) "
                "AND c.relrowsecurity AND c.relforcerowsecurity",
                [list(RLS_TABLES)],
            )
            active = {row[0] for row in cursor.fetchall()}
            missing = sorted(set(RLS_TABLES) - active)
            if missing:
                raise CommandError(f"Required forced-RLS tables are missing: {', '.join(missing)}")

            cursor.execute(
                "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgname = ANY(%s)",
                [list(CONTROL_PLANE_GUARD_TRIGGERS)],
            )
            active_guards = {row[0] for row in cursor.fetchall()}
            missing_guards = sorted(set(CONTROL_PLANE_GUARD_TRIGGERS) - active_guards)
            if missing_guards:
                raise CommandError(f"Required control-plane guards are missing: {', '.join(missing_guards)}")
        self.stdout.write("Runtime database role, forced-RLS inventory, and control-plane guards verified.")
