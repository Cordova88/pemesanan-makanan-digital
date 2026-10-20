from base64 import b64decode
from io import BytesIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from PIL import Image
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from orders.models import Order, Table
from users.views import _qr_png


class CMSTableWorkflowTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('table-review', is_staff=True))
        self.table = Table.objects.create(number='A1')
        self.url = reverse('staff:tables')
        self.edit = reverse('staff:table-edit', args=[self.table.pk])
        self.qr = reverse('staff:table-qr', args=[self.table.pk])
        self.download = reverse('staff:table-qr-download', args=[self.table.pk])

    def test_create_duplicate_and_empty_name_preserve_bound_errors(self):
        self.assertRedirects(
            self.client.post(self.url, {'number': 'Teras 2', 'is_active': 'on'}), self.url
        )
        created = Table.objects.get(number='Teras 2')
        self.assertTrue(created.is_active)
        self.assertNotEqual(created.token, self.table.token)

        for name in ('A1', ''):
            response = self.client.post(self.url, {'number': name, 'is_active': 'on'})
            self.assertTrue(response.context['form'].errors)
            self.assertEqual(response.context['form']['number'].value(), name)
            self.assertContains(response, 'Data belum disimpan')

        self.assertContains(
            self.client.post(self.url, {'number': 'A1'}), 'Nomor / nama meja ini sudah digunakan.'
        )
        self.assertEqual(Table.objects.count(), 2)

    def test_edit_status_name_preserves_token_and_cancel_destination(self):
        original_token = self.table.token
        self.assertEqual(self.client.get(self.edit).context['cancel_url'], self.url)
        self.assertRedirects(self.client.post(self.edit, {'number': 'Teras Revisi'}), self.url)
        self.table.refresh_from_db()
        self.assertEqual(self.table.number, 'Teras Revisi')
        self.assertFalse(self.table.is_active)
        self.assertEqual(self.table.token, original_token)
        self.assertRedirects(
            self.client.post(self.edit, {'number': 'Teras Revisi', 'is_active': 'on'}), self.url
        )
        self.table.refresh_from_db()
        self.assertEqual(self.table.token, original_token)
        self.assertTrue(self.table.is_active)

    def test_invalid_edit_preserves_name_status_and_token(self):
        Table.objects.create(number='A2')
        token = self.table.token
        response = self.client.post(self.edit, {'number': 'A2'})
        self.assertTrue(response.context['form'].errors)
        self.table.refresh_from_db()
        self.assertEqual(
            (self.table.number, self.table.is_active, self.table.token), ('A1', True, token)
        )

    def test_qr_contains_exact_customer_url_and_valid_png_without_creating_order(self):
        with patch('users.views._qr_png', wraps=_qr_png) as generate:
            response = self.client.get(self.qr)
            generate.assert_called_once_with('http://testserver/?table=' + self.table.token)

        self.assertTemplateUsed(response, 'users/table_qr.html')
        self.assertContains(response, 'Kode QR untuk Meja A1')
        self.assertContains(response, 'Unduh QR PNG')
        self.assertNotContains(response, 'Tambah meja')
        parsed = urlsplit(response.context['table_url'])
        self.assertEqual(parsed.path, '/')
        self.assertEqual(parse_qs(parsed.query), {'table': [self.table.token]})
        image = Image.open(BytesIO(b64decode(response.context['qr_data'])))
        self.assertEqual(image.format, 'PNG')
        self.assertEqual(image.width, image.height)
        image.verify()
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.client.get(response.context['table_url']).status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

    def test_download_matches_preview_and_uses_safe_identifier_filename(self):
        self.table.number = 'Teras / "Jendela"'
        self.table.save()
        preview = self.client.get(self.qr)
        response = self.client.get(self.download)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertEqual(
            response['Content-Disposition'],
            f'attachment; filename="rasakita-table-{self.table.pk}.png"',
        )
        self.assertEqual(response.content, b64decode(preview.context['qr_data']))
        self.assertEqual(Order.objects.count(), 0)

    def test_inactive_qr_warning_and_customer_table_context_rejected_then_restored(self):
        context_url = reverse('table-context', args=[self.table.token])
        self.assertEqual(self.client.get(context_url).json()['number'], 'A1')
        self.client.post(self.edit, {'number': 'A1'})
        self.assertEqual(self.client.get(context_url).status_code, 404)
        self.assertContains(self.client.get(self.qr), 'Meja nonaktif')
        self.assertEqual(self.client.get(self.download).status_code, 200)
        self.client.post(self.edit, {'number': 'A1', 'is_active': 'on'})
        self.assertEqual(self.client.get(context_url).status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

    def test_local_host_guidance_and_missing_qr_library_errors(self):
        self.assertTrue(
            self.client.get(self.qr, HTTP_HOST='localhost:8884').context['local_qr_host']
        )

        with patch('users.views._qr_png', side_effect=RuntimeError('QR tidak tersedia.')):
            self.assertRedirects(self.client.get(self.qr), self.url)
            self.assertEqual(self.client.get(self.download).status_code, 503)

    def test_missing_records_and_non_staff_access_do_not_change_tables(self):
        self.assertEqual(self.client.get(reverse('staff:table-qr', args=[99999])).status_code, 404)
        self.client.force_login(get_user_model().objects.create_user('table-ordinary'))

        for url in (self.url, self.edit, self.qr, self.download):
            self.assertEqual(self.client.get(url).status_code, 302)

        self.assertEqual(self.client.post(self.url, {'number': 'Blocked'}).status_code, 302)
        self.assertEqual(self.client.post(self.edit, {'number': 'Blocked'}).status_code, 302)
        self.assertEqual(Table.objects.count(), 1)
