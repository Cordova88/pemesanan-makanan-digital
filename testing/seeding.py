"""Writes the showcase catalog, staff, tables and sample orders into the showcase database."""
import shutil
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from menu.models import AddOn, Category, MenuItem, MenuTag, VariantGroup, VariantOption
from orders import services as order_services
from orders.models import Order, Table
from recommendation.services.language import TAG_LABELS

from .catalog import ADDONS, CATEGORIES, MENU, TABLES, MenuSpec


class ShowcaseGuard:
    """Refuses to seed anything other than the throwaway database in testing/.data/."""

    @staticmethod
    def check() -> None:
        data_dir = Path(getattr(settings, "SHOWCASE_DATA_DIR", "")).resolve()
        database = Path(settings.DATABASES["default"]["NAME"]).resolve()
        media = Path(settings.MEDIA_ROOT).resolve()

        if not getattr(settings, "SHOWCASE_DATA_DIR", None) or data_dir not in database.parents or data_dir not in media.parents:
            raise ImproperlyConfigured(
                "seed_showcase only runs with --settings=testing.settings (database and media in testing/.data/)."
            )


class SvgLibrary:
    """Copies test SVGs into showcase media and returns their storage names.

    SVGs are placed directly instead of being uploaded, because MenuItem.save() sends new
    uploads through Pillow, which cannot read SVG. Only the URL is used when serving them.
    """

    folder = "menu/showcase"

    def __init__(self, source: Path, media_root: Path) -> None:
        self._source = source
        self._target = media_root / self.folder
        self._target.mkdir(parents=True, exist_ok=True)

    def place(self, filename: str) -> str:
        if not filename:
            return ""
        shutil.copyfile(self._source / filename, self._target / filename)
        return f"{self.folder}/{filename}"


@dataclass
class SeedReport:
    items: int = 0
    orders: int = 0


class CatalogSeeder:
    """Creates categories, tags, add-ons and menu items (idempotent by name)."""

    def __init__(self, images: SvgLibrary) -> None:
        self._images = images
        self._categories: dict[str, Category] = {}
        self._addons: dict[str, AddOn] = {}
        self._tags: dict[str, MenuTag] = {}

    def run(self, report: SeedReport) -> None:
        self._categories = {name: Category.objects.get_or_create(name=name)[0] for name in CATEGORIES}
        self._addons = {
            name: AddOn.objects.update_or_create(name=name, defaults={"price": Decimal(price)})[0]
            for name, price in ADDONS.items()
        }
        needed = {tag for spec in MENU for tag in spec.tags}
        self._tags = {
            name: MenuTag.objects.update_or_create(name=name, defaults={"display_name": TAG_LABELS[name]})[0]
            for name in needed
        }
        for spec in MENU:
            self._item(spec)
            report.items += 1

    def _item(self, spec: MenuSpec) -> MenuItem:
        item, _ = MenuItem.objects.update_or_create(
            name=spec.name,
            category=self._categories[spec.category],
            defaults={
                "price": Decimal(spec.price),
                "description": spec.description,
                "is_available": spec.available,
            },
        )
        image = self._images.place(spec.svg)
        if item.image.name != image:
            # Assigning a stored name (not a file) skips the upload pipeline in MenuItem.save().
            item.image.name = image
            item.save(update_fields=["image", "updated_at"])
        item.tags.set([self._tags[tag] for tag in spec.tags])
        for addon in spec.addons:
            self._addons[addon].menu_items.add(item)
        for order, variant in enumerate(spec.variants):
            group, _ = VariantGroup.objects.update_or_create(
                menu_item=item, name=variant.name,
                defaults={"is_required": variant.required, "display_order": order},
            )
            for position, (option, adjustment) in enumerate(variant.options):
                VariantOption.objects.update_or_create(
                    group=group, name=option,
                    defaults={"price_adjustment": Decimal(adjustment), "display_order": position},
                )
        return item


class StaffSeeder:
    """Same development accounts as seed_demo: admin/admin12345 and cashier/cashier12345."""

    def run(self) -> tuple[User, User]:
        admin = self._user("admin", "admin12345", is_staff=True, is_superuser=True)
        cashier = self._user("cashier", "cashier12345")
        cashier.groups.add(Group.objects.get_or_create(name="Cashier")[0])
        return admin, cashier

    @staticmethod
    def _user(username: str, password: str, **flags: bool) -> User:
        user, created = User.objects.get_or_create(username=username, defaults=flags)
        if created or not user.has_usable_password():
            user.set_password(password)
            user.save()
        return user


class OrderSeeder:
    """Creates orders in every status through orders/services.py, so totals and audit logs are real."""

    def __init__(self, admin: User, cashier: User) -> None:
        self._admin = admin
        self._cashier = cashier

    def run(self, report: SeedReport) -> None:
        if Order.objects.exists():
            return  # keep whatever was made by hand in an earlier session
        tables = [Table.objects.get_or_create(number=number)[0] for number in TABLES]
        menu = {item.name: item for item in MenuItem.objects.prefetch_related("variant_groups__options")}

        def line(name: str, quantity: int = 1, addons: tuple[str, ...] = ()) -> dict:
            item = menu[name]
            variants = [group.options.order_by("display_order").first().id
                        for group in item.variant_groups.all() if group.is_required]
            addon_ids = list(AddOn.objects.filter(name__in=addons).values_list("id", flat=True))
            return {"menu_item_id": item.id, "quantity": quantity, "variant_ids": variants, "addon_ids": addon_ids}

        def order(customer: str, items: list[dict], table: Table | None = None, note: str = "") -> Order:
            report.orders += 1
            return order_services.create_order({
                "customer_name": customer,
                "order_type": Order.OrderType.DINE_IN if table else Order.OrderType.TAKEAWAY,
                "table_token": table.token if table else "",
                "note": note,
                "items": items,
            })

        # Waiting at the cashier.
        order("Budi", [line("Nasi Goreng Spesial", 2, ("Telur ceplok",)), line("Es Teh Manis", 2)], tables[0])
        order("Sari", [line("Soto Ayam Lamongan"), line("Es Jeruk Peras")], note="Kuah dipisah")
        order("Meja keluarga", [line("Sate Ayam Madura", 3), line("Gado-Gado", 2), line("Es Campur", 4)], tables[3])

        # Paid (cash and QRIS).
        paid = order("Andi", [line("Ayam Bakar Madu", 1, ("Nasi tambahan",)), line("Kopi Susu Gula Aren")], tables[1])
        order_services.pay(paid.public_id, self._cashier, "CASH", amount_received=Decimal("100000"))
        qris = order("Dewi", [line("Mie Goreng Jawa"), line("Pisang Goreng Keju", 1, ("Keju parut",))])
        order_services.pay(qris.public_id, self._cashier, "QRIS", external_reference="SHOWCASE-QRIS-001")

        # Cancelled, refunded, expired.
        cancelled = order("Rina", [line("Es Teh Manis")])
        order_services.cancel(cancelled.public_id, self._cashier)
        refunded = order("Tono", [line("Ayam Bakar Madu")], tables[2])
        order_services.pay(refunded.public_id, self._cashier, "CASH", amount_received=Decimal("50000"))
        order_services.refund(refunded.public_id, self._admin)
        expired = order("Pelanggan lama", [line("Gado-Gado")])
        Order.objects.filter(pk=expired.pk).update(expires_at=timezone.now() - timedelta(minutes=5))
        order_services.expire_order_if_due(expired.public_id)


class ShowcaseSeeder:
    """Entry point used by the seed_showcase command."""

    def run(self, with_orders: bool = True) -> SeedReport:
        ShowcaseGuard.check()
        report = SeedReport()
        admin, cashier = StaffSeeder().run()
        CatalogSeeder(SvgLibrary(Path(settings.SHOWCASE_SVG_DIR), Path(settings.MEDIA_ROOT))).run(report)
        if with_orders:
            OrderSeeder(admin, cashier).run(report)
        return report
