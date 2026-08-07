import secrets

import pytest
from django.core.exceptions import ImproperlyConfigured

from tekdocs.settings.base import env_int
from tekdocs.settings.validation import SMTP_BACKEND, validate_production_email, validate_production_public_url

VALID_CONFIGURATION = {
    "backend": SMTP_BACKEND,
    "host": "smtp.example.com",
    "port": 587,
    "default_from_email": "TekDocs <noreply@example.com>",
    "username": "smtp-user",
    "password": secrets.token_urlsafe(24),
    "use_tls": True,
    "use_ssl": False,
    "allow_insecure_smtp": False,
}


def test_valid_production_email_configuration_is_accepted():
    validate_production_email(**VALID_CONFIGURATION)


def test_non_integer_email_setting_is_rejected(monkeypatch):
    monkeypatch.setenv("EMAIL_PORT", "not-a-port")
    with pytest.raises(ImproperlyConfigured, match="must be an integer"):
        env_int("EMAIL_PORT", 587)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"backend": "django.core.mail.backends.console.EmailBackend"}, "SMTP backend"),
        ({"host": ""}, "EMAIL_HOST"),
        ({"port": 0}, "EMAIL_PORT"),
        ({"default_from_email": "not-an-address"}, "DEFAULT_FROM_EMAIL"),
        ({"default_from_email": "one@example.com, two@example.com"}, "DEFAULT_FROM_EMAIL"),
        ({"default_from_email": "noreply@example.com\nBcc: exposed@example.com"}, "DEFAULT_FROM_EMAIL"),
        ({"username": "smtp-user", "password": ""}, "configured together"),
        ({"use_tls": True, "use_ssl": True}, "cannot both"),
        (
            {"use_tls": False, "use_ssl": False, "allow_insecure_smtp": False},
            "TEKDOCS_ALLOW_INSECURE_SMTP",
        ),
    ],
)
def test_invalid_production_email_configuration_is_rejected(changes, message):
    with pytest.raises(ImproperlyConfigured, match=message):
        validate_production_email(**{**VALID_CONFIGURATION, **changes})


@pytest.mark.parametrize(
    ("public_url", "allow_insecure"),
    [
        ("https://docs.example.com", False),
        ("http://localhost:3200", True),
        ("https://docs.example.com/tekdocs", False),
    ],
)
def test_valid_public_url_configuration_is_accepted(public_url, allow_insecure):
    validate_production_public_url(public_url=public_url, allow_insecure=allow_insecure)


@pytest.mark.parametrize(
    "public_url",
    [
        "http://docs.example.com",
        "docs.example.com",
        "https://user:password@docs.example.com",
        "https://docs.example.com?token=unsafe",
        "https://docs.example.com#unsafe",
        "https://docs.example.com\n.evil.test",
        "https://[invalid",
    ],
)
def test_invalid_public_url_configuration_is_rejected(public_url):
    with pytest.raises(ImproperlyConfigured, match="public URL"):
        validate_production_public_url(public_url=public_url, allow_insecure=False)
