import secrets

from .base import *  # noqa: F403

SECRET_KEY = "test-secret-key-not-for-production"
TEKDOCS_BOOTSTRAP_TOKEN = secrets.token_urlsafe(32)
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
MIGRATION_MODULES = {"sites": None}
