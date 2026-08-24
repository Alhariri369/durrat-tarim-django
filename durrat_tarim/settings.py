import os
from pathlib import Path

import dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
print(BASE_DIR)
dotenv.load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set")

DEBUG = os.getenv("DJANGO_DEBUG", "False") == "True"
ALLOWED_HOSTS = [".vercel.app", "127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "accounts",
    "catalog",
    "dashboard",
    "support",
]

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
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
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "durrat_tarim.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "durrat_tarim.context_processors.site_context",
            ],
        },
    },
]

WSGI_APPLICATION = "durrat_tarim.wsgi.application"

USE_REMOTE_DB = os.getenv("USE_REMOTE_DB", "False") == "True"
if USE_REMOTE_DB and all(
    os.getenv(key)
    for key in ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_DB"]
):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB"),
            "USER": os.getenv("POSTGRES_USER"),
            "HOST": os.getenv("POSTGRES_HOST"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 300,
            "CONN_HEALTH_CHECKS": True,
            "DISABLE_SERVER_SIDE_CURSORS": True,
            "OPTIONS": {
                "keepalives": 1,
                "keepalives_idle": 20,
                "keepalives_interval": 10,
                "keepalives_count": 3,
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# old stuff
# DEFAULT_FILE_STORAGE = "storages.backends.s3.S3Storage"
# AWS_S3_ENDPOINT_URL = os.getenv("SUPABASE_S3_URL")  # from Supabase dashboard
# AWS_ACCESS_KEY_ID = os.getenv("SUPABASE_S3_KEY")
# AWS_SECRET_ACCESS_KEY = os.getenv("SUPABASE_S3_SECRET")
# AWS_STORAGE_BUCKET_NAME = "product-images"


# new stuff: Media storage (ImageKit) 
# Server-side auth needs only the private key; the public key is only for
# client-side uploads, which this project doesn't use.
IMAGEKIT_PRIVATE_KEY = os.getenv("IMAGEKIT_PRIVATE_KEY", "")
IMAGEKIT_URL_ENDPOINT = os.getenv("IMAGEKIT_URL_ENDPOINT", "")  # e.g. https://ik.imagekit.io/your_id

STORAGES = {
    "default": {
        "BACKEND": "catalog.imagekit_storage.ImageKitStorage",
    }
    if (IMAGEKIT_PRIVATE_KEY and IMAGEKIT_URL_ENDPOINT)
    else {
        # Local development fallback: MEDIA_ROOT (uploads/)
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# ---------- Email ----------

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_SENDER = os.getenv("RESEND_SENDER", "noreply@durrat-tarim.com")
RESEND_TIMEOUT = int(os.getenv("RESEND_TIMEOUT", "10"))

if os.getenv("DJANGO_EMAIL_BACKEND"):
    EMAIL_BACKEND = os.getenv("DJANGO_EMAIL_BACKEND")
elif DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "durrat_tarim.email_backend.ResendEmailBackend"

DEFAULT_FROM_EMAIL = RESEND_SENDER

# ---------- django-allauth ----------

ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = False
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 3
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_PREVENT_ENUMERATION = True
ACCOUNT_RATE_LIMITS = {"login_failed": "5/300s"}
ACCOUNT_ADAPTER = "accounts.adapter.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "accounts.adapter.SocialAccountAdapter"

# ---------- Social authentication (Google) ----------

_google_apps = None
if os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"):
    _google_apps = [
        {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "key": "",
        }
    ]

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    }
}
if _google_apps:
    SOCIALACCOUNT_PROVIDERS["google"]["APPS"] = _google_apps

# One-click redirect to Google (no intermediate confirmation page)
SOCIALACCOUNT_LOGIN_ON_GET = True
# Log into an existing account when the Google email already matches one
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

# Vercel terminates TLS at the proxy — detect https from the forwarded header
if os.getenv("VERCEL"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

# ---------- Password validation ----------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------- i18n ----------

LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Riyadh"
USE_I18N = True
USE_TZ = True

# ---------- Static & Media ----------

# STATIC_ROOT = BASE_DIR / "static"
# STATIC_URL = "/static/"
# STATICFILES_DIRS = []
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": os.getenv(
                "SUPABASE_S3_BUCKET", os.getenv("AWS_STORAGE_BUCKET_NAME", "products")
            ),
            "endpoint_url": os.getenv(
                "SUPABASE_S3_ENDPOINT", os.getenv("AWS_S3_ENDPOINT_URL")
            ),
            "access_key": os.getenv(
                "SUPABASE_S3_ACCESS_KEY", os.getenv("AWS_ACCESS_KEY_ID")
            ),
            "secret_key": os.getenv(
                "SUPABASE_S3_SECRET_KEY", os.getenv("AWS_SECRET_ACCESS_KEY")
            ),
            "default_acl": "public-read",
            "file_overwrite": False,
            "custom_domain": os.getenv("SUPABASE_PUBLIC_URL"),
        },
    }
    if (os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("SUPABASE_S3_ACCESS_KEY"))
    else {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

WHITENOISE_USE_FINDERS = True

# AWS_QUERYSTRING_AUTH = False  # no signed URLs — bucket must be public

MEDIA_URL = os.getenv("MEDIA_URL", "/uploads/")
MEDIA_ROOT = Path(
    os.getenv(
        "MEDIA_ROOT",
        "/tmp/uploads" if os.getenv("VERCEL") else BASE_DIR / "uploads",
    )
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
