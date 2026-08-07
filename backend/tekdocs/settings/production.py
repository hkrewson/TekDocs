import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "true").lower() in {"1", "true", "yes", "on"}
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

_required = {
    "DJANGO_SECRET_KEY": os.getenv("DJANGO_SECRET_KEY", ""),
    "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
    "TEKDOCS_MASTER_KEY": os.getenv("TEKDOCS_MASTER_KEY", ""),
    "TEKDOCS_PUBLICATION_SIGNING_KEY": os.getenv("TEKDOCS_PUBLICATION_SIGNING_KEY", ""),
}
_weak_values = {"", "changeme", "change-me", "replace-me", "development", "password", "secret"}
_invalid = [
    name for name, value in _required.items() if value.strip().lower() in _weak_values or len(value.strip()) < 32
]
if _invalid:
    raise ImproperlyConfigured(f"Missing or weak production secrets: {', '.join(_invalid)}")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain explicit production hosts")
