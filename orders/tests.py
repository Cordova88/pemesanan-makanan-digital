from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from menu.models import Category, MenuItem
from .models import AuditLog, Order, Table
from .models import Payment
from .services import cancel, change_table, create_order, edit_item, pay

# [OOP: Inheritance] OrderServiceTests mewarisi django.test.TestCase untuk mendapat
# database uji terisolasi dan assertion bawaan.
# [OOP: Abstraction] Tes memanggil fungsi service (create_order, pay, cancel,
# change_table) tanpa perlu tahu detail transaksi dan audit di dalamnya.
class OrderServiceTests(TestCase):
    # [OOP: Polymorphism] setUp meng-override hook bawaan TestCase (method overriding);
    # dipanggil otomatis sebelum setiap test untuk menyiapkan menu, meja, dan akun kasir.
    def setUp(self):
        category=Category.objects.create(name="Makanan")
        self.item=MenuItem.objects.create(category=category,name="Nasi Goreng",price=Decimal("15000"))
        self.table = Table.objects.create(number="05")
        self.other_table = Table.objects.create(number="07")
        self.cashier=User.objects.create_user("cashier",password="secret")
        self.cashier.groups.add(Group.objects.create(name="Cashier"))
    # [OOP: Encapsulation] Helper checkout membungkus langkah membuat pesanan
    # (data default + override lewat **values) agar bisa dipakai ulang oleh banyak test.
    def checkout(self, **values):
        data={"customer_name":"Ani","order_type":"TAKEAWAY","items":[{"menu_item_id":self.item.id,"quantity":2}]}; data.update(values); return create_order(data)
    def test_checkout_snapshots_server_price_and_audits(self):
        order=self.checkout(); self.assertEqual(order.total,Decimal("30000")); self.item.price=Decimal("20000"); self.item.save(); order.refresh_from_db(); self.assertEqual(order.items.get().unit_price,Decimal("15000")); self.assertTrue(order.audit_logs.filter(action=AuditLog.Action.CREATED).exists())
    def test_dine_in_requires_valid_table_token(self):
        with self.assertRaises(ValidationError): self.checkout(order_type="DINE_IN")
        with self.assertRaises(ValidationError): self.checkout(order_type="DINE_IN", table_token="made-up")
        order = self.checkout(order_type="DINE_IN", table_token=self.table.token)
        self.assertEqual(order.table, self.table)
    def test_inactive_table_and_takeaway_table_token_are_not_accepted_as_table_assignment(self):
        self.table.is_active = False; self.table.save()
        with self.assertRaises(ValidationError): self.checkout(order_type="DINE_IN", table_token=self.table.token)
        order = self.checkout(table_token=self.other_table.token)
        self.assertIsNone(order.table)
    def test_many_orders_can_use_one_table(self):
        first = self.checkout(order_type="DINE_IN", table_token=self.table.token)
        second = self.checkout(order_type="DINE_IN", table_token=self.table.token)
        self.assertEqual(self.table.orders.count(), 2)
        self.assertNotEqual(first.public_id, second.public_id)
    def test_unavailable_item_rejected(self):
        self.item.is_available=False; self.item.save()
        with self.assertRaises(ValidationError): self.checkout()
    def test_payment_records_cashier_and_cannot_repeat(self):
        order=pay(self.checkout().public_id,self.cashier,amount_received=Decimal("30000")); self.assertEqual(order.status,Order.Status.PAID); self.assertEqual(order.processed_by_cashier,self.cashier)
        with self.assertRaises(ValidationError): pay(order.public_id,self.cashier)

    def test_insufficient_cash_is_rejected_without_payment_or_paid_audit(self):
        self.item.price = Decimal("25000")
        self.item.save()
        order = self.checkout(items=[{"menu_item_id": self.item.id, "quantity": 1}])

        with self.assertRaises(ValidationError):
            pay(order.public_id, self.cashier, amount_received=Decimal("10000"))

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertFalse(Payment.objects.filter(order=order).exists())
        self.assertFalse(order.audit_logs.filter(action=AuditLog.Action.PAID).exists())

    def test_empty_order_cannot_be_paid(self):
        order = self.checkout()
        line = order.items.get()
        edit_item(order.public_id, line.pk, 0, self.cashier)

        with self.assertRaises(ValidationError):
            pay(order.public_id, self.cashier, amount_received=Decimal("30000"))

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.total, Decimal("0.00"))
        self.assertFalse(Payment.objects.filter(order=order).exists())
        self.assertFalse(order.audit_logs.filter(action=AuditLog.Action.PAID).exists())

    def test_unsupported_payment_method_is_rejected_without_payment(self):
        order = self.checkout()

        with self.assertRaises(ValidationError):
            pay(order.public_id, self.cashier, method="BITCOIN", amount_received=Decimal("30000"))

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertFalse(Payment.objects.filter(order=order).exists())
        self.assertFalse(order.audit_logs.filter(action=AuditLog.Action.PAID).exists())

    def test_exact_cash_records_due_and_zero_change(self):
        order = self.checkout()

        paid = pay(order.public_id, self.cashier, amount_received=Decimal("30000"))

        payment = paid.payment
        self.assertEqual(payment.amount, Decimal("30000.00"))
        self.assertEqual(payment.amount_received, Decimal("30000.00"))
        self.assertEqual(payment.change_given, Decimal("0.00"))
        audit = paid.audit_logs.get(action=AuditLog.Action.PAID)
        self.assertEqual(audit.after["amount"], "30000.00")
        self.assertEqual(audit.after["amount_received"], "30000.00")
        self.assertEqual(audit.after["change_given"], "0.00")

    def test_cash_overpayment_records_correct_change(self):
        order = self.checkout()

        paid = pay(order.public_id, self.cashier, amount_received=Decimal("50000"))

        self.assertEqual(paid.payment.amount, Decimal("30000.00"))
        self.assertEqual(paid.payment.amount_received, Decimal("50000.00"))
        self.assertEqual(paid.payment.change_given, Decimal("20000.00"))

    def test_payment_recalculates_due_from_order_items_not_cached_total(self):
        order = self.checkout()
        order.total = Decimal("1.00")
        order.save(update_fields=["total"])

        paid = pay(order.public_id, self.cashier, amount_received=Decimal("30000"))

        self.assertEqual(paid.total, Decimal("30000.00"))
        self.assertEqual(paid.payment.amount, Decimal("30000.00"))

    def test_valid_non_cash_methods_do_not_record_cash_tender_or_change(self):
        for method in (Payment.Method.CARD, Payment.Method.QRIS, Payment.Method.OTHER):
            with self.subTest(method=method):
                order = self.checkout()
                paid = pay(order.public_id, self.cashier, method=method)
                self.assertEqual(paid.status, Order.Status.PAID)
                self.assertEqual(paid.payment.amount, Decimal("30000.00"))
                self.assertIsNone(paid.payment.amount_received)
                self.assertIsNone(paid.payment.change_given)

    def test_payment_api_rejects_invalid_method_and_uses_order_total(self):
        order = self.checkout()
        self.client.force_login(self.cashier)

        insufficient = self.client.post(
            f"/api/orders/{order.public_id}/pay/",
            data='{"method":"CASH","amount_received":"10000","total":"1.00"}',
            content_type="application/json",
        )
        self.assertEqual(insufficient.status_code, 400)
        self.assertFalse(Payment.objects.filter(order=order).exists())
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

        invalid = self.client.post(
            f"/api/orders/{order.public_id}/pay/",
            data='{"method":"BITCOIN","amount_received":"30000"}',
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(Payment.objects.filter(order=order).exists())
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

        response = self.client.post(
            f"/api/orders/{order.public_id}/pay/",
            data='{"method":"CASH","amount_received":"30000","total":"1.00"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.amount, Decimal("30000.00"))
    def test_expired_order_cannot_pay(self):
        order=self.checkout(); order.expires_at=timezone.now()-timedelta(seconds=1); order.save()
        with self.assertRaises(ValidationError): pay(order.public_id,self.cashier)
    def test_cancelled_order_cannot_pay(self):
        order=cancel(self.checkout().public_id,self.cashier)
        with self.assertRaises(ValidationError): pay(order.public_id,self.cashier)
    def test_cashier_can_correct_pending_table_without_extending_expiry(self):
        order = self.checkout(order_type="DINE_IN", table_token=self.table.token)
        expires_at = order.expires_at
        changed = change_table(order.public_id, self.other_table.token, self.cashier)
        self.assertEqual(changed.table, self.other_table)
        self.assertEqual(changed.expires_at, expires_at)
        audit = changed.audit_logs.latest("created_at")
        self.assertEqual(audit.before["table"], "05")
        self.assertEqual(audit.after["table"], "07")
        changed.status = Order.Status.PAID; changed.save()
        with self.assertRaises(ValidationError): change_table(changed.public_id, self.table.token, self.cashier)
    def test_confirmation_page_and_lookup_are_refresh_safe(self):
        order = self.checkout()
        response = self.client.get(f"/orders/{order.public_id}/")
        self.assertTemplateUsed(response, "orders/confirmation.html")
        self.assertContains(response, order.public_id)
        lookup = self.client.get(f"/api/orders/{order.public_id}/")
        self.assertEqual(lookup.status_code, 200)
        self.assertEqual(lookup.json()["public_id"], order.public_id)
    def test_table_qr_lookup_does_not_create_order(self):
        response = self.client.get(f"/api/orders/tables/{self.table.token}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["number"], "05")
        self.assertEqual(Order.objects.count(), 0)
