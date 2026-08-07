from .base import *  # noqa: F403

DEBUG = True
SECRET_KEY = "development-only-not-for-production"
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
