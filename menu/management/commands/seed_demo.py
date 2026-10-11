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
            "beef", "duck", "seafood", "shrimp", "fish", "egg", "tofu", "tempeh",
            "cheese", "rice", "noodle", "fried_rice", "fried_noodle", "soup", "boiled",
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
        food_samples = (
            ("Sate Ayam", "18000.00", ("chicken", "savory", "juicy", "sharing", "dinner")),
            ("Soto Ayam", "16000.00", ("chicken", "brothy", "warming", "rice", "lunch")),
            ("Bakso Sapi", "17000.00", ("beef", "brothy", "warming", "noodle", "comfort_food")),
            ("Rendang Sapi", "28000.00", ("beef", "savory", "rich", "rice", "heavy_meal")),
            ("Nasi Ayam Teriyaki", "22000.00", ("chicken", "rice", "sweet", "savory", "filling")),
            ("Nasi Uduk", "14000.00", ("rice", "savory", "comfort_food", "breakfast", "filling")),
            ("Nasi Kuning", "16000.00", ("rice", "savory", "comfort_food", "breakfast", "filling")),
            ("Soto Betawi", "24000.00", ("beef", "brothy", "rich", "warming", "rice")),
            ("Ikan Bakar", "26000.00", ("fish", "seafood", "savory", "juicy", "dinner")),
            ("Udang Saus Padang", "30000.00", ("shrimp", "seafood", "spicy", "saucy", "sharing")),
            ("Capcay Kuah", "18000.00", ("savory", "brothy", "light", "mild", "warming")),
            ("Tumis Kangkung", "12000.00", ("savory", "light", "mild", "quick_meal", "lunch")),
            ("Tempe Mendoan", "10000.00", ("tempeh", "snack", "soft", "savory", "sharing")),
            ("Pisang Goreng", "10000.00", ("dessert", "sweet", "crispy", "snack", "sharing")),
            ("Roti Bakar Cokelat", "14000.00", ("bread", "sweet", "dessert", "crispy", "snack")),
        )
        for name, price, item_tags in food_samples:
            menu(name, foods, price, item_tags)

        drink_samples = (
            ("Es Kopi Susu", "15000.00", ("drink", "sweet", "cold", "creamy", "refreshing")),
            ("Kopi Hitam", "10000.00", ("drink", "hot", "warming", "satisfying", "solo")),
            ("Teh Hangat", "5000.00", ("drink", "sweet", "warm", "refreshing", "solo")),
            ("Lemon Tea", "10000.00", ("drink", "sweet", "sour", "cold", "refreshing")),
            ("Jus Alpukat", "15000.00", ("drink", "sweet", "cold", "creamy", "refreshing")),
            ("Jus Mangga", "14000.00", ("drink", "sweet", "cold", "refreshing", "light")),
            ("Jus Jambu", "12000.00", ("drink", "sweet", "cold", "refreshing", "light")),
            ("Susu Cokelat", "12000.00", ("drink", "sweet", "cold", "creamy", "dessert")),
            ("Susu Jahe", "12000.00", ("drink", "sweet", "warm", "warming", "creamy")),
            ("Wedang Jahe", "10000.00", ("drink", "warm", "warming", "sweet", "hot")),
            ("Bandrek", "12000.00", ("drink", "warm", "warming", "sweet", "hot")),
            ("Es Cincau", "10000.00", ("drink", "sweet", "cold", "refreshing", "light")),
            ("Es Cendol", "12000.00", ("drink", "sweet", "cold", "creamy", "dessert")),
            ("Air Mineral", "4000.00", ("drink", "cold", "light", "refreshing", "solo")),
            ("Soda Gembira", "13000.00", ("drink", "sweet", "cold", "refreshing", "sharing")),
        )
        for name, price, item_tags in drink_samples:
            menu(name, drinks, price, item_tags)

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
