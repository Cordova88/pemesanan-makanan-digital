from django.apps import AppConfig


class ShowcaseConfig(AppConfig):
    """Registers the showcase seeder; only installed by testing/settings.py."""

    name = "testing"
    label = "showcase"
    verbose_name = "RasaKita showcase (testing only)"
