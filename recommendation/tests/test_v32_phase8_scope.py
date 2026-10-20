"""Acceptance counterexamples: total quantities and explicit per-person caps."""

from copy import deepcopy
from decimal import Decimal
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase
from menu.models import Category, MenuItem
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.language import IndonesianPriceParser
from ..services.plan_interpreter import PlanInterpreter
from .test_budget import NoBudgetProvider


class ScopeLanguageTests(SimpleTestCase):
    def setUp(self):
        self.interpreter = PlanInterpreter(IndonesianPriceParser(), ['Makanan', 'Minuman'])

    def test_money_before_category_quantity_has_total_scope(self):
        for text in ('20rb untuk dua minuman', 'budget Rp20.000 buat 2 minuman'):
            with self.subTest(text=text):
                delta = self.interpreter.interpret(text)
                self.assertEqual(delta.total_budget, Decimal(20000))
                self.assertEqual(delta.role_quantities, {'Minuman': 2})
                self.assertIsNone(delta.quantity)

    def test_money_before_named_quantity_retains_unique_identity(self):
        for text in ('20rb untuk dua es jeruk', 'Rp20.000 buat 2 gelas es jeruk'):
            with self.subTest(text=text):
                delta = self.interpreter.interpret(text)
                self.assertEqual(delta.quantity, 2)
                self.assertEqual(delta.implicit_total, Decimal(20000))
                self.assertIn('es jeruk', delta.entity_text)
                self.assertNotIn('20', delta.entity_text)

    def test_individual_money_is_per_person_not_a_new_total(self):
        delta = self.interpreter.interpret('masing-masing 20rb ya')
        self.assertEqual(delta.per_person_budget, Decimal(20000))
        self.assertEqual(delta.serving_mode, 'individual')
        self.assertIsNone(delta.total_budget)

    def test_people_and_nonmoney_are_never_reordered_as_items(self):
        for text in ('20rb untuk dua orang', 'uang bulananku 2 juta', 'jam 20 untuk dua minuman'):
            delta = self.interpreter.interpret(text)
            self.assertIsNone(delta.quantity)
            self.assertIsNone(delta.implicit_total)

    def test_explicit_unit_scope_is_not_promoted_to_total(self):
        delta = self.interpreter.interpret('20rb untuk dua minuman per menu')
        self.assertIsNone(delta.total_budget)
        self.assertEqual(delta.role_quantities, {'Minuman': 2})

    def test_named_unit_scope_preserves_amount_for_the_price_parser(self):
        delta = self.interpreter.interpret('20rb untuk dua es kelapa per menu')
        parsed = IndonesianPriceParser().parse(delta.entity_text)
        self.assertEqual(parsed.constraint.maximum, Decimal(20000))
        self.assertIsNone(delta.implicit_total)

    def test_negative_linked_quantities_are_clarified(self):
        for text in ('20rb untuk -2 minuman', '20rb untuk -2 es jeruk'):
            self.assertIsNotNone(self.interpreter.interpret(text).clarification)

    def test_linked_per_person_request_does_not_become_total(self):
        for text in ('20rb untuk dua minuman per orang', '20rb untuk dua es jeruk per orang'):
            delta = self.interpreter.interpret(text)
            self.assertIsNotNone(delta.clarification)
            self.assertIsNone(delta.implicit_total)


class ScopeEndpointLogicTests(TestCase):
    def setUp(self):
        self.food = Category.objects.create(name='Makanan')
        self.drinks = Category.objects.create(name='Minuman')
        self.jeruk = MenuItem.objects.create(name='Es Jeruk', price=10000, category=self.drinks)
        self.kelapa = MenuItem.objects.create(name='Es Kelapa', price=12000, category=self.drinks)
        self.ayam = MenuItem.objects.create(name='Ayam Geprek', price=30000, category=self.food)
        self.session = SessionStore()

    def reply(self, text):
        return ChatbotService(self.session, gemini_client=NoBudgetProvider()).reply(text)

    def graph(self):
        return ConversationSession(self.session).contexts()

    def test_category_quantity_total_selects_plan_and_rejects_overpriced_replacement(self):
        self.reply('20rb untuk dua minuman')
        graph = self.graph()
        self.assertEqual(graph['overall']['total_budget'], '20000')
        self.assertEqual(graph['plan']['role_quantities'], {'Minuman': 2})
        self.assertNotIn('Minuman', graph['plan']['unresolved_roles'])
        before = deepcopy(graph['plan'])
        self.assertEqual(before['entries'][0]['menu_id'], self.jeruk.pk)
        self.assertEqual(before['entries'][0]['quantity'], 2)
        self.assertIsNone(graph['active']['constraints'].get('budget'))
        result = self.reply('es kelapa')
        self.assertFalse(result['recommendations'])  # 2 x 12000 exceeds combined20000.
        self.assertEqual(self.graph()['plan'], before)
        self.reply('es jeruk')
        self.assertEqual(self.graph()['plan']['entries'][0]['quantity'], 2)

    def test_named_quantity_total_rejects_overpriced_pair(self):
        for text in ('20rb untuk dua es jeruk', '20rb untuk dua es kelapa'):
            with self.subTest(text=text):
                self.session = SessionStore()
                result = self.reply(text)

                if 'jeruk' in text:
                    self.assertEqual({r.item.name for r in result['recommendations']}, {'Es Jeruk'})
                    self.assertEqual(self.graph()['overall']['total_budget'], '20000')
                    self.assertEqual(self.graph()['plan']['entries'][0]['quantity'], 2)
                else:
                    self.assertFalse(result['recommendations'])
                    self.assertFalse(self.graph()['plan']['entries'])

    def test_per_person_correction_preserves_explicit_total_and_people(self):
        self.reply('40rb untuk 2 orang')
        self.reply('masing-masing 20rb ya')
        graph = self.graph()
        self.assertEqual(graph['overall']['total_budget'], '40000')
        self.assertEqual(graph['overall']['per_person_budget'], '20000')
        self.assertEqual(graph['overall']['person_count'], 2)
        self.assertEqual(graph['plan']['serving_mode'], 'individual')
        self.assertFalse(graph['plan']['entries'])
        self.assertFalse(self.reply('ayam geprek')['recommendations'])  # Per-person cap20k.

    def test_invalid_per_person_update_rolls_back_mode_and_plan(self):
        self.reply('budget total 60k untuk 2 orang')
        self.reply('masing-masing 30k')
        self.reply('ayam geprek')
        before = deepcopy(self.graph())
        result = self.reply('masing-masing 10k')
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.graph()['overall'], before['overall'])
        self.assertEqual(self.graph()['plan'], before['plan'])

    def test_makan_saja_filters_category_without_drink_results(self):
        result = self.reply('budget 30rb buat makan saja')
        self.assertTrue(result['recommendations'])
        self.assertEqual({r.item.category.name for r in result['recommendations']}, {'Makanan'})
        self.assertEqual(self.graph()['active']['category'], 'Makanan')

    def test_multiple_amounts_never_guess_a_total_for_named_quantity(self):
        result = self.reply('20rb untuk dua es jeruk budget 10rb')
        self.assertFalse(result['recommendations'])
        self.assertFalse(self.graph()['plan']['entries'])

    def test_explicit_unit_cap_retains_role_quantity_without_total(self):
        self.reply('20rb untuk dua minuman per menu')
        graph = self.graph()
        self.assertNotIn('total_budget', graph['overall'])
        self.assertEqual(graph['active']['constraints']['budget']['maximum'], '20000')
        self.assertEqual(graph['plan']['role_quantities'], {'Minuman': 2})
        result = self.reply('es kelapa')
        self.assertTrue(result['recommendations'])  # Two12000 items valid under unit cap20k.
        self.assertEqual(self.graph()['plan']['entries'][0]['quantity'], 2)

    def test_invalid_or_unbound_linked_scope_never_commits_plan(self):
        for text in (
            '20rb untuk -2 minuman',
            '20rb untuk -2 es jeruk',
            '20rb untuk dua minuman per orang',
            '20rb untuk dua es jeruk per orang',
        ):
            with self.subTest(text=text):
                self.session = SessionStore()
                result = self.reply(text)
                self.assertFalse(result['recommendations'])
                self.assertFalse(self.graph()['plan']['entries'])
                self.assertFalse(self.graph()['overall'])

    def test_named_unit_scope_rejects_an_item_above_its_explicit_cap(self):
        accepted = self.reply('20rb untuk dua es kelapa per menu')
        self.assertTrue(accepted['recommendations'])
        self.assertEqual(self.graph()['plan']['entries'][0]['quantity'], 2)
        self.assertNotIn('total_budget', self.graph()['overall'])
        self.session = SessionStore()
        self.kelapa.price = 25000
        self.kelapa.save(update_fields=['price'])
        result = self.reply('20rb untuk dua es kelapa per menu')
        self.assertFalse(result['recommendations'])
        self.assertFalse(self.graph()['plan']['entries'])
