"""Price formats through the real conversation pipeline, not just the parser."""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase

from menu.models import Category, MenuItem, MenuTag
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.entity_resolver import EntityResolver
from ..services.language import IndonesianPriceParser
from .test_local_conversation import OfflineGenerator


class PriceContextRegressionTests(SimpleTestCase):
    def test_plain_rupiah_amount_in_food_context_is_a_budget(self) -> None:
        parser = IndonesianPriceParser()
        for text in ('minuman 10000', 'aku mau minuman 10000', 'menu 10000', 'es jeruk 10000'):
            with self.subTest(text=text):
                self.assertEqual(parser.parse_maximum(text), 10000)

    def test_price_is_not_part_of_generic_or_exact_requested_entity(self) -> None:
        resolver = EntityResolver(((1, 'Es Jeruk'),), ('minuman', 'drink'))
        for price in ('10k', '10 ribu', '10000', '10.000', 'Rp10.000', '10 rupiah'):
            with self.subTest(price=price):
                self.assertIsNone(resolver.resolve('aku mau minuman ' + price))
                self.assertEqual(resolver.resolve('aku mau es jeruk ' + price).menu_ids, (1,))

    def test_nonmoney_numbers_remain_nonmoney_in_food_context(self) -> None:
        parser = IndonesianPriceParser()
        for text in ('minuman 10000 ml', 'menu rating 4.5', 'minuman jam 20:30',
                     'minuman meja 10000', 'minuman nomor 10000', 'menu ke 2'):
            with self.subTest(text=text):
                self.assertIsNone(parser.parse(text).constraint)
        self.assertEqual(parser.parse_maximum('minuman 10 rupiah'), 10)


class PriceConversationRegressionTests(TestCase):
    def setUp(self) -> None:
        food = Category.objects.create(name='Makanan')
        drinks = Category.objects.create(name='Minuman')
        drink_tag = MenuTag.objects.create(name='drink')
        rice_tag = MenuTag.objects.create(name='rice')
        self.drinks: list[MenuItem] = []
        for name in ('Es Jeruk', 'Es Kelapa'):
            item = MenuItem.objects.create(name=name, price=Decimal(10000), category=drinks)
            item.tags.add(drink_tag)
            self.drinks.append(item)
        expensive = MenuItem.objects.create(name='Minuman Mahal', price=Decimal(15000), category=drinks)
        expensive.tags.add(drink_tag)
        rice = MenuItem.objects.create(name='Nasi Goreng', price=Decimal(20000), category=food)
        rice.tags.add(rice_tag)
        self.session = SessionStore()
        self.generator = OfflineGenerator()

    def reply(self, text: str) -> dict:
        return ChatbotService(self.session, gemini_client=self.generator).reply(text)

    def assert_two_drinks(self, result: dict) -> None:
        self.assertEqual({match.item.pk for match in result['recommendations']}, {item.pk for item in self.drinks})
        self.assertEqual(result['active_search']['budget']['maximum'], '10000')

    def test_all_ten_thousand_formats_recommend_both_equal_price_drinks(self) -> None:
        for price in ('10k', '10 ribu', '10000', '10.000', 'Rp10.000', '10rb'):
            for prefix in ('minuman ', 'aku mau minuman '):
                with self.subTest(price=price, prefix=prefix):
                    self.session = SessionStore()
                    self.assert_two_drinks(self.reply(prefix + price))

    def test_ten_rupiah_is_literal_and_later_grouped_price_replaces_it(self) -> None:
        result = self.reply('minuman 10 rupiah')
        self.assertFalse(result['recommendations'])
        self.assertEqual(result['active_search']['max_price'], 10)
        self.assert_two_drinks(self.reply('aku mau minuman 10.000'))

    def test_new_drink_request_does_not_inherit_food_budget(self) -> None:
        first = self.reply('makanan 10 ribu ada ga')
        self.assertFalse(first['recommendations'])
        self.assertEqual(first['active_search']['max_price'], 10000)
        result = self.reply('kalau gitu minuman aja')
        self.assertEqual({match.item.name for match in result['recommendations']}, {'Es Jeruk', 'Es Kelapa', 'Minuman Mahal'})
        self.assertIsNone(result['active_search']['max_price'])
        self.assertEqual(self.session[ConversationSession.CONTEXTS_KEY]['previous'][-1]['constraints']['budget']['maximum'], '10000')

    def test_exact_name_with_price_and_then_generic_drink_clears_identity_scope(self) -> None:
        first = self.reply('aku mau es jeruk 10.000')
        self.assertEqual([match.item.name for match in first['recommendations']], ['Es Jeruk'])
        self.assertIn(ConversationSession.ENTITY_KEY, self.session)
        self.assert_two_drinks(self.reply('aku mau minuman 10000'))
        self.assertNotIn(ConversationSession.ENTITY_KEY, self.session)

    def test_new_plain_budget_updates_previous_cap(self) -> None:
        self.reply('minuman budget 20000')
        self.assert_two_drinks(self.reply('minuman 10000'))

    def test_unavailable_and_inactive_menu_still_do_not_leak(self) -> None:
        self.drinks[1].is_available = False
        self.drinks[1].save(update_fields=['is_available'])
        result = self.reply('minuman 10k')
        self.assertEqual([match.item.name for match in result['recommendations']], ['Es Jeruk'])
        self.drinks[0].is_active = False
        self.drinks[0].save(update_fields=['is_active'])
        self.assertFalse(self.reply('minuman 10.000')['recommendations'])

    def test_http_budget_correction_returns_both_cards_in_the_browser_payload(self) -> None:
        with patch('recommendation.services.gemini.GeminiClient.generate', return_value=None):
            for price in ('10k', '10 rupiah', '10000', '10.000'):
                with self.subTest(price=price):
                    response = self.client.post('/api/recommendation/chat/',
                                                {'message': 'aku mau minuman ' + price},
                                                content_type='application/json')
                    self.assertEqual(response.status_code, 200)
                    body = response.json()
                    expected_max = 10 if price == '10 rupiah' else 10000
                    self.assertEqual(body['active_search']['max_price'], expected_max)
                    expected_names = set() if price == '10 rupiah' else {'Es Jeruk', 'Es Kelapa'}
                    self.assertEqual({item['name'] for item in body['recommendations']}, expected_names)
