"""Phase6 expression stays bounded by current verified business facts."""
from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase

from menu.models import Category,MenuItem,MenuTag,VariantGroup
from ..services.budget import BudgetConstraint
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.recommendation import SearchConstraints
from ..services.response_composer import LocalResponseComposer
from ..services.response_plan import ResponsePlan
from ..services.tag_extractor import Preferences
from .test_budget import NoBudgetProvider


class NaturalWordingTests(SimpleTestCase):
    def compose(self,criteria,preferences=None):
        return LocalResponseComposer(SessionStore()).compose(ResponsePlan('recommendation',[],preferences or Preferences(),constraints=criteria))

    def test_category_dedup_and_no_semicolon_field_list(self):
        text=self.compose(SearchConstraints(category='Minuman',required_tags=frozenset({'drink','cold'}),budget=BudgetConstraint(maximum=Decimal(10000))))
        self.assertEqual(text.casefold().count('minuman'),1)
        self.assertNotIn(';',text)
        self.assertIn('maksimal Rp10.000',text)
        self.assertNotIn(',00',text)
        self.assertIn('dingin',text)

    def test_fractional_rupiah_is_preserved(self):
        text=self.compose(SearchConstraints(budget=BudgetConstraint(maximum=Decimal('10000.50'))))
        self.assertIn('Rp10.000,50',text)

    def test_price_range_preserves_exclusive_bounds(self):
        text=self.compose(SearchConstraints(budget=BudgetConstraint(minimum=Decimal(5000),maximum=Decimal(10000),minimum_inclusive=False)))
        self.assertIn('lebih dari Rp5.000',text)
        self.assertIn('maksimal Rp10.000',text)

    def test_approximate_is_not_maximum_claim(self):
        text=self.compose(SearchConstraints(category='Makanan',soft_target=Decimal(20000)))
        self.assertIn('mendekati Rp20.000',text)
        self.assertIn('bukan batas maksimum',text)

    def test_exclusion_is_request_not_allergen_free_claim(self):
        text=self.compose(SearchConstraints(excluded_tags=frozenset({'shrimp'})))
        self.assertIn('menghindari udang',text)
        self.assertNotIn('bebas',text)
        self.assertNotIn('aman',text)

    def test_soft_preference_and_empty_criteria_are_natural(self):
        text=self.compose(SearchConstraints(),Preferences(prefer_affordable=True))
        self.assertIn('hemat',text)
        self.assertNotIn('required_tags',text)


class RecoveryWordingTests(TestCase):
    def setUp(self):
        self.food=Category.objects.create(name='Makanan');self.drink=Category.objects.create(name='Minuman')
        self.rice=MenuItem.objects.create(name='Nasi Goreng',category=self.food,price=20000)
        self.juice=MenuItem.objects.create(name='Es Jeruk',category=self.drink,price=10000)
        self.session=SessionStore();self.provider=NoBudgetProvider()
    def reply(self,text):return ChatbotService(self.session,gemini_client=self.provider).reply(text)
    def graph(self):return ConversationSession(self.session).contexts()

    def test_unavailable_exact_name_without_invented_reason(self):
        self.juice.is_available=False;self.juice.save()
        result=self.reply('es jeruk')
        self.assertIn('Es Jeruk belum tersedia',result['message'])
        self.assertIn('minuman lain',result['message'])
        for reason in ('habis','stok','tutup','rusak'):self.assertNotIn(reason,result['message'])
        self.assertFalse(result['recommendations'])

    def test_inactive_category_is_unavailable_not_fake_absent_menu(self):
        self.drink.is_active=False;self.drink.save()
        result=self.reply('es jeruk')
        self.assertIn('Es Jeruk belum tersedia',result['message'])

    def test_required_variants_missing_has_specific_reason(self):
        VariantGroup.objects.create(menu_item=self.rice,name='Porsi',is_required=True)
        self.reply('budget total 30k')
        result=self.reply('nasi goreng')
        self.assertIn('varian wajib',result['message'])
        self.assertIn('Nasi Goreng',result['message'])

    def test_total_conflict_only_verified_amounts_and_no_partial_commit(self):
        self.reply('budget total 30k');self.reply('nasi goreng');self.reply('sekalian es jeruk')
        before=deepcopy(self.graph()['plan'])
        result=self.reply('sekalian es jeruk')
        self.assertIn('Rp40.000',result['message'])
        self.assertIn('Rp30.000',result['message'])
        self.assertIn('lebih terjangkau',result['message'])
        self.assertEqual(self.graph()['plan'],before)
        self.assertEqual(result['message'].count('?'),1)

    def test_category_conflict_shows_computed_sum_and_declared_cap(self):
        self.reply('alokasi makanan 20k dan minuman 10k');self.reply('nasi goreng')
        result=self.reply('sekalian nasi goreng')
        self.assertIn('Rp40.000',result['message'])
        self.assertIn('Rp20.000',result['message'])
        self.assertIn('alokasi',result['message'])

    def test_known_people_count_does_not_get_asked_again(self):
        result=self.reply('budget 40k untuk 2 orang')
        self.assertNotIn('Berapa orang',result['message'])
        self.assertIn('berbagi',result['message'])
        self.assertEqual(result['message'].count('?'),1)

    def test_missing_people_count_asks_only_count_first(self):
        result=self.reply('budget 20k per orang')
        self.assertIn('Berapa orang',result['message'])
        self.assertNotIn('berbagi',result['message'])

    def test_known_serving_mode_count_update_does_not_repeat_sharing_question(self):
        self.reply('40 ribu untuk 2 orang masing-masing mau makan')
        result=self.reply('jadi 3 orang')
        self.assertNotIn('berbagi',result['message'])
        self.assertEqual(self.graph()['overall']['person_count'],3)

    def test_unknown_input_preserves_valid_search_and_total_then_new_menu_recovers(self):
        self.reply('budget total 30k');self.reply('minuman maksimal 10k')
        before=deepcopy(self.graph()['overall']);search=ConversationSession(self.session).load_constraints().to_dict()
        self.reply('aku mau barang zzzq')
        self.assertEqual(self.graph()['overall'],before)
        self.assertEqual(ConversationSession(self.session).load_constraints().to_dict(),search)
        result=self.reply('nasi goreng')
        self.assertEqual([match.item.pk for match in result['recommendations']],[self.rice.pk])

    def test_local_wording_requires_no_provider(self):
        result=self.reply('minuman maksimal 10k')
        self.assertNotIn(';',result['message'])
        self.assertEqual(self.provider.calls,0)
