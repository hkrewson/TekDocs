import secrets

import pytest
from django.core.exceptions import ImproperlyConfigured

from tekdocs.settings.base import env_int
from tekdocs.settings.validation import (
    SMTP_BACKEND,
    oidc_provider_from_environment,
    validate_production_email,
    validate_production_public_url,
    validate_production_security,
)

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


OIDC_CONFIGURATION = {
    "TEKDOCS_OIDC_PROVIDER_ID": "company-sso",
    "TEKDOCS_OIDC_PROVIDER_NAME": "Company SSO",
    "TEKDOCS_OIDC_DISCOVERY_URL": "https://identity.example.com/.well-known/openid-configuration",
    "TEKDOCS_OIDC_CLIENT_ID": "tekdocs-client",
    "TEKDOCS_OIDC_CLIENT_SECRET": secrets.token_urlsafe(32),
}


def test_oidc_is_optional_and_complete_configuration_is_accepted():
    assert oidc_provider_from_environment({}) is None
    provider = oidc_provider_from_environment(OIDC_CONFIGURATION)
    assert provider == {
        "id": "company-sso",
        "name": "Company SSO",
        "discovery_url": OIDC_CONFIGURATION["TEKDOCS_OIDC_DISCOVERY_URL"],
        "client_id": "tekdocs-client",
        "client_secret": OIDC_CONFIGURATION["TEKDOCS_OIDC_CLIENT_SECRET"],
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"TEKDOCS_OIDC_CLIENT_SECRET": ""},
        {"TEKDOCS_OIDC_PROVIDER_ID": "Company SSO"},
        {"TEKDOCS_OIDC_PROVIDER_NAME": " Company SSO"},
        {"TEKDOCS_OIDC_DISCOVERY_URL": "http://identity.example.com/.well-known/openid-configuration"},
        {"TEKDOCS_OIDC_DISCOVERY_URL": "https://user:secret@identity.example.com/config"},
        {"TEKDOCS_OIDC_DISCOVERY_URL": "https://identity.example.com/config?secret=unsafe"},
    ],
)
def test_partial_or_malformed_oidc_configuration_is_rejected(changes):
    with pytest.raises(ImproperlyConfigured, match="OIDC configuration"):
        oidc_provider_from_environment({**OIDC_CONFIGURATION, **changes})


VALID_SECURITY_CONFIGURATION = {
    "public_url": "https://docs.example.com",
    "csrf_trusted_origins": ["https://docs.example.com"],
    "ssl_redirect": True,
    "hsts_seconds": 31536000,
    "session_cookie_secure": True,
    "csrf_cookie_secure": True,
    "allow_insecure_public_url": False,
}


def test_valid_production_security_configuration_is_accepted():
    validate_production_security(**VALID_SECURITY_CONFIGURATION)


@pytest.mark.parametrize(
    "changes",
    [
        {"ssl_redirect": False},
        {"hsts_seconds": 300},
        {"session_cookie_secure": False},
        {"csrf_cookie_secure": False},
        {"csrf_trusted_origins": []},
        {"csrf_trusted_origins": ["http://docs.example.com"]},
        {"csrf_trusted_origins": ["https://docs.example.com/path"]},
    ],
)
def test_insecure_production_security_configuration_is_rejected(changes):
    with pytest.raises(ImproperlyConfigured, match="production security"):
        validate_production_security(**{**VALID_SECURITY_CONFIGURATION, **changes})
