"""Immutable pinned consumers do not retain a live writer on their source."""

from importlib import import_module

from django.db import migrations

PREVIOUS = import_module("apps.core.migrations.0194_fragment_authority_scope_validation").FORWARD_SQL
LIVE_ONLY = PREVIOUS.replace(
    "WHERE block.id=NEW.content_id",
    "WHERE block.id=NEW.content_id AND placement.resolution_mode='live'",
)


class Migration(migrations.Migration):
    dependencies = [("core", "0198_shared_git_publication")]
    operations = [migrations.RunSQL(LIVE_ONLY, PREVIOUS)]
