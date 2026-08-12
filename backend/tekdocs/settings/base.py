from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from tekdocs.version import VERSION

from .secret_files import read_secret
from .validation import oidc_provider_from_environment

BASE_DIR = Path(__file__).resolve().parents[2]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer") from exc


SECRET_KEY = read_secret("DJANGO_SECRET_KEY", default="development-only-not-for-production")
TEKDOCS_MASTER_KEY = read_secret("TEKDOCS_MASTER_KEY")
TEKDOCS_PUBLICATION_SIGNING_KEY = read_secret("TEKDOCS_PUBLICATION_SIGNING_KEY")
TEKDOCS_BOOTSTRAP_TOKEN = read_secret("TEKDOCS_BOOTSTRAP_TOKEN")
TEKDOCS_DATABASE_ROLE = os.getenv("TEKDOCS_DATABASE_ROLE", "runtime")
TEKDOCS_DATABASE_RUNTIME_ROLE = os.getenv("TEKDOCS_DATABASE_RUNTIME_ROLE", "tekdocs_runtime")
TEKDOCS_DATABASE_RUNTIME_PASSWORD = read_secret("TEKDOCS_DATABASE_RUNTIME_PASSWORD")
TEKDOCS_PUBLIC_URL = os.getenv("TEKDOCS_PUBLIC_URL", "http://localhost:3200").rstrip("/")
TEKDOCS_ALLOW_INSECURE_PUBLIC_URL = env_bool("TEKDOCS_ALLOW_INSECURE_PUBLIC_URL", False)
INVITATION_TTL_HOURS = env_int("INVITATION_TTL_HOURS", 168)
if not 1 <= INVITATION_TTL_HOURS <= 2160:
    raise ImproperlyConfigured("INVITATION_TTL_HOURS must be between 1 and 2160")
PASSWORD_RESET_TIMEOUT = env_int("PASSWORD_RESET_TIMEOUT_SECONDS", 3600)
if not 300 <= PASSWORD_RESET_TIMEOUT <= 86400:
    raise ImproperlyConfigured("PASSWORD_RESET_TIMEOUT_SECONDS must be between 300 and 86400")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
_oidc_environment = dict(os.environ)
_oidc_environment["TEKDOCS_OIDC_CLIENT_SECRET"] = read_secret("TEKDOCS_OIDC_CLIENT_SECRET")
TEKDOCS_OIDC_PROVIDER = oidc_provider_from_environment(_oidc_environment)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "rest_framework",
    "drf_spectacular",
    "allauth",
    "allauth.account",
    "allauth.headless",
    "allauth.mfa",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.openid_connect",
    "allauth.usersessions",
    "apps.accounts",
    "apps.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "allauth.usersessions.middleware.UserSessionsMiddleware",
    "apps.core.middleware.RLSRequestScopeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestContextMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "tekdocs.urls"
WSGI_APPLICATION = "tekdocs.wsgi.application"
ASGI_APPLICATION = "tekdocs.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "tekdocs"),
        "USER": os.getenv("POSTGRES_USER", "tekdocs"),
        "PASSWORD": read_secret("POSTGRES_PASSWORD"),
        "HOST": os.getenv("POSTGRES_HOST", "db"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 5},
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("DJANGO_CACHE_URL", "redis://valkey:6379/2"),
    }
}

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SITE_ID = 1
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*", "display_name*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_ADAPTER = "apps.accounts.adapters.InviteOnlyAccountAdapter"
ACCOUNT_LOGIN_ON_PASSWORD_RESET = False
ACCOUNT_REAUTHENTICATION_TIMEOUT = 300
ACCOUNT_RATE_LIMITS = {
    "login": "20/m/ip",
    "login_failed": "10/m/ip,5/10m/key",
    "reset_password": "10/h/ip,3/h/key",
    "reset_password_from_key": "10/h/ip",
}
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_STORE_TOKENS = False
SOCIALACCOUNT_PROVIDERS = {}
if TEKDOCS_OIDC_PROVIDER:
    SOCIALACCOUNT_PROVIDERS = {
        "openid_connect": {
            "APPS": [
                {
                    "provider_id": TEKDOCS_OIDC_PROVIDER["id"],
                    "name": TEKDOCS_OIDC_PROVIDER["name"],
                    "client_id": TEKDOCS_OIDC_PROVIDER["client_id"],
                    "secret": TEKDOCS_OIDC_PROVIDER["client_secret"],
                    "settings": {
                        "server_url": TEKDOCS_OIDC_PROVIDER["discovery_url"],
                        "email_authentication": True,
                        "email_authentication_auto_connect": True,
                    },
                }
            ]
        }
    }
HEADLESS_ONLY = True
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": "/auth/verify-email/{key}",
    "account_reset_password": "/auth/reset-password",
    "account_reset_password_from_key": "/auth/reset-password/{key}",
    "account_signup": "/auth/register",
    "socialaccount_login_error": "/",
}
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes", "webauthn"]
MFA_ADAPTER = "apps.accounts.adapters.EncryptedMFAAdapter"
MFA_RECOVERY_CODES_SHOW_ONCE = True
MFA_TOTP_ISSUER = "TekDocs"
MFA_PASSKEY_LOGIN_ENABLED = True
MFA_PASSKEY_SIGNUP_ENABLED = False
USERSESSIONS_ADAPTER = "apps.accounts.adapters.AuditedUserSessionsAdapter"
USERSESSIONS_TRACK_ACTIVITY = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "TekDocs API",
    "DESCRIPTION": "Self-hosted MSP knowledge and inventory API",
    "VERSION": VERSION,
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "ENUM_NAME_OVERRIDES": {
        "OrganizationKindEnum": "apps.core.models.OrganizationKind",
        "PersonAssociationKindEnum": "apps.core.models.PersonAssociationKind",
        "LocationKindEnum": "apps.core.models.LocationKind",
        "EntityLinkTypeEnum": "apps.core.models.EntityLinkType",
        "BuiltInRoleEnum": "apps.accounts.models.BuiltInRole",
        "TenantAssignableRoleEnum": "apps.accounts.models.TENANT_ASSIGNABLE_ROLE_CHOICES",
        "CustomRoleScopeEnum": "apps.accounts.models.CustomRoleScope",
        "OrganizationAccessModeEnum": "apps.core.models.OrganizationAccessMode",
        "CatalogProductKindEnum": "apps.core.models.CatalogProductKind",
        "CatalogModelLifecycleEnum": "apps.core.models.CatalogModelLifecycle",
    },
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TZ", "America/Chicago")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "TekDocs <noreply@localhost>")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = read_secret("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)
TEKDOCS_ALLOW_INSECURE_SMTP = env_bool("TEKDOCS_ALLOW_INSECURE_SMTP", False)

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://valkey:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://valkey:6379/1")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    "dispatch-transactional-outbox": {
        "task": "apps.core.tasks.dispatch_outbox_events",
        "schedule": 60.0,
    },
    "dispatch-notification-emails": {
        "task": "apps.core.tasks.dispatch_notification_emails",
        "schedule": 60.0,
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": '{{"time":"{asctime}","level":"{levelname}","logger":"{name}","message":"{message}"}}',
            "style": "{",
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "structured"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}
