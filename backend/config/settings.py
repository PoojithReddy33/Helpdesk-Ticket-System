"""
Django settings for the helpdesk backend.

Configuration that changes between machines (secrets, database credentials)
is read from a .env file that is never committed to git.
"""

from datetime import timedelta
from pathlib import Path

import environ

# backend/config/settings.py -> parent is config/, parent.parent is backend/
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY")

DEBUG = env("DEBUG")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])


# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "django_filters",
    "django_q",
]

LOCAL_APPS = [
    "accounts",
    "tickets",
    "notifications",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves static files in production without needing nginx. Must sit
    # directly below SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # CORS must sit above CommonMiddleware so its headers are attached even
    # when CommonMiddleware short-circuits the response.
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

# Most hosts inject a single DATABASE_URL. Fall back to the individual
# variables for local development.
if env("DATABASE_URL", default=None):
    DATABASES = {"default": env.db("DATABASE_URL")}
    DATABASES["default"]["OPTIONS"] = {
        "charset": "utf8mb4",
        "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
    }
else:
    DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME"),
            "USER": env("DB_USER"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": env("DB_HOST", default="127.0.0.1"),
            "PORT": env("DB_PORT", default="3306"),
            "OPTIONS": {
                # utf8mb4 is real 4-byte UTF-8. MySQL's "utf8" is only 3 bytes
                # and cannot store emoji.
                "charset": "utf8mb4",
                # Strict mode makes MySQL reject invalid data instead of
                # silently truncating it.
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------

# Points Django at our custom user model. Must be set before the first
# migration is applied.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------

REST_FRAMEWORK = {
    # How the API identifies the caller. JWT first for real clients;
    # session auth kept so the browsable API still works in development.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Endpoints require authentication unless a view opts out.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # Filtering, search, and ordering available on every list endpoint.
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
}


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------

SIMPLE_JWT = {
    # Short-lived: if an access token leaks, it expires quickly.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    # Long-lived: used only to obtain new access tokens.
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    # Each refresh issues a brand-new refresh token.
    "ROTATE_REFRESH_TOKENS": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "SIGNING_KEY": SECRET_KEY,
}


# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------

# Only these origins may call the API from a browser.
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5500", "http://127.0.0.1:5500"],
)


# --------------------------------------------------------------------------
# Internationalization
# --------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"

# Kept as UTC so the database never needs CONVERT_TZ (MySQL ships without
# timezone tables). The API serves UTC timestamps and the frontend converts
# them to each viewer's local time.
TIME_ZONE = "UTC"

USE_I18N = True

# Store all datetimes in the database as UTC; convert on display.
USE_TZ = True


# --------------------------------------------------------------------------
# Static files
# --------------------------------------------------------------------------

STATIC_URL = "static/"
# collectstatic gathers admin + DRF assets here for WhiteNoise to serve.
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        # Compresses files and adds a content hash to each name, so browsers
        # can cache them forever and still get the new version on deploy.
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# --------------------------------------------------------------------------
# Background tasks (django-q2)
# --------------------------------------------------------------------------

Q_CLUSTER = {
    "name": "helpdesk",
    # Worker processes. Each runs tasks independently.
    "workers": 2,
    # Give up on a task after this many seconds so one hung job cannot
    # occupy a worker forever.
    "timeout": 60,
    # Re-queue a task the worker never finished. Must exceed `timeout`,
    # or a still-running task gets duplicated.
    "retry": 120,
    "max_attempts": 3,
    # Keep the last N successful results for inspection in the admin.
    "save_limit": 250,
    # Poll the queue this often (seconds) when it is empty.
    "poll": 2,
    "catch_up": False,
    # Use the Django ORM as the broker - no Redis, no extra service.
    "orm": "default",
}


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------

# Development default: emails are printed to the terminal, not sent.
# Set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend in .env
# to send for real.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="helpdesk@example.com")

# Where the frontend lives, so emails can link back to a ticket.
FRONTEND_URL = env("FRONTEND_URL", default="http://127.0.0.1:5500")


# --------------------------------------------------------------------------
# Production hardening
# --------------------------------------------------------------------------

# Domains allowed to submit forms / POST to this site over HTTPS.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

if not DEBUG:
    # The host terminates TLS and forwards this header, so Django knows the
    # original request was HTTPS even though it arrives over HTTP internally.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

    # Cookies are sent only over HTTPS, so a network sniffer cannot read them.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # HSTS tells browsers to refuse plain HTTP for this domain for a year.
    # Start small (e.g. 3600) when first deploying - it is hard to undo.
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Stops browsers guessing a file's type, which can turn an upload into
    # executable content.
    SECURE_CONTENT_TYPE_NOSNIFF = True
