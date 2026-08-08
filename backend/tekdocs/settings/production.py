import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .validation import validate_production_email, validate_production_public_url, validate_production_security

DEBUG = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)  # noqa: F405
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

_required = {
    "DJANGO_SECRET_KEY": os.getenv("DJANGO_SECRET_KEY", ""),
    "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
    "TEKDOCS_MASTER_KEY": os.getenv("TEKDOCS_MASTER_KEY", ""),
    "TEKDOCS_PUBLICATION_SIGNING_KEY": os.getenv("TEKDOCS_PUBLICATION_SIGNING_KEY", ""),
    "TEKDOCS_BOOTSTRAP_TOKEN": os.getenv("TEKDOCS_BOOTSTRAP_TOKEN", ""),
}
_weak_values = {"", "changeme", "change-me", "replace-me", "development", "password", "secret"}
_invalid = [
    name for name, value in _required.items() if value.strip().lower() in _weak_values or len(value.strip()) < 32
]
if _invalid:
    raise ImproperlyConfigured(f"Missing or weak production secrets: {', '.join(_invalid)}")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain explicit production hosts")

validate_production_email(
    backend=EMAIL_BACKEND,  # noqa: F405
    host=EMAIL_HOST,  # noqa: F405
    port=EMAIL_PORT,  # noqa: F405
    default_from_email=DEFAULT_FROM_EMAIL,  # noqa: F405
    username=EMAIL_HOST_USER,  # noqa: F405
    password=EMAIL_HOST_PASSWORD,  # noqa: F405
    use_tls=EMAIL_USE_TLS,  # noqa: F405
    use_ssl=EMAIL_USE_SSL,  # noqa: F405
    allow_insecure_smtp=TEKDOCS_ALLOW_INSECURE_SMTP,  # noqa: F405
)
validate_production_public_url(
    public_url=TEKDOCS_PUBLIC_URL,  # noqa: F405
    allow_insecure=TEKDOCS_ALLOW_INSECURE_PUBLIC_URL,  # noqa: F405
)
validate_production_security(
    public_url=TEKDOCS_PUBLIC_URL,  # noqa: F405
    csrf_trusted_origins=CSRF_TRUSTED_ORIGINS,  # noqa: F405
    ssl_redirect=SECURE_SSL_REDIRECT,
    hsts_seconds=SECURE_HSTS_SECONDS,
    session_cookie_secure=SESSION_COOKIE_SECURE,
    csrf_cookie_secure=CSRF_COOKIE_SECURE,
    allow_insecure_public_url=TEKDOCS_ALLOW_INSECURE_PUBLIC_URL,  # noqa: F405
)
