from pathlib import Path

import environ

from .infrastructure import database_config, media_storage_config

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(env("DJANGO_ENV_FILE", default=str(BASE_DIR / ".env")))
if env("PAYMENTS_ENV_FILE", default=""):
    environ.Env.read_env(env("PAYMENTS_ENV_FILE"))
SECRET_KEY = env("DJANGO_SECRET_KEY")
DOCUMENT_DATA_ENCRYPTION_KEYS = env.list("DOCUMENT_DATA_ENCRYPTION_KEYS", default=[])
DEBUG = env("DEBUG")
GUEST_AUTH_DEMO_OTP = env.bool("GUEST_AUTH_DEMO_OTP", default=False)
GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION = env.bool(
    "GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION", default=False
)
BOOKING_HOLD_MINUTES = env.int("BOOKING_HOLD_MINUTES", default=15)
PAYMENTS_SCHEDULER_SECRET = env("PAYMENTS_SCHEDULER_SECRET", default="")
PAYMENTS_INLINE_CHECKOUT = env.bool("PAYMENTS_INLINE_CHECKOUT", default=False)
PAYMENT_PROVIDER = env("PAYMENT_PROVIDER", default="simulator")
XPAYMENT_ENABLED = env.bool("XPAYMENT_ENABLED", default=False)
XPAYMENT_PROTOCOL_VERIFIED = env.bool("XPAYMENT_PROTOCOL_VERIFIED", default=False)
XPAYMENT_SANDBOX_PROTOCOL_VERIFIED = env.bool("XPAYMENT_SANDBOX_PROTOCOL_VERIFIED", default=False)
XPAYMENT_API_KEY = env("XPAYMENT_API_KEY", default="")
XPAYMENT_API_VERSION = env("XPAYMENT_API_VERSION", default="v1")
XPAYMENT_ENV = env("XPAYMENT_ENV", default="production")
XPAYMENT_DEVICE_NAME = env("XPAYMENT_DEVICE_NAME", default="")
XPAYMENT_PRODUCTION_RESORT_IDS = env.list("XPAYMENT_PRODUCTION_RESORT_IDS", default=[])
XPAYMENT_ACCOUNT_ID = env("XPAYMENT_ACCOUNT_ID", default="")
XPAYMENT_WEBHOOK_SECRET = env("XPAYMENT_WEBHOOK_SECRET", default="")
PAYMENTS_ALLOW_SIMULATOR = env.bool("PAYMENTS_ALLOW_SIMULATOR", default=DEBUG)
HALYK_EPAY_ENV = env("HALYK_EPAY_ENV", default="sandbox")
HALYK_EPAY_PROTOCOL_VERIFIED = env.bool("HALYK_EPAY_PROTOCOL_VERIFIED", default=False)
HALYK_EPAY_CLIENT_ID = env("HALYK_EPAY_CLIENT_ID", default="")
HALYK_EPAY_CLIENT_SECRET = env("HALYK_EPAY_CLIENT_SECRET", default="")
HALYK_EPAY_SHOP_ID = env("HALYK_EPAY_SHOP_ID", default="")
HALYK_EPAY_TERMINAL_ID = env("HALYK_EPAY_TERMINAL_ID", default="")
HALYK_EPAY_INVOICE_USERNAME = env("HALYK_EPAY_INVOICE_USERNAME", default="")
HALYK_EPAY_INVOICE_PASSWORD = env("HALYK_EPAY_INVOICE_PASSWORD", default="")
HALYK_EPAY_LOOKUP_GRANT = env("HALYK_EPAY_LOOKUP_GRANT", default="password")
HALYK_EPAY_INVOICE_PREFIX = env("HALYK_EPAY_INVOICE_PREFIX", default="")
HALYK_EPAY_INVOICE_START = env.int("HALYK_EPAY_INVOICE_START", default=100000)
HALYK_EPAY_INVOICE_END = env.int("HALYK_EPAY_INVOICE_END", default=999999)
PAYMENTS_PUBLIC_API_ORIGIN = env("PAYMENTS_PUBLIC_API_ORIGIN", default="")
PAYMENTS_PUBLIC_SITE_ORIGIN = env("PAYMENTS_PUBLIC_SITE_ORIGIN", default="")
PAYMENTS_PUBLIC_STAFF_ORIGIN = env("PAYMENTS_PUBLIC_STAFF_ORIGIN", default="")
if not 1 <= BOOKING_HOLD_MINUTES <= 120:
    raise ValueError("BOOKING_HOLD_MINUTES must be between 1 and 120")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "booking",
    "commerce",
    "identity",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": database_config(env)}
AUTH_USER_MODEL = "booking.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "booking.authentication.NativeBearerAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "booking.errors.exception_handler",
}
LANGUAGE_CODE = "ru"
TIME_ZONE = "Asia/Almaty"
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "private-media"
LEGACY_MEDIA_ROOT = BASE_DIR / "mediafiles"
MEDIA_STORAGE = env("MEDIA_STORAGE", default="local")
MEDIA_UPLOAD_MAX_BYTES = env.int("MEDIA_UPLOAD_MAX_BYTES", default=0)
MEDIA_GUEST_DAILY_BYTES = env.int("MEDIA_GUEST_DAILY_BYTES", default=50 * 1024 * 1024)
MEDIA_RESORT_DAILY_BYTES = env.int("MEDIA_RESORT_DAILY_BYTES", default=500 * 1024 * 1024)
STAFF_WORKSPACE_URL = env("STAFF_WORKSPACE_URL", default="http://127.0.0.1:4173/staff")
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_HANDLERS = [
    "booking.upload_handlers.BoundedUploadHandler",
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]
STORAGES = {
    "default": media_storage_config(env),
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_SAVE_EVERY_REQUEST = True
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if env.bool("TRUST_PROXY", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
