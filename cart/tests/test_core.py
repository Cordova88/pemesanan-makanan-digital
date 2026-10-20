import json
from decimal import Decimal

from django.test import TestCase

from menu.models import AddOn, Category, MenuItem, VariantGroup, VariantOption


class SessionCartApiTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Food")
        self.menu_item = MenuItem.objects.create(category=category, name="Nasi Goreng", price=Decimal("15000"))
        group = VariantGroup.objects.create(menu_item=self.menu_item, name="Size")
        self.large = VariantOption.objects.create(group=group, name="Large", price_adjustment=Decimal("4000"))
        self.cheese = AddOn.objects.create(name="Cheese", price=Decimal("5000"))
        self.cheese.menu_items.add(self.menu_item)

    def post(self, path, data):
        return self.client.post(path, data=json.dumps(data), content_type="application/json")

    def test_different_selections_are_separate_lines_and_prices_are_server_side(self):
        self.post("/api/cart/add/", {"menu_item_id": self.menu_item.id, "quantity": 1})
        response = self.post("/api/cart/add/", {"menu_item_id": self.menu_item.id, "quantity": 2, "variant_ids": [self.large.id], "addon_ids": [self.cheese.id], "price": 1})
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["total"], "63000.00")

    def test_checkout_uses_session_cart_then_clears_it_on_success(self):
        self.post("/api/cart/add/", {"menu_item_id": self.menu_item.id, "quantity": 1})
        response = self.post("/api/orders/checkout/", {"customer_name": "Ani", "order_type": "TAKEAWAY"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["total"], "15000.00")
        self.assertEqual(self.client.get("/api/cart/").json()["items"], [])

    def test_cart_is_retained_when_checkout_fails(self):
        self.post("/api/cart/add/", {"menu_item_id": self.menu_item.id, "quantity": 1})
        self.menu_item.is_available = False
        self.menu_item.save()
        self.assertEqual(self.post("/api/orders/checkout/", {"customer_name": "Ani", "order_type": "TAKEAWAY"}).status_code, 400)
        self.assertEqual(len(self.client.get("/api/cart/").json()["items"]), 1)
