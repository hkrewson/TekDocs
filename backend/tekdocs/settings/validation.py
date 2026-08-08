import re
from collections.abc import Mapping
from email.utils import getaddresses
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_email

SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
OIDC_ENVIRONMENT_KEYS = (
    "TEKDOCS_OIDC_PROVIDER_ID",
    "TEKDOCS_OIDC_PROVIDER_NAME",
    "TEKDOCS_OIDC_DISCOVERY_URL",
    "TEKDOCS_OIDC_CLIENT_ID",
    "TEKDOCS_OIDC_CLIENT_SECRET",
)
OIDC_PROVIDER_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def oidc_provider_from_environment(environment: Mapping[str, str]) -> dict[str, str] | None:
    values = {key: environment.get(key, "") for key in OIDC_ENVIRONMENT_KEYS}
    configured = [key for key, value in values.items() if value]
    if not configured:
        return None
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ImproperlyConfigured("Incomplete OIDC configuration: " + ", ".join(missing))

    provider_id = values["TEKDOCS_OIDC_PROVIDER_ID"]
    name = values["TEKDOCS_OIDC_PROVIDER_NAME"]
    discovery_url = values["TEKDOCS_OIDC_DISCOVERY_URL"]
    client_id = values["TEKDOCS_OIDC_CLIENT_ID"]
    client_secret = values["TEKDOCS_OIDC_CLIENT_SECRET"]
    errors: list[str] = []

    if not OIDC_PROVIDER_ID.fullmatch(provider_id):
        errors.append("TEKDOCS_OIDC_PROVIDER_ID must use lowercase letters, digits, underscores, or hyphens")
    if name.strip() != name or not name or len(name) > 40 or any(ord(character) < 32 for character in name):
        errors.append("TEKDOCS_OIDC_PROVIDER_NAME must be 1-40 printable characters without outer whitespace")
    if client_id.strip() != client_id or not client_id or len(client_id) > 191:
        errors.append("TEKDOCS_OIDC_CLIENT_ID must be 1-191 characters without outer whitespace")
    if not client_secret or len(client_secret) > 191 or any(ord(character) < 32 for character in client_secret):
        errors.append("TEKDOCS_OIDC_CLIENT_SECRET must be 1-191 characters without control characters")

    try:
        parsed = urlsplit(discovery_url)
        hostname = parsed.hostname
    except ValueError:
        parsed = urlsplit("")
        hostname = None
    if discovery_url.strip() != discovery_url or parsed.scheme != "https" or not hostname:
        errors.append("TEKDOCS_OIDC_DISCOVERY_URL must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        errors.append("TEKDOCS_OIDC_DISCOVERY_URL cannot contain credentials, a query, or a fragment")

    if errors:
        raise ImproperlyConfigured("Invalid OIDC configuration: " + "; ".join(errors))
    return {
        "id": provider_id,
        "name": name,
        "discovery_url": discovery_url,
        "client_id": client_id,
        "client_secret": client_secret,
    }


def validate_production_public_url(*, public_url: str, allow_insecure: bool) -> None:
    errors: list[str] = []
    try:
        parsed = urlsplit(public_url)
        hostname = parsed.hostname
    except ValueError:
        parsed = urlsplit("")
        hostname = None
    if public_url.strip() != public_url or any(ord(character) < 32 for character in public_url):
        errors.append("TEKDOCS_PUBLIC_URL cannot contain whitespace or control characters")
    if parsed.scheme not in {"http", "https"} or not hostname:
        errors.append("TEKDOCS_PUBLIC_URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        errors.append("TEKDOCS_PUBLIC_URL cannot contain credentials, a query, or a fragment")
    if parsed.scheme != "https" and not allow_insecure:
        errors.append("HTTP requires TEKDOCS_ALLOW_INSECURE_PUBLIC_URL=true")
    if errors:
        raise ImproperlyConfigured("Invalid public URL configuration: " + "; ".join(errors))


def validate_production_email(
    *,
    backend: str,
    host: str,
    port: int,
    default_from_email: str,
    username: str,
    password: str,
    use_tls: bool,
    use_ssl: bool,
    allow_insecure_smtp: bool,
) -> None:
    errors: list[str] = []
    if backend != SMTP_BACKEND:
        errors.append("EMAIL_BACKEND must use Django's SMTP backend")
    if not host.strip():
        errors.append("EMAIL_HOST is required")
    if not 1 <= port <= 65535:
        errors.append("EMAIL_PORT must be between 1 and 65535")
    if use_tls and use_ssl:
        errors.append("EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled")
    if not use_tls and not use_ssl and not allow_insecure_smtp:
        errors.append("plaintext SMTP requires TEKDOCS_ALLOW_INSECURE_SMTP=true")
    if bool(username.strip()) != bool(password):
        errors.append("EMAIL_HOST_USER and EMAIL_HOST_PASSWORD must be configured together")

    addresses = getaddresses([default_from_email])
    sender_address = addresses[0][1] if len(addresses) == 1 else ""
    if "\r" in default_from_email or "\n" in default_from_email or not sender_address:
        errors.append("DEFAULT_FROM_EMAIL must contain one valid address without newlines")
    else:
        try:
            validate_email(sender_address)
        except ValidationError:
            errors.append("DEFAULT_FROM_EMAIL must contain one valid address without newlines")

    if errors:
        raise ImproperlyConfigured("Invalid production email configuration: " + "; ".join(errors))


def validate_production_security(
    *,
    public_url: str,
    csrf_trusted_origins: list[str],
    ssl_redirect: bool,
    hsts_seconds: int,
    session_cookie_secure: bool,
    csrf_cookie_secure: bool,
    allow_insecure_public_url: bool,
) -> None:
    parsed_public_url = urlsplit(public_url)
    public_origin = f"{parsed_public_url.scheme}://{parsed_public_url.netloc}"
    errors: list[str] = []
    if not ssl_redirect and not allow_insecure_public_url:
        errors.append("SECURE_SSL_REDIRECT must be enabled")
    if hsts_seconds < 31536000:
        errors.append("SECURE_HSTS_SECONDS must be at least 31536000")
    if not session_cookie_secure:
        errors.append("SESSION_COOKIE_SECURE must be enabled")
    if not csrf_cookie_secure:
        errors.append("CSRF_COOKIE_SECURE must be enabled")
    if public_origin not in csrf_trusted_origins:
        errors.append("DJANGO_CSRF_TRUSTED_ORIGINS must include the TEKDOCS_PUBLIC_URL origin")
    for origin in csrf_trusted_origins:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path not in {"", "/"}:
            errors.append("DJANGO_CSRF_TRUSTED_ORIGINS entries must be absolute origins")
            break
        if parsed.scheme != "https" and not allow_insecure_public_url:
            errors.append("DJANGO_CSRF_TRUSTED_ORIGINS entries must use HTTPS")
            break
    if errors:
        raise ImproperlyConfigured("Invalid production security configuration: " + "; ".join(errors))
