from decimal import Decimal

from django.test import TestCase

from .models import Category, MenuItem


class StorefrontTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Makanan")
        MenuItem.objects.create(category=category, name="Nasi Goreng", price=Decimal("15000"))

    def test_storefront_is_available(self):
        response = self.client.get("/")
        self.assertTemplateUsed(response, "menu/storefront.html")
        self.assertContains(response, "/static/menu/css/storefront.css")
        self.assertContains(response, "/static/menu/js/storefront.mjs")

    def test_menu_api_exposes_selection_data(self):
        response = self.client.get("/api/menu/")
        item = response.json()["items"][0]
        self.assertEqual(item["name"], "Nasi Goreng")
        self.assertIn("variants", item)
        self.assertIn("addons", item)
