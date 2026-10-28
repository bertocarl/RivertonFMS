import os
from pathlib import Path
from celery import Celery

# Set default Django settings module for 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bonje_fms.settings')  # ⚠️ Replace with your actual project directory folder name

app = Celery('bonje_fms')

# Load settings from Django settings using the 'CELERY_' prefix namespace.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs (picks up reports/tasks.py).
app.autodiscover_tasks()

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=""):
    return os.environ.get(name, default)


SECRET_KEY = env("DJANGO_SECRET_KEY", "totalenergies-fms-bonje-riverton")
DEBUG = env("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o]

#KRA Etims

KRA_ETIMS_BASE_URL = os.environ.get(
    "KRA_ETIMS_BASE_URL", "https://etims-sbx.kra.go.ke/etims-oscu/v1.0"
)
KRA_TAXPAYER_PIN = os.environ.get("KRA_TAXPAYER_PIN")
KRA_BRANCH_CODE = os.environ.get("KRA_BRANCH_CODE", "00")
KRA_DEVICE_SERIAL = os.environ.get("KRA_DEVICE_SERIAL")
KRA_CMC_KEY = os.environ.get("KRA_CMC_KEY")

# --- Redis Host Configuration ---
REDIS_HOST = os.environ.get('REDIS_HOST', '127.0.0.1')
REDIS_PORT = os.environ.get('REDIS_PORT', '6379')
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

# --- Celery Configuration ---
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Africa/Nairobi'  # Set to Kenya Time

# --- Django Cache Configuration (Optimizes HTMX/AJAX Dashboard Polling) ---
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/1",  # Database 1 for cache, 0 for Celery
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "common",
    "accounts",
    "forecourt",
    "shifts",
    "sales",
    "purchases",
    "ledger",
    "reports",
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
                "common.context.shell",
            ],
        },
    },
]

if env("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME"),
            "USER": env("DB_USER", "bonje"),
            "PASSWORD": env("DB_PASSWORD", "bonje"),
            "HOST": env("DB_HOST", "localhost"),
            "PORT": env("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "forecourt:dashboard"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Business settings
CURRENCY = "KES"
STATION_BACKUP_DIR = BASE_DIR / "backups"
IFSF_API_TOKEN = env("IFSF_API_TOKEN", "change-me-ifsf-token")
REPORT_ROWS_PER_PAGE = 20

# Celery / Redis. USE_CELERY=0 runs report tasks inline so Redis is optional.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_TASK_ALWAYS_EAGER = env("USE_CELERY", "0") != "1"
CELERY_TIMEZONE = TIME_ZONE

if not DEBUG:
    SESSION_COOKIE_SECURE = env("SECURE_COOKIES", "0") == "1"
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}