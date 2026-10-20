"""User-selected budget replacement and named references from local feedback."""

from decimal import Decimal
import re
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import TestCase

from menu.models import Category, MenuItem, MenuTag
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from .test_local_conversation import OfflineGenerator


class BudgetReplacementRegressionTests(TestCase):
    def setUp(self) -> None:
        food = Category.objects.create(name='Makanan')
        drinks = Category.objects.create(name='Minuman')
        cold = MenuTag.objects.create(name='cold')
        sweet = MenuTag.objects.create(name='sweet')
        self.items: dict[str, MenuItem] = {}

        for name, price, category in (
            ('Air Putih', 3000, drinks),
            ('Es Jeruk', 10000, drinks),
            ('Es Kelapa', 10000, drinks),
            ('Minuman Mahal', 25000, drinks),
            ('Makanan Hemat', 3000, food),
            ('Ayam Geprek', 18000, food),
            ('Nasi Goreng', 20000, food),
        ):
            self.items[name] = MenuItem.objects.create(
                name=name, price=Decimal(price), category=category
            )

        self.items['Es Jeruk'].tags.add(cold, sweet)
        self.items['Es Kelapa'].tags.add(sweet)
        self.session = SessionStore()
        self.generator = OfflineGenerator()

    def reply(self, text: str) -> dict:
        return ChatbotService(self.session, gemini_client=self.generator).reply(text)

    def test_each_new_nominal_replaces_the_complete_previous_range(self) -> None:
        self.reply('minuman maksimal 15.000')
        lower = self.reply('diatas 5.000')
        self.assertIsNone(lower['active_search']['budget']['maximum'])
        self.assertEqual(lower['active_search']['budget']['minimum'], '5000')
        self.assertFalse(lower['active_search']['budget']['minimum_inclusive'])
        self.assertIn(
            self.items['Minuman Mahal'].pk, {match.item.pk for match in lower['recommendations']}
        )
        cap = self.reply('minuman 10k')
        self.assertIsNone(cap['active_search']['budget']['minimum'])
        self.assertEqual(cap['active_search']['budget']['maximum'], '10000')
        self.assertEqual(
            {match.item.name for match in cap['recommendations']},
            {'Air Putih', 'Es Jeruk', 'Es Kelapa'},
        )

    def test_new_food_budget_does_not_inherit_the_previous_minimum(self) -> None:
        self.reply('minuman diatas 5.000')
        result = self.reply('makanan maksimal 20.000')
        self.assertIsNone(result['active_search']['budget']['minimum'])
        self.assertEqual(
            {match.item.name for match in result['recommendations']},
            {'Makanan Hemat', 'Ayam Geprek', 'Nasi Goreng'},
        )

    def test_explicit_range_in_one_message_keeps_both_bounds(self) -> None:
        self.reply('minimal 30 ribu')
        result = self.reply('minuman antara 5 ribu sampai 10 ribu')
        self.assertEqual(result['active_search']['budget']['minimum'], '5000')
        self.assertEqual(result['active_search']['budget']['maximum'], '10000')
        self.assertEqual(
            {match.item.name for match in result['recommendations']}, {'Es Jeruk', 'Es Kelapa'}
        )

    def test_named_followup_selects_kelapa_not_generic_cold_jeruk(self) -> None:
        self.reply('makanan maksimal 20.000')
        result = self.reply('yang es kelapa')
        self.assertEqual([match.item.name for match in result['recommendations']], ['Es Kelapa'])
        self.assertEqual(self.session[ConversationSession.ENTITY_KEY], [self.items['Es Kelapa'].pk])
        self.assertEqual(self.generator.calls, 0)

    def test_named_followup_still_obeys_budget(self) -> None:
        self.reply('minuman maksimal 5000')
        result = self.reply('yang es kelapa')
        self.assertFalse(result['recommendations'])
        self.assertIn('es kelapa', result['message'].lower())

    def test_generic_and_positional_followups_still_work(self) -> None:
        self.reply('minuman maksimal 10 ribu')
        cold = self.reply('yang dingin')
        self.assertEqual([match.item.name for match in cold['recommendations']], ['Es Jeruk'])
        self.assertEqual(
            [match.item.name for match in self.reply('yang terakhir')['recommendations']],
            ['Es Jeruk'],
        )

    def test_drink_summary_does_not_duplicate_category_name(self) -> None:
        result = self.reply('minuman 10k')
        self.assertEqual(len(re.findall(r'\bminuman\b', result['message'].lower())), 1)

    def test_invalid_new_range_preserves_previous_budget(self) -> None:
        self.reply('minuman maksimal 10 ribu')
        saved = dict(self.session[ConversationSession.SEARCH_KEY])
        result = self.reply('minimal 20 ribu maksimal 10 ribu')
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.session[ConversationSession.SEARCH_KEY], saved)

    def test_http_payload_uses_replaced_bounds_and_exact_name(self) -> None:
        with patch('recommendation.services.gemini.GeminiClient.generate', return_value=None):
            for message in (
                'minuman maksimal 15000',
                'diatas 5000',
                'minuman 10k',
                'yang es kelapa',
            ):
                response = self.client.post(
                    '/api/recommendation/chat/',
                    {'message': message},
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual([item['name'] for item in body['recommendations']], ['Es Kelapa'])
        self.assertIsNone(body['active_search']['budget']['minimum'])
        self.assertEqual(body['active_search']['budget']['maximum'], '10000')
