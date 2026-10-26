from decimal import Decimal
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from menu.models import Category, MenuItem
from orders.models import AuditLog, Order, Payment, Table
from orders.services import cancel, create_order, process_qr_payment


class FakeOnlinePaymentGatewayTests(TestCase):
    def setUp(self) -> None:
        category = Category.objects.create(name="Makanan Utama")
        self.item = MenuItem.objects.create(
            category=category, name="Nasi Ayam Bakar", price=Decimal("25000")
        )
        self.table = Table.objects.create(number="12")

    def create_test_order(self, quantity: int = 2) -> Order:
        return create_order({
            "customer_name": "Budi",
            "order_type": "DINE_IN",
            "table_token": self.table.token,
            "items": [{"menu_item_id": self.item.id, "quantity": quantity}],
        })

    def test_qr_payment_automatically_completes_transaction_with_required_amount(self) -> None:
        order = self.create_test_order(quantity=2)
        expected_total = Decimal("50000.00")
        self.assertEqual(order.total, expected_total)
        self.assertEqual(order.status, Order.Status.PENDING)

        paid_order = process_qr_payment(order.public_id)

        self.assertEqual(paid_order.status, Order.Status.PAID)
        self.assertIsNotNone(paid_order.paid_at)
        self.assertIsNone(paid_order.processed_by_cashier)

        payment = Payment.objects.get(order=paid_order)
        self.assertEqual(payment.method, Payment.Method.QRIS)
        self.assertEqual(payment.amount, expected_total)
        self.assertEqual(payment.amount_received, expected_total)
        self.assertEqual(payment.change_given, Decimal("0.00"))
        self.assertIsNone(payment.cashier)
        self.assertTrue(payment.external_reference.startswith("QRIS-"))

        audit = paid_order.audit_logs.filter(action=AuditLog.Action.PAID).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.after.get("amount"), "50000.00")
        self.assertEqual(audit.after.get("method"), "QRIS")

    def test_qr_payment_is_idempotent_on_repeated_scans(self) -> None:
        order = self.create_test_order(quantity=1)
        first_scan = process_qr_payment(order.public_id)
        self.assertEqual(first_scan.status, Order.Status.PAID)

        # Scanning again should return successfully without error
        second_scan = process_qr_payment(order.public_id)
        self.assertEqual(second_scan.status, Order.Status.PAID)
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)

    def test_qr_payment_rejects_expired_order(self) -> None:
        order = self.create_test_order()
        order.expires_at = timezone.now() - timedelta(seconds=10)
        order.save(update_fields=["expires_at"])

        with self.assertRaises(ValidationError):
            process_qr_payment(order.public_id)

    def test_qr_payment_rejects_cancelled_order(self) -> None:
        order = self.create_test_order()
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            process_qr_payment(order.public_id)

    def test_scan_via_phone_browser_get_renders_success_and_completes_transaction(self) -> None:
        order = self.create_test_order(quantity=3)
        expected_total = Decimal("75000.00")

        # Simulate smartphone camera scanning QR: GET /orders/<public_id>/pay-qr/
        response = self.client.get(f"/orders/{order.public_id}/pay-qr/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "orders/payment_success.html")
        self.assertContains(response, "Pembayaran Berhasil")
        self.assertContains(response, order.public_id)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.payment.amount, expected_total)
        self.assertEqual(order.payment.amount_received, expected_total)

    def test_scan_via_api_post_returns_json_and_completes_transaction(self) -> None:
        order = self.create_test_order(quantity=1)

        # Simulate desktop simulation button / API trigger
        response = self.client.post(
            f"/api/orders/{order.public_id}/pay-qr/",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data["order"]["status"], "PAID")
        self.assertEqual(data["order"]["payment"]["method"], "QRIS")
        self.assertEqual(data["order"]["payment"]["amount"], "25000.00")

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_pay_qr_unknown_order_returns_404(self) -> None:
        response = self.client.get("/orders/UNKNOWNID/pay-qr/")
        self.assertEqual(response.status_code, 404)

        json_response = self.client.post("/api/orders/UNKNOWNID/pay-qr/")
        self.assertEqual(json_response.status_code, 404)

    def test_lookup_and_confirmation_page_reflect_qr_payment_flow(self) -> None:
        order = self.create_test_order(quantity=2)

        # Check confirmation page renders
        conf_response = self.client.get(f"/orders/{order.public_id}/")
        self.assertEqual(conf_response.status_code, 200)
        self.assertTemplateUsed(conf_response, "orders/confirmation.html")
        self.assertContains(conf_response, order.public_id)

        # Check API lookup returns pay_qr_url
        lookup_response = self.client.get(f"/api/orders/{order.public_id}/")
        self.assertEqual(lookup_response.status_code, 200)
        lookup_data = lookup_response.json()
        self.assertIn("pay_qr_url", lookup_data)
        self.assertEqual(lookup_data["pay_qr_url"], f"/orders/{order.public_id}/pay-qr/")
        self.assertFalse(lookup_data["is_paid"])

        # Pay via QR
        process_qr_payment(order.public_id)

        # Lookup again
        lookup_after = self.client.get(f"/api/orders/{order.public_id}/").json()
        self.assertTrue(lookup_after["is_paid"])
        self.assertEqual(lookup_after["status"], "PAID")
        self.assertIsNotNone(lookup_after["payment"])
        self.assertEqual(lookup_after["payment"]["method"], "QRIS")
