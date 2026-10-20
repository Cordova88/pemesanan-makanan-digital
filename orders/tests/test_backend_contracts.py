from decimal import Decimal

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from menu.models import AddOn, Category, MenuItem, VariantGroup, VariantOption
from ..models import Order
from ..services import create_order, pay


class OrderStatePropertyTests(SimpleTestCase):
    def test_status_properties_follow_current_state_without_a_query(self) -> None:
        order = Order(status=Order.Status.PENDING)
        self.assertTrue(order.is_pending)
        self.assertFalse(order.is_paid)
        order.status = Order.Status.PAID
        self.assertFalse(order.is_pending)
        self.assertTrue(order.is_paid)
        order.status = Order.Status.REFUNDED
        self.assertFalse(order.is_paid)


class SharedSelectionOrderTests(TestCase):
    def test_selected_prices_snapshots_and_payment_total_remain_exact(self) -> None:
        category = Category.objects.create(name="Food")
        item = MenuItem.objects.create(category=category, name="Rice", price=Decimal("10.50"))
        group = VariantGroup.objects.create(menu_item=item, name="Size", is_required=True)
        option = VariantOption.objects.create(group=group, name="Large", price_adjustment=Decimal("2.25"))
        addon = AddOn.objects.create(name="Sauce", price=Decimal("0.75"))
        addon.menu_items.add(item)
        order = create_order({
            "customer_name": "Test", "order_type": "TAKEAWAY",
            "items": [{"menu_item_id": item.pk, "quantity": 2, "variant_ids": [option.pk] * 2, "addon_ids": [addon.pk]}],
        })
        line = order.items.get()
        self.assertEqual(line.unit_price, Decimal("13.50"))
        self.assertEqual(order.total, Decimal("27.00"))
        self.assertEqual(line.variants.count(), 1)
        self.assertEqual(line.addons.count(), 1)
        item.price = Decimal("20.00")
        item.save()
        cashier = User.objects.create_user("property-test-cashier")
        paid = pay(order.public_id, cashier, amount_received="30.00")
        self.assertEqual(paid.payment.amount, Decimal("27.00"))
        self.assertEqual(paid.payment.change_given, Decimal("3.00"))
