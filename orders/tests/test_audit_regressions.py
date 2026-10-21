from decimal import Decimal
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from menu.models import Category, MenuItem
from ..models import AuditLog, Order, OrderItem
from ..services import add_item, create_order


class CheckoutWorkRegressions(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Dummy category')
        self.item = MenuItem.objects.create(
            category=category, name='Dummy item', price=Decimal('10.50'),
        )

    def payload(self, count):
        return {
            'customer_name': 'Dummy customer', 'order_type': 'TAKEAWAY',
            'items': [{'menu_item_id': self.item.pk, 'quantity': 1} for _ in range(count)],
        }

    def test_checkout_aggregates_once_and_preserves_rows_totals_and_item_audits(self):
        for count in (2, 4, 8):
            with self.subTest(count=count):
                with CaptureQueriesContext(connection) as queries:
                    order = create_order(self.payload(count))
                sums = [q for q in queries if 'SUM(' in q['sql'].upper()]
                self.assertEqual(len(sums), 1)
                order.refresh_from_db()
                self.assertEqual(order.total, Decimal('10.50') * count)
                self.assertEqual(order.items.count(), count)
                audits = list(order.audit_logs.filter(
                    action=AuditLog.Action.ITEM_ADDED,
                ).order_by('pk'))
                self.assertEqual(len(audits), count)
                self.assertEqual(
                    [Decimal(a.after['total']) for a in audits],
                    [Decimal('10.50') * i for i in range(1, count + 1)],
                )
                self.assertEqual(order.audit_logs.filter(action=AuditLog.Action.CREATED).count(), 1)

    def test_invalid_later_line_rolls_back_order_items_and_audits(self):
        payload = self.payload(2)
        payload['items'][1]['quantity'] = 0
        with self.assertRaises(ValidationError):
            create_order(payload)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_standalone_add_item_still_persists_authoritative_total(self):
        order = create_order(self.payload(1))
        order.total = Decimal('9999.00')  # Simulate a stale caller's cached total.
        add_item(order, self.item.pk, 2)
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal('31.50'))

    def test_known_id_bearer_access_and_expired_history_remain_available(self):
        order = create_order(self.payload(1))
        Order.objects.filter(pk=order.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        for client in (Client(), Client()):
            response = client.get(f'/api/orders/{order.public_id}/')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['status'], Order.Status.EXPIRED)
            self.assertEqual(response.json()['total'], '10.50')
            self.assertNotIn('customer_name', response.json())
            self.assertNotIn('phone', response.json())
        response = self.client.get('/api/orders/DUMMY-MISSING/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {'error': 'Order not found.'})
