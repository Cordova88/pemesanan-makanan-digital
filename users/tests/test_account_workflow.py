from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse


class AccountManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.superuser = User.objects.create_user(
            'owner', password='OwnerPass!123', is_staff=True, is_superuser=True
        )
        cls.staff = User.objects.create_user('staff-only', password='StaffPass!123', is_staff=True)

    def test_only_superuser_can_open_accounts(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(reverse('staff:accounts'))
        self.assertEqual(response.status_code, 302)
        self.assertNotContains(response, 'Tambah akun', status_code=302)

        self.client.force_login(self.superuser)
        response = self.client.get(reverse('staff:accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tambah akun')

    def test_superuser_creates_cashier_account(self) -> None:
        self.client.force_login(self.superuser)
        url = reverse('staff:accounts')
        response = self.client.post(
            url,
            {
                'username': 'kasir-baru',
                'first_name': 'Kasir',
                'last_name': 'Baru',
                'email': 'kasir@example.com',
                'role': 'cashier',
                'password1': 'KasirPass!123',
                'password2': 'KasirPass!123',
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, url)

        cashier = User.objects.get(username='kasir-baru')
        self.assertTrue(cashier.is_active)
        self.assertFalse(cashier.is_staff)
        self.assertFalse(cashier.is_superuser)
        self.assertTrue(cashier.groups.filter(name='Cashier').exists())

        self.client.logout()
        response = self.client.post(
            reverse('staff:login'),
            {'username': 'kasir-baru', 'password': 'KasirPass!123'},
        )
        self.assertRedirects(response, reverse('kasir:dashboard'))

    def test_edit_changes_role_and_password(self) -> None:
        account = User.objects.create_user('ubah-akun', password='LamaPass!123')
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse('staff:account-edit', args=[account.pk]),
            {
                'username': 'ubah-akun',
                'first_name': 'Ubah',
                'last_name': 'Akun',
                'email': '',
                'role': 'admin',
                'password1': 'BaruPass!123',
                'password2': 'BaruPass!123',
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, reverse('staff:accounts'))

        account.refresh_from_db()
        self.assertTrue(account.is_staff)
        self.assertFalse(account.is_superuser)
        self.assertTrue(account.check_password('BaruPass!123'))

    def test_superuser_cannot_demote_or_disable_self(self) -> None:
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse('staff:account-edit', args=[self.superuser.pk]),
            {
                'username': 'owner',
                'first_name': '',
                'last_name': '',
                'email': '',
                'role': 'admin',
                'is_active': 'on',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors.get('role'))

        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_superuser)

    def test_navigation_shows_accounts_only_for_superuser(self) -> None:
        self.client.force_login(self.superuser)
        self.assertContains(self.client.get(reverse('staff:dashboard')), 'Akun')

        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get(reverse('staff:dashboard')), 'Akun')
