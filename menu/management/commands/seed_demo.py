from decimal import Decimal
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from menu.models import AddOn, Category, MenuItem, MenuTag, VariantGroup, VariantOption
from orders.models import Table
from recommendation.services.language import TAG_LABELS


class Command(BaseCommand):
    help = "Create development admin, cashier, and Indonesian menu sample data."

    def handle(self, *args, **kwargs):
        cashiers, _ = Group.objects.get_or_create(name="Cashier")
        admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={"is_staff": True, "is_superuser": True},
        )
        if not admin.has_usable_password():
            admin.set_password("admin12345")
            admin.save()
        cashier, _ = User.objects.get_or_create(username="cashier")
        if not cashier.has_usable_password():
            cashier.set_password("cashier12345")
            cashier.save()
        cashier.groups.add(cashiers)
        foods, _ = Category.objects.get_or_create(name="Makanan")
        drinks, _ = Category.objects.get_or_create(name="Minuman")

        tag_names = (
            "spicy", "very_spicy", "savory", "sweet", "sour", "salty",
            "umami", "rich", "mild", "crispy", "crunchy", "soft", "tender",
            "chewy", "creamy", "juicy", "saucy", "dry", "brothy", "chicken",
            "beef", "seafood", "shrimp", "fish", "egg", "tofu", "tempeh",
            "cheese", "rice", "noodle", "fried_rice", "fried_noodle", "soup",
            "bread", "heavy_meal", "light_meal", "snack", "dessert", "drink",
            "filling", "light", "comfort_food", "refreshing", "warming",
            "satisfying", "hot", "warm", "cold", "quick_meal", "late_night",
            "breakfast", "lunch", "dinner", "sharing", "solo",
        )
        tags = {}
        for name in tag_names:
            tag, _ = MenuTag.objects.update_or_create(
                name=name,
                defaults={"display_name": TAG_LABELS[name]},
            )
            tags[name] = tag

        def menu(name, category, price, item_tags, **defaults):
            item, _ = MenuItem.objects.get_or_create(
                name=name,
                category=category,
                defaults={"price": Decimal(price), **defaults},
            )
            item.tags.set([tags[tag] for tag in item_tags])
            return item

        nasi = menu(
            "Nasi Goreng",
            foods,
            "15000.00",
            ("rice", "fried_rice", "savory", "umami", "egg", "filling",
             "heavy_meal", "comfort_food", "quick_meal"),
            description="Nasi goreng spesial",
        )
        menu(
            "Ayam Geprek",
            foods,
            "15000.00",
            ("chicken", "rice", "spicy", "savory", "crispy", "filling",
             "heavy_meal", "comfort_food"),
        )
        menu(
            "Mie Goreng",
            foods,
            "14000.00",
            ("noodle", "fried_noodle", "savory", "umami", "filling",
             "heavy_meal", "comfort_food", "quick_meal", "egg"),
        )
        menu(
            "Mie Pedas",
            foods,
            "15000.00",
            ("noodle", "spicy", "savory", "filling", "heavy_meal",
             "quick_meal"),
        )
        menu(
            "Tahu Crispy",
            foods,
            "10000.00",
            ("tofu", "snack", "crispy", "crunchy", "savory", "light",
             "light_meal", "sharing"),
        )
        menu(
            "Es Teh",
            drinks,
            "5000.00",
            ("drink", "sweet", "cold", "refreshing", "light", "solo"),
        )
        menu(
            "Es Jeruk",
            drinks,
            "8000.00",
            ("drink", "sweet", "sour", "cold", "refreshing", "light", "solo"),
        )
        menu(
            "Ayam Geprek Mozzarella",
            foods,
            "20000.00",
            ("chicken", "rice", "spicy", "savory", "crispy", "cheese",
             "rich", "filling", "heavy_meal", "comfort_food"),
        )

        group, _ = VariantGroup.objects.get_or_create(
            menu_item=nasi,
            name="Ukuran",
            defaults={"is_required": True},
        )
        VariantOption.objects.get_or_create(
            group=group,
            name="Regular",
            defaults={"price_adjustment": 0},
        )
        VariantOption.objects.get_or_create(
            group=group,
            name="Large",
            defaults={"price_adjustment": Decimal("4000.00")},
        )
        for name, price in (("Extra Sambal", "3000.00"), ("Extra Cheese", "5000.00")):
            addon, _ = AddOn.objects.get_or_create(
                name=name,
                defaults={"price": Decimal(price)},
            )
            addon.menu_items.add(nasi)
        for number in ("01", "02", "03", "04", "05", "06", "07", "08"):
            Table.objects.get_or_create(number=number)
        self.stdout.write(
            self.style.SUCCESS(
                "Sample data ready. Credentials: admin/admin12345, "
                "cashier/cashier12345 (change them)."
            )
        )
