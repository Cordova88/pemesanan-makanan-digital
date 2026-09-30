from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from menu.models import Category, MenuItem
from .models import AuditLog, Order
from .services import cancel, create_order, pay

class OrderServiceTests(TestCase):
    def setUp(self):
        category=Category.objects.create(name="Makanan")
        self.item=MenuItem.objects.create(category=category,name="Nasi Goreng",price=Decimal("15000"))
        self.cashier=User.objects.create_user("cashier",password="secret")
        self.cashier.groups.add(Group.objects.create(name="Cashier"))
    def checkout(self, **values):
        data={"customer_name":"Ani","order_type":"TAKEAWAY","items":[{"menu_item_id":self.item.id,"quantity":2}]}; data.update(values); return create_order(data)
    def test_checkout_snapshots_server_price_and_audits(self):
        order=self.checkout(); self.assertEqual(order.total,Decimal("30000")); self.item.price=Decimal("20000"); self.item.save(); order.refresh_from_db(); self.assertEqual(order.items.get().unit_price,Decimal("15000")); self.assertTrue(order.audit_logs.filter(action=AuditLog.Action.CREATED).exists())
    def test_dine_in_requires_table(self):
        with self.assertRaises(ValidationError): self.checkout(order_type="DINE_IN")
    def test_unavailable_item_rejected(self):
        self.item.is_available=False; self.item.save()
        with self.assertRaises(ValidationError): self.checkout()
    def test_payment_records_cashier_and_cannot_repeat(self):
        order=pay(self.checkout().public_id,self.cashier); self.assertEqual(order.status,Order.Status.PAID); self.assertEqual(order.processed_by_cashier,self.cashier)
        with self.assertRaises(ValidationError): pay(order.public_id,self.cashier)
    def test_expired_order_cannot_pay(self):
        order=self.checkout(); order.expires_at=timezone.now()-timedelta(seconds=1); order.save()
        with self.assertRaises(ValidationError): pay(order.public_id,self.cashier)
    def test_cancelled_order_cannot_pay(self):
        order=cancel(self.checkout().public_id,self.cashier)
        with self.assertRaises(ValidationError): pay(order.public_id,self.cashier)
