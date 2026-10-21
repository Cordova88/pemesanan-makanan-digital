"""Regressions from the user's local, no-Gemini conversation screenshots."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import TestCase

from menu.models import Category, MenuItem, MenuTag
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.entity_resolver import EntityResolver
from ..services.language import tag_label
from ..services.tag_extractor import Preferences
from ..services.text_generator import TextGenerator


class OfflineGenerator(TextGenerator):
    def __init__(self) -> None:
        self.calls: int = 0

    def generate(self, prompt: str) -> str | None:
        self.calls += 1

        return None


class LocalConversationRegressionTests(TestCase):
    def setUp(self) -> None:
        food = Category.objects.create(name='Makanan')
        drinks = Category.objects.create(name='Minuman')
        tags = {
            name: MenuTag.objects.create(name=name)
            for name in ('rice', 'fried_rice', 'chicken', 'drink', 'filling', 'spicy')
        }
        self.items: dict[str, MenuItem] = {}

        for name, price, category, names in (
            ('Nasi Goreng', 20000, food, ('rice', 'fried_rice', 'filling')),
            ('Ayam Geprek', 18000, food, ('chicken', 'spicy')),
            ('Es Jeruk', 10000, drinks, ('drink',)),
        ):
            item = MenuItem.objects.create(name=name, price=Decimal(price), category=category)
            item.tags.add(*(tags[name] for name in names))
            self.items[name] = item

        self.session = SessionStore()
        self.generator = OfflineGenerator()

    def reply(self, text: str) -> dict:
        return ChatbotService(self.session, gemini_client=self.generator).reply(text)

    def test_compound_purchase_verbs_identify_the_object_offline(self) -> None:
        resolver = EntityResolver(())

        for text, entity, status in (
            ('aku mau beli mobil', 'mobil', 'NON_FOOD_OUT_OF_SCOPE'),
            ('mau beli mobil', 'mobil', 'NON_FOOD_OUT_OF_SCOPE'),
            ('ada bantal?', 'bantal', 'NON_FOOD_OUT_OF_SCOPE'),
            ('aku mau beli tepung', 'tepung', 'FOOD_BUT_NOT_AVAILABLE'),
        ):
            with self.subTest(text=text):
                result = resolver.resolve(text)
                self.assertIsNotNone(result)
                self.assertEqual((result.requested_entity, result.domain_status), (entity, status))

    def test_catalog_identity_still_precedes_offline_examples(self) -> None:
        resolver = EntityResolver(((123, 'Tepung'), (456, 'Bantal')))
        self.assertEqual(resolver.resolve('aku mau beli tepung').menu_ids, (123,))
        self.assertEqual(resolver.resolve('ada bantal?').menu_ids, (456,))
        self.assertEqual(
            EntityResolver(()).resolve('ada glorp?').domain_status, 'AMBIGUOUS_REQUEST'
        )

    def test_known_out_of_scope_objects_do_not_need_provider_classification(self) -> None:
        for text, entity in (
            ('aku ingin motor', 'motor'),
            ('mau beli mobil', 'mobil'),
            ('ada bantal?', 'bantal'),
        ):
            with self.subTest(text=text):
                result = self.reply(text)
                self.assertIn(entity, result['message'].lower())
                self.assertNotIn('Boleh jelaskan', result['message'])
                self.assertFalse(result['recommendations'])

        self.assertEqual(self.generator.calls, 0)

    def test_reopening_existing_session_greets_without_clearing_budget_or_references(self) -> None:
        first = self.reply('nasi maksimal 20 ribu')
        search = dict(self.session[ConversationSession.SEARCH_KEY])
        ids = list(self.session.get('last_recommendations', []))
        result = self.reply('')
        self.assertTrue(first['recommendations'])
        self.assertNotIn('belum menangkap', result['message'])
        self.assertIn('menu', result['message'].lower())
        self.assertEqual(self.session[ConversationSession.SEARCH_KEY], search)
        self.assertEqual(self.session.get('last_recommendations', []), ids)
        self.assertEqual(
            result['preferences']['tags'], self.session[ConversationSession.STATE_KEY]['tags']
        )

    def test_new_drink_scope_archives_food_budget_and_local_exclusion(self) -> None:
        self.reply('nasi maksimal 20 ribu')
        # Reproduce older-session tags seen in the screenshots, including no category.
        self.session[ConversationSession.STATE_KEY] = Preferences(
            tags={'rice', 'fried_rice', 'filling', 'chicken', 'drink'},
        ).to_dict(state='RECOMMENDING')
        self.reply('jangan pedas')
        self.reply('10 ribu ayam')
        result = self.reply('sekarang cari minuman')
        self.assertEqual([match.item.name for match in result['recommendations']], ['Es Jeruk'])
        self.assertIsNone(result['active_search']['max_price'])
        self.assertNotIn('spicy', result['active_search']['excluded_tags'])
        archived = self.session[ConversationSession.CONTEXTS_KEY]['previous'][-1]['constraints']
        self.assertEqual(archived['budget']['maximum'], '10000')
        self.assertIn('spicy', archived['excluded_tags'])
        self.assertEqual(set(result['preferences']['tags']), {'drink'})
        self.assertEqual(set(self.session[ConversationSession.STATE_KEY]['tags']), {'drink'})

    def test_other_request_with_no_remaining_results_explains_exhaustion(self) -> None:
        self.reply('minuman maksimal 10 ribu')
        result = self.reply('yang lain')
        self.assertFalse(result['recommendations'])
        self.assertIn('belum ada menu lain', result['message'].lower())
        self.assertIn('batas', result['message'].lower())
        self.assertEqual(result['active_search']['max_price'], 10000)
        self.assertIn(self.items['Es Jeruk'].pk, self.session[ConversationSession.SHOWN_KEY])
        self.assertFalse(self.session.get(ConversationSession.REJECTED_KEY))

    def test_reference_without_previous_cards_asks_for_an_anchor(self) -> None:
        self.reply('halo')
        result = self.reply('yang terakhir')
        self.assertFalse(result['recommendations'])
        self.assertIn('sebelumnya', result['message'])
        self.assertNotIn('belum menangkap', result['message'])
        self.assertEqual(self.generator.calls, 0)

    def test_tiny_budget_stays_active_until_explicit_change(self) -> None:
        result = self.reply('budget 1 rupiah')
        self.assertFalse(result['recommendations'])
        # V3.2: a fresh bare budget needs an explicit per-menu/total answer.
        self.assertIn('per menu', result['message'])
        self.reply('per menu')
        result = self.reply('jangan pedas')
        self.assertFalse(result['recommendations'])
        self.assertEqual(result['active_search']['max_price'], 1)
        self.assertIn('spicy', result['active_search']['excluded_tags'])
        result = self.reply('10 ribu ayam')
        self.assertFalse(result['recommendations'])
        self.assertEqual(result['active_search']['max_price'], 10000)

    def test_http_sequence_exposes_current_chips_and_explains_no_more_cards(self) -> None:
        with patch('recommendation.services.gemini.GeminiClient.generate', return_value=None):
            for text in (
                '',
                'halo',
                'hi',
                'makan dengan budget 20000',
                'budget 1 rupiah',
                'aku ingin motor',
                'aku mau beli tepung',
                'mau beli mobil',
                'ada bantal?',
                'jangan pedas',
                '10 ribu ayam',
                'sekarang cari minuman',
            ):
                response = self.client.post(
                    '/api/recommendation/chat/', {'message': text}, content_type='application/json'
                )
                self.assertEqual(response.status_code, 200, text)

            body = response.json()
            self.assertEqual([item['name'] for item in body['recommendations']], ['Es Jeruk'])
            self.assertEqual(body['preferences']['tags'], [tag_label('drink')])
            self.assertIsNone(body['active_search']['max_price'])
            response = self.client.post(
                '/api/recommendation/chat/',
                {'message': 'yang lain'},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['recommendations'])
        self.assertIn('belum ada menu lain', response.json()['message'].lower())
