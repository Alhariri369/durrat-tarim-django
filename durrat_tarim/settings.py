from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or os.getenv("JWT_SECRET")
DEBUG = os.getenv("DJANGO_DEBUG","False") == "True"
ALLOWED_HOSTS = [
    ".vercel.app"
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "catalog",
    "support",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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

if all(os.getenv(key) for key in ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_SERVER", "POSTGRES_DB"]):
    DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("POSTGRES_SERVER"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "OPTIONS": {
            "sslmode": os.getenv("POSTGRES_SSLMODE", "prefer"),
        },
        "CONN_MAX_AGE": 60,  # الحد من الاتصالات الخاملة (بالثواني)
        "DISABLE_SERVER_SIDE_CURSORS": True,  # هام جداً مع PgBouncer transaction mode
        }
    }
# else:
#     DATABASES = {
#         "default": {
#             "ENGINE": "django.db.backends.sqlite3",
#             "NAME": BASE_DIR / "db.sqlite3",
#         }
#     }

AUTH_USER_MODEL = "accounts.User"

LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Riyadh"
USE_I18N = True
USE_TZ = True

STATIC_ROOT = BASE_DIR/ "staticfiles"
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/uploads/"
MEDIA_ROOT = ROOT_DIR / "uploads"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/auth/login"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
