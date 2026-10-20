import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from menu.models import AddOn, Category, MenuItem, VariantGroup, VariantOption


class CMSVariantWorkflowTests(TestCase):
    def setUp(self):
        self.client.force_login(
            get_user_model().objects.create_user('variant-review', is_staff=True)
        )
        category = Category.objects.create(name='Makanan')
        self.item = MenuItem.objects.create(category=category, name='Nasi', price=20000)
        self.other = MenuItem.objects.create(category=category, name='Sup', price=15000)
        self.group = VariantGroup.objects.create(
            menu_item=self.item, name='Ukuran', is_required=True
        )
        self.option = VariantOption.objects.create(
            group=self.group, name='Besar', price_adjustment=3000
        )
        self.addon = AddOn.objects.create(name='Telur', price=5000)
        self.addon.menu_items.add(self.item)
        self.url = reverse('staff:variants')
        self.addons = reverse('staff:addons')

    def group_data(self, **extra):
        return {
            'kind': 'group',
            'menu_item': self.item.pk,
            'name': 'Level',
            'is_active': 'on',
            'display_order': 1,
            **extra,
        }

    def option_data(self, **extra):
        return {
            'kind': 'option',
            'group': self.group.pk,
            'name': 'Kecil',
            'price_adjustment': 0,
            'is_active': 'on',
            'display_order': 1,
            **extra,
        }

    def addon_data(self, **extra):
        return {
            'name': 'Keju',
            'price': 4000,
            'menu_items': [self.other.pk],
            'is_available': 'on',
            'is_active': 'on',
            **extra,
        }

    def catalog(self):
        return {row['id']: row for row in self.client.get('/api/menu/').json()['items']}

    def test_create_group_and_option_and_distinct_form_ids(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="group_name"')
        self.assertContains(response, 'id="option_name"')
        self.assertRedirects(self.client.post(self.url, self.group_data()), self.url)
        self.assertRedirects(self.client.post(self.url, self.option_data()), self.url)
        self.assertTrue(VariantGroup.objects.filter(name='Level', menu_item=self.item).exists())
        self.assertTrue(VariantOption.objects.filter(name='Kecil', price_adjustment=0).exists())

    def test_invalid_group_retains_values_and_non_field_duplicate_errors(self):
        for payload in (self.group_data(name='Ukuran'), self.group_data(display_order=-1)):
            response = self.client.post(self.url, payload)
            form = response.context['group_form']
            self.assertTrue(form.is_bound)
            self.assertTrue(form.errors)
            self.assertFalse(response.context['option_form'].is_bound)
            self.assertContains(response, 'Data belum disimpan')
            self.assertEqual(form['name'].value(), payload['name'])

        self.assertEqual(VariantGroup.objects.count(), 1)
        self.assertContains(
            self.client.post(self.url, self.group_data(name='Ukuran')),
            'Grup dengan nama ini sudah ada',
        )

    def test_invalid_option_retains_negative_price_duplicate_and_missing_group_errors(self):
        for payload in (
            self.option_data(price_adjustment=-1),
            self.option_data(name='Besar'),
            self.option_data(group=''),
        ):
            response = self.client.post(self.url, payload)
            self.assertTrue(response.context['option_form'].errors)
            self.assertTrue(response.context['option_form'].is_bound)
            self.assertFalse(response.context['group_form'].is_bound)
            self.assertContains(response, 'Data belum disimpan')

        self.assertEqual(VariantOption.objects.count(), 1)
        self.assertContains(
            self.client.post(self.url, self.option_data(name='Besar')),
            'Opsi dengan nama ini sudah ada',
        )

    def test_edit_links_cancel_and_option_price_order_status_persist(self):
        edit = reverse('staff:variant-option-edit', args=[self.option.pk])
        group_edit = reverse('staff:variant-group-edit', args=[self.group.pk])
        self.assertContains(self.client.get(self.url), 'href="' + edit + '"')

        for url in (edit, group_edit):
            self.assertEqual(self.client.get(url).context['cancel_url'], self.url)

        self.assertRedirects(
            self.client.post(
                edit, self.option_data(name='Besar Revisi', price_adjustment=4500, display_order=2)
            ),
            self.url,
        )
        self.option.refresh_from_db()
        self.assertEqual(self.option.price_adjustment, 4500)
        self.assertEqual(self.option.display_order, 2)
        self.assertRedirects(
            self.client.post(group_edit, self.group_data(name='Ukuran', is_active='')), self.url
        )
        self.assertEqual(self.catalog()[self.item.pk]['variants'], [])

    def test_addon_create_edit_relations_clear_and_invalid_price(self):
        self.assertRedirects(self.client.post(self.addons, self.addon_data()), self.addons)
        created = AddOn.objects.get(name='Keju')
        self.assertEqual(list(created.menu_items.all()), [self.other])
        edit = reverse('staff:addon-edit', args=[created.pk])
        response = self.client.get(edit)
        self.assertEqual(response.context['cancel_url'], self.addons)
        self.assertContains(response, 'data-choice-picker')
        response = self.client.post(edit, self.addon_data(price=-1, menu_items=[self.item.pk]))
        self.assertTrue(response.context['form'].errors)
        created.refresh_from_db()
        self.assertEqual(created.price, 4000)
        self.assertEqual(list(created.menu_items.all()), [self.other])
        self.assertRedirects(
            self.client.post(edit, self.addon_data(price=4500, menu_items=[])), self.addons
        )
        self.assertFalse(created.menu_items.exists())
        self.assertContains(self.client.get(self.addons), 'Belum terhubung ke menu')
        self.assertFalse(
            any(
                row['addons'] and any(a['id'] == created.pk for a in row['addons'])
                for row in self.catalog().values()
            )
        )

    def test_addon_duplicate_keeps_bound_menu_choices(self):
        response = self.client.post(self.addons, self.addon_data(name='Telur'))
        self.assertIn('name', response.context['form'].errors)
        self.assertEqual(response.context['form']['menu_items'].value(), [str(self.other.pk)])
        self.assertContains(response, 'Data belum disimpan')
        self.assertContains(response, 'Nama tambahan ini sudah digunakan.')
        self.assertEqual(AddOn.objects.count(), 1)

    def test_catalog_hides_inactive_options_groups_and_unavailable_addons(self):
        self.assertEqual(
            self.catalog()[self.item.pk]['variants'][0]['options'][0]['id'], self.option.pk
        )
        self.assertEqual(self.catalog()[self.other.pk]['addons'], [])
        self.option.is_active = False
        self.option.save()
        self.assertEqual(self.catalog()[self.item.pk]['variants'][0]['options'], [])

        for field in ('is_available', 'is_active'):
            self.addon.is_available = self.addon.is_active = True
            setattr(self.addon, field, False)
            self.addon.save()
            self.assertEqual(self.catalog()[self.item.pk]['addons'], [])

    def test_cart_price_uses_cms_prices_and_rejects_missing_required_or_unrelated_selection(self):
        def add(**extra):
            data = {
                'menu_item_id': self.item.pk,
                'quantity': 2,
                'variant_ids': [self.option.pk],
                'addon_ids': [self.addon.pk],
                'price': 1,
                **extra,
            }

            return self.client.post(
                '/api/cart/add/', data=json.dumps(data), content_type='application/json'
            )

        self.assertEqual(add(variant_ids=[]).status_code, 400)
        self.addon.menu_items.set([self.other])
        self.assertEqual(add().status_code, 400)
        self.addon.menu_items.set([self.item])
        response = add()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total'], '56000.00')  # (20000 + 3000 + 5000) x 2

    def test_non_staff_cannot_access_or_save(self):
        self.client.force_login(get_user_model().objects.create_user('variant-ordinary'))

        for url in (
            self.url,
            self.addons,
            reverse('staff:variant-group-edit', args=[self.group.pk]),
            reverse('staff:variant-option-edit', args=[self.option.pk]),
            reverse('staff:addon-edit', args=[self.addon.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertEqual(self.client.post(url, {}).status_code, 302)

        self.assertEqual(VariantGroup.objects.count(), 1)
        self.assertEqual(VariantOption.objects.count(), 1)
        self.assertEqual(AddOn.objects.count(), 1)
