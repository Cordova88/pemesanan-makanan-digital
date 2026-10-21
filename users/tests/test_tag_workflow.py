from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from menu.models import Category, MenuItem, MenuTag, MenuTagAlias


class CMSTagWorkflowTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('tag-review', is_staff=True))
        category = Category.objects.create(name='Makanan')
        self.first = MenuItem.objects.create(category=category, name='Ayam', price=20000)
        self.second = MenuItem.objects.create(
            category=category, name='Sup', price=15000, is_active=False
        )
        self.outside = MenuItem.objects.create(category=category, name='Nasi', price=5000)
        self.tag = MenuTag.objects.create(name='spicy', display_name='Pedas')
        self.other = MenuTag.objects.create(name='savory', display_name='Gurih')
        self.first.tags.add(self.tag, self.other)
        self.second.tags.add(self.tag)
        self.alias = MenuTagAlias.objects.create(tag=self.tag, phrase='pedes')
        self.other_alias = MenuTagAlias.objects.create(tag=self.other, phrase='asin')
        self.url = reverse('staff:tags')
        self.edit = reverse('staff:tag-edit', args=[self.tag.pk])
        self.delete = reverse('staff:tag-delete', args=[self.tag.pk])

    def test_search_by_code_or_label_and_count_includes_inactive_menu(self):
        for query in (' SPI ', 'pedas'):
            response = self.client.get(self.url, {'q': query})
            self.assertEqual([tag.pk for tag in response.context['tags']], [self.tag.pk])
            self.assertEqual(response.context['tags'][0].menu_count, 2)
            self.assertEqual(response.context['tag_total'], 2)
            self.assertContains(response, 'Reset')

        self.assertContains(
            self.client.get(self.url, {'q': 'tidak-ada'}), 'Tidak ada tag yang cocok'
        )
        self.assertEqual(len(self.client.get(self.url).context['tags']), 2)

    def test_create_and_duplicate_invalid_code_preserve_search_context(self):
        self.assertRedirects(
            self.client.post(self.url, {'name': 'fresh', 'display_name': ''}), self.url
        )
        self.assertEqual(str(MenuTag.objects.get(name='fresh')), 'fresh')

        for code in ('spicy', 'kode tidak valid'):
            response = self.client.post(
                self.url + '?q=Pedas', {'name': code, 'display_name': 'Uji'}
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn('name', response.context['form'].errors)
            self.assertContains(response, 'Tag belum disimpan')
            self.assertEqual(response.context['query'], 'Pedas')

        self.assertEqual(MenuTag.objects.count(), 3)

    def test_edit_detaches_only_unchecked_menu_and_preserves_other_data(self):
        response = self.client.get(self.edit)
        self.assertContains(response, 'Pemakaian pada 2 menu')
        self.assertContains(response, 'href="' + self.url + '"')
        self.assertEqual(
            set(response.context['form'].fields['menus'].queryset), {self.first, self.second}
        )
        self.assertRedirects(
            self.client.post(
                self.edit, {'name': 'hot', 'display_name': 'Pedas Baru', 'menus': [self.first.pk]}
            ),
            self.url,
        )
        self.tag.refresh_from_db()
        self.assertEqual(self.tag.name, 'hot')
        self.assertEqual(list(self.tag.menu_items.all()), [self.first])
        self.assertTrue(self.first.tags.filter(pk=self.other.pk).exists())
        self.assertEqual(MenuItem.objects.count(), 3)
        self.assertTrue(MenuTagAlias.objects.filter(pk=self.alias.pk).exists())

    def test_edit_rejects_unrelated_menu_and_duplicate_code_without_detaching(self):
        for payload in (
            {'name': 'spicy', 'display_name': 'Uji', 'menus': [self.outside.pk]},
            {'name': 'savory', 'display_name': 'Uji', 'menus': []},
        ):
            response = self.client.post(self.edit, payload)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
            self.assertContains(response, 'Perubahan tag belum disimpan')
            self.tag.refresh_from_db()
            self.assertEqual(self.tag.display_name, 'Pedas')
            self.assertEqual(self.tag.menu_items.count(), 2)

    def test_clear_all_usage_keeps_tag_and_menus(self):
        self.assertRedirects(
            self.client.post(self.edit, {'name': 'spicy', 'display_name': 'Pedas', 'menus': []}),
            self.url,
        )
        self.assertFalse(self.tag.menu_items.exists())
        self.assertTrue(MenuTag.objects.filter(pk=self.tag.pk).exists())
        self.assertEqual(MenuItem.objects.count(), 3)

    def test_delete_get_is_read_only_and_missing_confirmation_is_rejected(self):
        response = self.client.get(self.delete)
        self.assertContains(response, '1 alias akan ikut dihapus')
        self.assertContains(response, 'Sup')
        self.assertContains(response, '(nonaktif)')
        self.assertEqual(self.tag.menu_items.count(), 2)
        self.assertRedirects(self.client.post(self.delete, {}), self.url)
        self.assertTrue(MenuTag.objects.filter(pk=self.tag.pk).exists())
        self.assertEqual(self.tag.menu_items.count(), 2)

    def test_confirmed_delete_removes_only_target_tag_and_its_aliases(self):
        self.assertRedirects(self.client.post(self.delete, {'confirm_detach': 'yes'}), self.url)
        self.assertFalse(MenuTag.objects.filter(pk=self.tag.pk).exists())
        self.assertFalse(MenuTagAlias.objects.filter(pk=self.alias.pk).exists())
        self.assertTrue(MenuTagAlias.objects.filter(pk=self.other_alias.pk).exists())
        self.assertEqual(list(self.first.tags.all()), [self.other])
        self.assertEqual(MenuItem.objects.count(), 3)

    def test_unused_tag_can_be_deleted_without_detach_checkbox(self):
        tag = MenuTag.objects.create(name='unused')
        url = reverse('staff:tag-delete', args=[tag.pk])
        self.assertNotContains(self.client.get(url), 'name="confirm_detach"')
        self.assertRedirects(self.client.post(url, {}), self.url)
        self.assertFalse(MenuTag.objects.filter(pk=tag.pk).exists())

    def test_non_staff_cannot_read_or_change_tags(self):
        self.client.force_login(get_user_model().objects.create_user('tag-ordinary'))

        for url in (self.url, self.edit, self.delete):
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertEqual(self.client.post(url, {'confirm_detach': 'yes'}).status_code, 302)

        self.assertTrue(MenuTag.objects.filter(pk=self.tag.pk).exists())
        self.assertEqual(self.tag.menu_items.count(), 2)
