"""Read aggregate guard reservations, never prompts, keys or user identifiers."""
import json
from django.core.management.base import BaseCommand
from recommendation.services.security import UsageGuard


class Command(BaseCommand):
    help = 'Show aggregate quota attempts, including denials; these are not provider billing.'

    def handle(self, *args: object, **options: object) -> None:
        self.stdout.write(json.dumps(UsageGuard().snapshot(), sort_keys=True))
