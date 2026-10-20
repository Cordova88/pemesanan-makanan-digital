"""A confirmed Minuman category must not require a duplicate drink tag."""
from decimal import Decimal

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import TestCase

from menu.models import Category, MenuItem, MenuTag
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.recommendation import RecommendationService, SearchConstraints
from ..services.tag_extractor import Preferences
from .test_local_conversation import OfflineGenerator


class DrinkCategoryRegressionTests(TestCase):
    def setUp(self) -> None:
        self.category = Category.objects.create(name='Minuman')
        self.food = Category.objects.create(name='Makanan')
        self.drink = MenuTag.objects.create(name='drink')
        self.sweet = MenuTag.objects.create(name='sweet')
        self.jeruk = MenuItem.objects.create(name='Es Jeruk', category=self.category, price=Decimal(10000))
        self.jeruk.tags.add(self.drink, self.sweet)
        self.kelapa = MenuItem.objects.create(name='Es Kelapa', category=self.category, price=Decimal(10000))
        self.kelapa.tags.add(self.sweet)  # Match screenshot: Manis only, no drink tag.
        self.food_item = MenuItem.objects.create(name='Roti Manis', category=self.food, price=Decimal(10000))
        self.food_item.tags.add(self.sweet)
        self.session = SessionStore()
        self.generator = OfflineGenerator()

    def reply(self, text: str) -> dict:
        return ChatbotService(self.session, gemini_client=self.generator).reply(text)

    def names(self, result: dict) -> set[str]:
        return {match.item.name for match in result['recommendations']}

    def test_general_drinks_include_both_despite_missing_duplicate_tag(self) -> None:
        result = self.reply('aku mau minuman 10.000')
        self.assertEqual(self.names(result), {'Es Jeruk', 'Es Kelapa'})
        self.assertEqual(result['active_search']['max_price'], 10000)
        self.assertEqual(set(self.kelapa.tags.values_list('name', flat=True)), {'sweet'})

    def test_catalog_question_uses_the_same_category_semantics(self) -> None:
        result = self.reply('ada minuman maksimal 10 ribu?')
        self.assertTrue(result['catalog_question'])
        self.assertEqual(self.names(result), {'Es Jeruk', 'Es Kelapa'})

    def test_older_session_rejecting_jeruk_can_still_find_kelapa(self) -> None:
        state = ConversationSession(self.session)
        state.save_preferences(Preferences(tags={'drink'}), 'RECOMMENDING')
        state.save_search(SearchConstraints(frozenset({'drink'}), category='Minuman', max_price=10000))
        state.record_recommendations([self.jeruk.pk], shown_ids=[self.jeruk.pk])
        result = self.reply('tidak cocok')
        self.assertEqual(self.names(result), {'Es Kelapa'})
        self.assertIn(self.jeruk.pk, state.get_explicit_rejections())

    def test_reference_selection_accepts_category_evidence(self) -> None:
        result = self.reply('minuman 10k')
        self.assertEqual(len(result['recommendations']), 2)
        result = self.reply('yang kedua')
        self.assertEqual(self.names(result), {'Es Kelapa'})

    def test_specific_flavor_still_requires_the_actual_tag(self) -> None:
        plain = MenuItem.objects.create(name='Air Putih', category=self.category, price=Decimal(5000))
        result = RecommendationService().rank(Preferences(tags={'drink', 'sweet'}),
            constraints=SearchConstraints(frozenset({'drink', 'sweet'}), category='Minuman', max_price=10000))
        self.assertEqual({match.item.pk for match in result}, {self.jeruk.pk, self.kelapa.pk})
        self.assertNotIn(plain.pk, {match.item.pk for match in result})

    def test_drink_category_also_applies_to_hard_drink_exclusion(self) -> None:
        result = RecommendationService().rank(Preferences(excluded_tags={'drink'}),
            constraints=SearchConstraints(frozenset({'sweet'}), max_price=10000))
        self.assertEqual({match.item.pk for match in result}, {self.food_item.pk})

    def test_budget_and_availability_remain_hard_filters(self) -> None:
        self.kelapa.price = Decimal(10001)
        self.kelapa.save(update_fields=['price'])
        self.assertEqual(self.names(self.reply('minuman 10k')), {'Es Jeruk'})
        self.kelapa.price = Decimal(10000)
        self.kelapa.is_available = False
        self.kelapa.save(update_fields=['price', 'is_available'])
        self.assertEqual(self.names(self.reply('minuman 10k')), {'Es Jeruk'})
        self.category.is_active = False
        self.category.save(update_fields=['is_active'])
        self.assertFalse(self.reply('minuman 10k')['recommendations'])

    def test_http_payload_includes_kelapa_without_inventing_catalog_tags(self) -> None:
        response = self.client.post('/api/recommendation/chat/',
                                    {'message': 'aku mau minuman 10.000'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        cards = {item['name']: item for item in response.json()['recommendations']}
        self.assertEqual(set(cards), {'Es Jeruk', 'Es Kelapa'})
        self.assertEqual(cards['Es Kelapa']['labels'], ['🍯 Manis'])
