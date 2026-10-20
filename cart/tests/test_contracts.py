from decimal import Decimal

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import TestCase

from menu.models import Category, MenuItem, VariantGroup, VariantOption
from ..services import CartService


class CartIsolationTests(TestCase):
    def setUp(self) -> None:
        category = Category.objects.create(name="Food")
        self.item = MenuItem.objects.create(category=category, name="Rice", price=Decimal("10.50"))
        group = VariantGroup.objects.create(menu_item=self.item, name="Size")
        self.option = VariantOption.objects.create(group=group, name="Large", price_adjustment=Decimal("2.25"))
        self.session = SessionStore()
        self.cart = CartService(self.session)

    def test_returned_line_and_checkout_lists_cannot_mutate_saved_cart(self) -> None:
        line = self.cart.add_item(self.item.pk, 2, [self.option.pk])
        line["quantity"] = 99
        line["variant_ids"].clear()
        checkout = self.cart.checkout_items()
        self.assertEqual(checkout[0]["quantity"], 2)
        self.assertEqual(checkout[0]["variant_ids"], [self.option.pk])
        checkout[0]["variant_ids"].clear()
        self.assertEqual(self.cart.checkout_items()[0]["variant_ids"], [self.option.pk])
        self.assertEqual(self.session["cart"][0]["quantity"], 2)
        self.assertEqual(self.cart.get_total(), Decimal("25.50"))

    def test_rendered_and_updated_lines_are_snapshots(self) -> None:
        line = self.cart.add_item(self.item.pk, 1, [self.option.pk])
        updated = self.cart.update_quantity(line["id"], 2)
        updated["quantity"] = 99
        rendered = self.cart.get_items()
        rendered[0]["variant_ids"].clear()
        self.assertEqual(self.cart.checkout_items()[0]["quantity"], 2)
        self.assertEqual(CartService(self.session).checkout_items()[0]["variant_ids"], [self.option.pk])
