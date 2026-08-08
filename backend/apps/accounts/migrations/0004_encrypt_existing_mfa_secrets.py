import json

from django.conf import settings
from django.db import migrations

from apps.core.crypto import EnvelopeCipher

PREFIX = "tdmfa1:"
ASSOCIATED_DATA = b"tekdocs:mfa-authenticator:v1"


def encrypt_value(cipher, value):  # type: ignore[no-untyped-def]
    if value.startswith(PREFIX):
        return value
    envelope = cipher.encrypt(value.encode("utf-8"), ASSOCIATED_DATA)
    return PREFIX + json.dumps(envelope.as_dict(), separators=(",", ":"), sort_keys=True)


def encrypt_existing_secrets(apps, schema_editor):  # type: ignore[no-untyped-def]
    authenticator_model = apps.get_model("mfa", "Authenticator")
    cipher = EnvelopeCipher.from_base64(settings.TEKDOCS_MASTER_KEY)
    for authenticator in authenticator_model.objects.all().iterator():
        data = dict(authenticator.data)
        changed = False
        for field in ("secret", "seed"):
            value = data.get(field)
            if isinstance(value, str):
                data[field] = encrypt_value(cipher, value)
                changed = True
        codes = data.get("migrated_codes")
        if isinstance(codes, list):
            data["migrated_codes"] = [encrypt_value(cipher, code) for code in codes]
            changed = True
        if changed:
            authenticator.data = data
            authenticator.save(update_fields=["data"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_invitation_acceptance"),
        ("mfa", "0001_initial"),
    ]

    operations = [migrations.RunPython(encrypt_existing_secrets, migrations.RunPython.noop)]
