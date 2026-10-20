import tempfile
from pathlib import Path
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from menu.models import Category, MenuItem, MenuTag
from users.tests.test_photo_editor import photo


class CMSMenuWorkflowTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        setting = override_settings(MEDIA_ROOT=Path(directory.name) / 'media', MENU_ORIGINALS_ROOT=Path(directory.name) / 'originals')
        setting.enable()
        self.addCleanup(setting.disable)
        self.client.force_login(get_user_model().objects.create_user('menu-workflow-test', is_staff=True))
        self.category = Category.objects.create(name='Makanan')
        self.tag = MenuTag.objects.create(name='savory', display_name='Gurih')
        self.item = MenuItem.objects.create(category=self.category, name='Menu Awal', price=18000,
                                           detail_image='menu/detail/retained.webp')
        self.item.tags.add(self.tag)
        self.url = reverse('staff:menu-items')

    def data(self, **extra):
        return {'category': self.category.pk, 'name': 'Menu Uji Baru', 'description': 'Dibuat segar',
                'price': '24000', 'is_active': 'on', 'is_available': 'on', 'tags': [self.tag.pk], **extra}

    def test_add_and_edit_share_all_customer_photo_and_status_fields(self):
        for url in (self.url, reverse('staff:menu-item-edit', args=[self.item.pk])):
            response = self.client.get(url)
            for text in ('Informasi menu', 'Status menu', 'data-photo-selection', 'data-choice-picker', 'Foto lama (arsip opsional)'):
                self.assertContains(response, text)

    def test_search_name_category_and_empty_result(self):
        for query in ('awal', 'makanan'):
            response = self.client.get(self.url, {'q': query})
            self.assertEqual(list(response.context['items']), [self.item])
            self.assertContains(response, 'Reset')
        response = self.client.get(self.url, {'q': 'tidak-ada-menu-ini'})
        self.assertEqual(list(response.context['items']), [])
        self.assertContains(response, 'Tidak ada menu yang cocok')

    def test_upload_then_edit_preserves_photo_and_archive_and_updates_tags(self):
        self.assertRedirects(self.client.post(self.url, self.data(image=photo())), self.url)
        created = MenuItem.objects.get(name='Menu Uji Baru')
        filename = created.image.name
        self.assertTrue(filename.endswith('.webp'))
        created.detail_image = self.item.detail_image.name
        created.save(update_fields=['detail_image'])
        edit_url = reverse('staff:menu-item-edit', args=[created.pk])
        payload = self.data(name='Menu Revisi', price='25000', tags=[])
        self.assertRedirects(self.client.post(edit_url, payload), self.url)
        created.refresh_from_db()
        self.assertEqual(created.image.name, filename)
        self.assertEqual(created.detail_image.name, 'menu/detail/retained.webp')
        self.assertEqual(created.price, 25000)
        self.assertFalse(created.tags.exists())

    def test_invalid_price_and_stock_keep_existing_data_and_bound_tags(self):
        response = self.client.post(reverse('staff:menu-item-edit', args=[self.item.pk]),
                                    self.data(price='-1', stock_estimate='-2'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors.get('price'))
        self.assertTrue(response.context['form'].errors.get('stock_estimate'))
        self.assertEqual(response.context['form']['tags'].value(), [str(self.tag.pk)])
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, 'Menu Awal')
        self.assertEqual(self.item.price, 18000)
        self.assertEqual(list(self.item.tags.all()), [self.tag])

    def test_customer_catalog_requires_both_menu_flags_and_active_category(self):
        for field in ('is_available', 'is_active'):
            with self.subTest(field=field):
                self.item.is_available = self.item.is_active = True
                setattr(self.item, field, False)
                self.item.save()
                self.assertEqual(self.client.get('/api/menu/').json()['items'], [])
        self.item.is_active = self.item.is_available = True
        self.item.save()
        self.category.is_active = False
        self.category.save()
        self.assertEqual(self.client.get('/api/menu/').json()['items'], [])
        self.category.is_active = True
        self.category.save()
        self.assertEqual([item['id'] for item in self.client.get('/api/menu/').json()['items']], [self.item.pk])

    def test_category_cancel_is_explicit_and_non_staff_cannot_create(self):
        response = self.client.get(reverse('staff:category-edit', args=[self.category.pk]))
        self.assertContains(response, 'Nama kategori')
        self.assertContains(response, 'href="' + reverse('staff:categories') + '"')
        self.client.force_login(get_user_model().objects.create_user('ordinary-workflow-test'))
        self.assertEqual(self.client.post(self.url, self.data()).status_code, 302)
        self.assertEqual(MenuItem.objects.count(), 1)
