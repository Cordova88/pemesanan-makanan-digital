from django.test import TestCase

# Create your tests here.
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from orders.models import Order


class CashierAreaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        group, _ = Group.objects.get_or_create(name="Cashier")
        cls.cashier = User.objects.create_user("kasir1", password="pw12345!x")
        cls.cashier.groups.add(group)
        cls.admin = User.objects.create_user("adm", password="pw12345!x", is_staff=True)
        cls.other = User.objects.create_user("biasa", password="pw12345!x")
        cls.order = Order.objects.create(customer_name="Budi", order_type="TAKEAWAY")

    def test_anonymous_redirected_to_login(self):
        r = self.client.get(reverse("kasir:dashboard"))
        self.assertRedirects(r, reverse("staff:login") + "?next=" + reverse("kasir:dashboard"))

    def test_cashier_login_goes_to_cashier_area(self):
        r = self.client.post(reverse("staff:login"), {"username": "kasir1", "password": "pw12345!x"})
        self.assertRedirects(r, reverse("kasir:dashboard"))

    def test_admin_login_goes_to_cms(self):
        r = self.client.post(reverse("staff:login"), {"username": "adm", "password": "pw12345!x"})
        self.assertRedirects(r, reverse("staff:dashboard"))

    def test_account_without_role_cannot_login(self):
        r = self.client.post(reverse("staff:login"), {"username": "biasa", "password": "pw12345!x"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_non_cashier_forbidden(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("kasir:dashboard")).status_code, 403)

    def test_cashier_sees_pending_order(self):
        self.client.force_login(self.cashier)
        self.assertContains(self.client.get(reverse("kasir:dashboard")), self.order.public_id)

    def test_search_by_id_opens_detail(self):
        self.client.force_login(self.cashier)
        r = self.client.get(reverse("kasir:dashboard"), {"q": self.order.public_id.lower()})
        self.assertRedirects(r, reverse("kasir:order", args=[self.order.public_id]))

    def test_detail_shows_customer(self):
        self.client.force_login(self.cashier)
        self.assertContains(self.client.get(reverse("kasir:order", args=[self.order.public_id])), "Budi")

    def test_unknown_id_goes_back_to_search(self):
        self.client.force_login(self.cashier)
        r = self.client.get(reverse("kasir:order", args=["ZZZZZZZZ"]))
        self.assertRedirects(r, reverse("kasir:dashboard") + "?q=ZZZZZZZZ", fetch_redirect_response=False)

    def test_cashier_cannot_open_admin_cms(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("staff:dashboard")).status_code, 302)

    def test_admin_can_open_cashier_area(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("kasir:dashboard")).status_code, 200)