from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from menu.models import Category


class CMSShellOperationTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user('cms-shell-test', is_staff=True)
        self.client.force_login(self.staff)

    def test_all_navigation_pages_remain_accessible(self):
        for name in (
            'dashboard',
            'categories',
            'menu-items',
            'tags',
            'variants',
            'addons',
            'tables',
            'orders',
            'audit-log',
        ):
            with self.subTest(page=name):
                response = self.client.get(reverse('staff:' + name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'cms-shell.css')
                self.assertContains(response, 'aria-label="Buka navigasi CMS"')

    def test_category_add_edit_and_duplicate_keep_the_same_contract(self):
        url = reverse('staff:categories')
        self.assertRedirects(
            self.client.post(url, {'name': 'Kategori Uji', 'is_active': 'on'}), url
        )
        category = Category.objects.get(name='Kategori Uji')
        response = self.client.post(url, {'name': 'Kategori Uji', 'is_active': 'on'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors.get('name'))
        self.assertEqual(Category.objects.count(), 1)
        self.assertRedirects(
            self.client.post(
                reverse('staff:category-edit', args=[category.pk]), {'name': 'Kategori Revisi'}
            ),
            url,
        )
        category.refresh_from_db()
        self.assertEqual(category.name, 'Kategori Revisi')
        self.assertFalse(category.is_active)
