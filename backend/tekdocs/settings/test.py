import base64
import secrets

from .base import *  # noqa: F403

SECRET_KEY = "test-secret-key-not-for-production"
TEKDOCS_MASTER_KEY = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
TEKDOCS_PUBLICATION_SIGNING_KEY = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
TEKDOCS_BOOTSTRAP_TOKEN = secrets.token_urlsafe(32)
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
