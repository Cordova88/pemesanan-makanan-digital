"""Conversational-only UI retains backend preference compatibility."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from menu.models import Category, MenuItem, MenuTag
from orders.models import Order


@override_settings(GEMINI_ENABLED=False)
class ChipRemovalTests(TestCase):
    def setUp(self):
        food = Category.objects.create(name='Makanan')
        drink = Category.objects.create(name='Minuman')
        spicy = MenuTag.objects.create(name='spicy')
        item = MenuItem.objects.create(name='Ayam Geprek', category=food, price=20000)
        item.tags.add(spicy)
        MenuItem.objects.create(name='Es Jeruk', category=drink, price=10000)

    def test_page_removes_obsolete_renderer_container_handlers_and_keeps_controls(self):
        response = self.client.get('/chatbot/')
        self.assertEqual(response.status_code, 200)
        text = response.content.decode()

        for obsolete in (
            'renderPreferences',
            'id="preferences"',
            'preference-chip',
            'Hapus preferensi',
        ):
            self.assertNotIn(obsolete, text)

        for control in (
            'id="input"',
            'id="send"',
            'id="reset"',
            'chat-quick-replies',
            'chat-recommendation',
            'X-CSRFToken',
            'aria-busy',
            'aria-live="polite"',
        ):
            self.assertIn(control, text)

    def test_exclusive_chip_css_removed_while_catalog_category_css_remains(self):
        root = Path(settings.BASE_DIR) / 'menu/static/menu/css'
        retro = (root / 'retro.css').read_text(encoding='utf-8')
        page = (root / 'page4.css').read_text(encoding='utf-8')

        for css in (retro, page):
            self.assertNotIn('.chat-preferences', css)
            self.assertNotIn('.preference-chip', css)

        self.assertIn('.category-chip', retro)
        self.assertIn('@media(max-width:359px)', retro)

    def test_chat_revisions_switch_and_legacy_remove_commands_still_work(self):
        with patch('google.genai.Client', side_effect=AssertionError('No SDK')):
            for message in (
                'makanan pedas maksimal 25k',
                'gak jadi pedas',
                'hapus preferensi pedas',
                'minuman maksimal 10k',
            ):
                response = self.client.post(
                    '/api/recommendation/chat/',
                    {'message': message},
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 200)

        self.assertEqual(response.json()['active_search']['category'], 'Minuman')
        self.assertEqual(response.json()['active_search']['max_price'], 10000)
        self.assertEqual(Order.objects.count(), 0)
        self.assertNotIn('cart', self.client.session)
