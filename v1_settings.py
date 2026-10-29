"""V1 local development profile. Production uses config.settings explicitly."""

from pathlib import Path
from secrets import token_urlsafe
import os
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / '.env')
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent
# Persist a local-only key so login sessions survive development restarts.
_key_path = BASE_DIR / '.local-secret-key'

if not os.environ.get('DJANGO_SECRET_KEY') and not _key_path.exists():
    try:
        with _key_path.open('x', encoding='utf-8') as key_file:
            key_file.write(token_urlsafe(48))
    except FileExistsError:
        pass

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or _key_path.read_text(encoding='utf-8').strip()
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "menu",
    "cart",
    "orders",
    "users",
    "recommendation",
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
            ]
        },
    }
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
LANGUAGE_CODE = "id"
TIME_ZONE = "Asia/Makassar"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/staff/login/"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_ENABLED = os.environ.get("GEMINI_ENABLED", "false").lower() == "true"
GEMINI_MAX_CALLS_PER_SESSION = int(os.environ.get("GEMINI_MAX_CALLS_PER_SESSION", "50"))
GEMINI_MAX_TOOL_ITERATIONS = int(os.environ.get("GEMINI_MAX_TOOL_ITERATIONS", "4"))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "recommendation.services.gemini": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


MENU_ORIGINALS_ROOT = BASE_DIR / 'private' / 'menu-originals'
SESSION_COOKIE_NAME = 'rasakita_v1_session'
