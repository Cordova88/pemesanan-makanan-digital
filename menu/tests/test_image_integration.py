import json
from types import SimpleNamespace

from django.test import TestCase

from menu.models import Category, MenuItem
from orders.services import create_order
from orders.views import _order
from recommendation.views import _item


class DynamicPhotoContractTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Makanan")
        self.item = MenuItem.objects.create(
            category=self.category, name="Sate Ayam", price=24000, image="menu/sate-first.webp"
        )

    def add_to_cart(self):
        response = self.client.post(
            "/api/cart/add/",
            json.dumps({"menu_item_id": self.item.pk, "quantity": 2, "note": "Pisahkan bumbu"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        return response.json()

    def test_new_menu_photo_is_consistent_without_name_mapping(self):
        catalog = self.client.get("/api/menu/").json()["items"][0]
        cart = self.add_to_cart()["items"][0]
        self.assertEqual(catalog["image_url"], self.item.image.url)
        self.assertEqual(cart["image_url"], catalog["image_url"])
        self.assertEqual(cart["menu_item_id"], self.item.pk)
        self.assertEqual(cart["note"], "Pisahkan bumbu")
        self.assertEqual(cart["line_total"], "48000.00")
        order = create_order(
            {
                "customer_name": "Uji",
                "order_type": "TAKEAWAY",
                "items": [{"menu_item_id": self.item.pk, "quantity": 2}],
            }
        )
        serialized = _order(order)["items"][0]
        self.assertEqual(serialized["image_url"], self.item.image.url)
        self.assertEqual(serialized["menu_item_id"], self.item.pk)
        self.assertEqual(serialized["line_total"], "48000.00")

    def test_cart_photo_resolves_even_when_item_leaves_catalog(self):
        self.add_to_cart()
        self.item.is_available = False
        self.item.save(update_fields=["is_available"])
        self.assertEqual(self.client.get("/api/menu/").json()["items"], [])
        line = self.client.get("/api/cart/").json()["items"][0]
        self.assertFalse(line["valid"])
        self.assertEqual(line["image_url"], self.item.image.url)

    def test_rename_and_replacement_use_current_url_and_preserve_order_snapshot(self):
        self.add_to_cart()
        order = create_order(
            {
                "customer_name": "Uji",
                "order_type": "TAKEAWAY",
                "items": [{"menu_item_id": self.item.pk, "quantity": 1}],
            }
        )
        self.item.image = "menu/sate-second.webp"
        self.item.name = "Sate Ayam Spesial"
        self.item.price = 30000
        self.item.save()
        self.assertEqual(
            self.client.get("/api/cart/").json()["items"][0]["image_url"], self.item.image.url
        )
        rendered = _order(order)["items"][0]
        self.assertEqual(rendered["name"], "Sate Ayam")
        self.assertEqual(rendered["line_total"], "24000.00")
        self.assertEqual(rendered["image_url"], self.item.image.url)

    def test_no_photo_is_empty_in_all_contracts(self):
        self.item.image = ""
        self.item.save(update_fields=["image"])
        self.assertEqual(self.client.get("/api/menu/").json()["items"][0]["image_url"], "")
        self.assertEqual(self.add_to_cart()["items"][0]["image_url"], "")

    def test_recommendation_only_adds_photo_contract(self):
        result = _item(SimpleNamespace(item=self.item, labels=[], match_reasons=[]))
        self.assertEqual(result["image_url"], self.item.image.url)
        self.assertEqual(result["id"], self.item.pk)

    def test_pages_load_shared_styles_and_photo_module(self):
        for url in ["/", "/chatbot/", "/orders/visual-demo/"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "menu/css/menu-card.css")
