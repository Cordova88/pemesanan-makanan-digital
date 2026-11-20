"""Showcase settings: the normal local app, but on a throwaway database and media folder.

Run through testing/run.ps1. Everything this mode writes lives in testing/.data/,
so the real db.sqlite3 and media/ are never touched.
"""
from pathlib import Path

from v1_settings import *  # noqa: F401,F403
from v1_settings import INSTALLED_APPS

SHOWCASE_DIR = Path(__file__).resolve().parent
SHOWCASE_DATA_DIR = SHOWCASE_DIR / ".data"
SHOWCASE_SVG_DIR = SHOWCASE_DIR / "svg"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SHOWCASE_DATA_DIR / "showcase.sqlite3",
    }
}
MEDIA_ROOT = SHOWCASE_DATA_DIR / "media"
INSTALLED_APPS = [*INSTALLED_APPS, "testing.apps.ShowcaseConfig"]

# Cookies are shared across ports on localhost; keep showcase sessions separate.
SESSION_COOKIE_NAME = "rasakita_showcase_session"
CSRF_COOKIE_NAME = "rasakita_showcase_csrftoken"
