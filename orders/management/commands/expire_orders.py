from django.core.management.base import BaseCommand
from orders.services import expire_pending_orders
class Command(BaseCommand):
    help = "Mark all expired pending orders as EXPIRED. Run every minute using a scheduler."
    def handle(self, *args, **options):
        expire_pending_orders()
        self.stdout.write(self.style.SUCCESS("Expired pending orders processed."))
