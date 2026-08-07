from email.utils import getaddresses
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_email

SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"


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
