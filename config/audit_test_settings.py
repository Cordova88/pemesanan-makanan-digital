"""Dummy-only settings for an externally isolated, offline regression runner.

Never import config.settings/v1_settings: both may load local credentials.
These settings separate test storage; they do not provide OS/network isolation.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

BASE_DIR = Path(__file__).resolve().parent.parent
_scratch = TemporaryDirectory(prefix='rasakita-audit-tests-')
SECRET_KEY = 'dummy-test-key-for-isolated-regressions-only-never-for-deployment'
DEBUG = False
ALLOWED_HOSTS = ['testserver']
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'menu', 'cart', 'orders', 'users', 'recommendation',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:',
    'TEST': {'NAME': ':memory:'},
}}
CACHES = {'default': {
    'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    'LOCATION': 'dummy-audit-tests',
}}
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
MEDIA_ROOT = Path(_scratch.name) / 'media'
MENU_ORIGINALS_ROOT = Path(_scratch.name) / 'originals'
MEDIA_URL = '/media/'
STATIC_URL = '/static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/staff/login/'
LANGUAGE_CODE = 'id'
TIME_ZONE = 'Asia/Makassar'
USE_TZ = True
GEMINI_ENABLED = False
GEMINI_API_KEY = ''
GEMINI_MODEL = 'dummy-model'
GEMINI_MAX_CALLS_PER_SESSION = 50
GEMINI_MAX_TOOL_ITERATIONS = 4
CHATBOT_REQUIRE_SHARED_CACHE = False
