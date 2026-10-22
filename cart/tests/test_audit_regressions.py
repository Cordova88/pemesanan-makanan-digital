import json
from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.core.exceptions import ValidationError
from django.test import TestCase

from menu.models import Category, MenuItem
from ..services import CartService


class CartAuditRegressions(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Dummy category')
        self.item = MenuItem.objects.create(
            category=category, name='Dummy food', price=Decimal('10.50'),
        )
        self.session = SessionStore()
        self.cart = CartService(self.session)

    def test_add_rejects_out_of_policy_quantities_without_saving(self):
        for quantity in (True, False, 0, -1, 100, 1.5, '1'):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                self.cart.add_item(self.item.pk, quantity)
        self.assertEqual(self.cart.checkout_items(), [])
        self.assertNotIn('cart', self.session)

    def test_coalescing_cannot_exceed_99_or_mutate_the_cart_on_rejection(self):
        self.cart.add_item(self.item.pk, 98)
        self.cart.add_item(self.item.pk, 1)
        before = deepcopy(self.session['cart'])
        with self.assertRaises(ValidationError):
            self.cart.add_item(self.item.pk, 1)
        self.assertEqual(self.session['cart'], before)
        self.assertEqual(self.cart.checkout_items()[0]['quantity'], 99)
        # Distinct preparation notes still intentionally keep separate lines.
        self.cart.add_item(self.item.pk, 1, note='Dummy separate note')
        self.assertEqual(len(self.cart.checkout_items()), 2)

    def test_quantity_patch_and_selection_patch_use_same_policy(self):
        line = self.cart.add_item(self.item.pk, 1)
        for quantity in (True, False, 100, '2', 1.5):
            for update in (
                lambda: self.cart.update_quantity(line['id'], quantity),
                lambda: self.cart.update_selection(line['id'], {'quantity': quantity}),
            ):
                with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                    update()
                self.assertEqual(self.cart.checkout_items()[0]['quantity'], 1)
        self.cart.update_quantity(line['id'], 99)
        self.assertEqual(self.cart.checkout_items()[0]['quantity'], 99)
        self.cart.update_quantity(line['id'], 0)
        self.assertEqual(self.cart.checkout_items(), [])

    def test_detail_resolves_each_line_once_and_excludes_invalid_lines_from_total(self):
        lines = [
            {'id': 'dummy-a', 'valid': True, 'line_total': '21.00'},
            {'id': 'dummy-b', 'valid': False, 'line_total': '100.00'},
        ]
        with patch.object(CartService, 'get_items', return_value=lines) as resolve:
            response = self.client.get('/api/cart/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'items': lines, 'total': '21.00'})
        resolve.assert_called_once()

    def test_http_quantity_rejection_retains_existing_line(self):
        response = self.client.post('/api/cart/add/', json.dumps({
            'menu_item_id': self.item.pk, 'quantity': 99,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        line_id = response.json()['items'][0]['id']
        for data in ({'quantity': 100}, {'quantity': True}, {'quantity': 100, 'note': 'dummy'}):
            response = self.client.patch(
                f'/api/cart/{line_id}/', json.dumps(data), content_type='application/json',
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/cart/').json()['items'][0]['quantity'], 99)
