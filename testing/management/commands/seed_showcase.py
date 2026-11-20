from django.core.management.base import BaseCommand

from testing.seeding import ShowcaseSeeder


class Command(BaseCommand):
    help = "Fill the showcase database (testing/.data/) with menu, SVG photos, tables, staff and sample orders."

    def add_arguments(self, parser):
        parser.add_argument("--no-orders", action="store_true", help="Seed the catalog only.")

    def handle(self, *args: object, **options: object) -> None:
        report = ShowcaseSeeder().run(with_orders=not options["no_orders"])
        self.stdout.write(self.style.SUCCESS(f"Showcase ready: {report.items} menu items, {report.orders} orders."))
