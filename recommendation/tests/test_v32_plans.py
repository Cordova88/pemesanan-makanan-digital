"""Phase 3: independent people/quantity/role updates in an isolated draft plan."""

from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase

from menu.models import Category, MenuItem, MenuTag, VariantGroup, VariantOption
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.conversation_store import ConversationStore, ConversationStoreUnavailable
from ..services.language import IndonesianPriceParser
from ..services.plan_interpreter import PlanInterpreter
from ..services.recommendation import SearchConstraints
from .test_budget import NoBudgetProvider


class PlanLanguageTests(SimpleTestCase):
    def test_category_allocations_bind_on_either_side_of_money(self) -> None:
        for text in (
            '20rb makan dan 10rb minum',
            '20rb buat makan, 10rb buat minum.',
            'Makan 20k, minum 10k.',
            'Untuk minuman 10rb, makanan 20rb.',
            '30rb total, 20rb makanan dan 10rb minuman.',
        ):
            with self.subTest(text=text):
                delta = self.interpreter.interpret(text)
                self.assertIsNone(delta.clarification)
                self.assertEqual(delta.category_budgets, {'Makanan': '20000', 'Minuman': '10000'})
                self.assertTrue(delta.combination_request)
                self.assertEqual(delta.total_budget or delta.implicit_total, Decimal(30000))

    def test_allocation_conflicts_and_unbound_amounts_require_clarification(self) -> None:
        for text in (
            '20rb makan dan 10rb makan',
            '20rb makan dan 10rb minum dan 5rb',
            '25rb total, 20rb makanan dan 10rb minuman',
            '30rb total dan 40rb total, makanan 20rb dan minuman 10rb',
            'makanan 20rb minuman 10rb',
            'makanan sekitar 20rb dan minuman 10rb',
            'makanan di atas 20rb dan minuman 10rb',
            'makanan -20rb dan minuman 10rb',
        ):
            with self.subTest(text=text):
                self.assertIsNotNone(self.interpreter.interpret(text).clarification)

    def test_explicit_total_is_kept_separate_from_allocation_sum(self) -> None:
        delta = self.interpreter.interpret('40rb total, 20rb makan dan 10rb minum')
        self.assertIsNone(delta.clarification)
        self.assertEqual(delta.total_budget, Decimal(40000))
        self.assertIsNone(delta.implicit_total)

    def test_allocation_roles_use_current_dynamic_categories(self) -> None:
        interpreter = PlanInterpreter(IndonesianPriceParser(), ['Hidangan Utama', 'Jus'])
        delta = interpreter.interpret('20rb untuk hidangan utama dan 10rb untuk jus')
        self.assertEqual(delta.category_budgets, {'Hidangan Utama': '20000', 'Jus': '10000'})
        self.assertEqual(delta.implicit_total, Decimal(30000))

    def test_ranges_and_personal_finance_are_not_category_allocations(self) -> None:
        for text in ('makanan 10rb sampai 20rb', 'uang bulananku 20rb makan dan 10rb minum'):
            with self.subTest(text=text):
                self.assertFalse(self.interpreter.interpret(text).category_budgets)

    def test_currency_variants_bind_allocations_without_changing_count_roles(self) -> None:
        for text in (
            'Rp20.000 makan dan 10000 minum',
            'dua puluh ribu makan dan sepuluh ribu minum',
        ):
            with self.subTest(text=text):
                delta = self.interpreter.interpret(text)
                self.assertIsNone(delta.clarification)
                self.assertEqual(delta.category_budgets, {'Makanan': '20000', 'Minuman': '10000'})
                self.assertFalse(delta.role_quantities)
                self.assertIsNone(delta.quantity)

    def test_allocation_clause_with_multiple_roles_or_alternatives_is_not_guessed(self) -> None:
        for text in (
            '20rb makan minum dan 10rb minum',
            '20rb makan atau 10rb minum',
            'makanan 20rb total dan minuman 10rb',
        ):
            with self.subTest(text=text):
                self.assertIsNotNone(self.interpreter.interpret(text).clarification)

    def test_single_leading_total_is_not_counted_twice_by_role_quantity_parsing(self) -> None:
        delta = self.interpreter.interpret('total 50rb untuk 2 makanan dan 1 minuman')
        self.assertIsNone(delta.clarification)
        self.assertEqual(delta.total_budget, Decimal(50000))
        self.assertEqual(delta.role_quantities, {'Makanan': 2, 'Minuman': 1})

    def setUp(self) -> None:
        self.interpreter = PlanInterpreter(
            IndonesianPriceParser(), ['Makanan', 'Minuman', 'Camilan']
        )

    def test_people_delta_is_not_quantity_or_money(self) -> None:
        for text in ('jadi 3 orang', 'eh tiga orang', 'sekarang dua puluh orang'):
            delta = self.interpreter.interpret(text)
            self.assertIsNotNone(delta.person_count)
            self.assertIsNone(delta.quantity)
            self.assertIsNone(delta.implicit_total)

    def test_explicit_quantity_retains_catalog_phrase(self) -> None:
        for text in ('dua es jeruk', 'pesan 2 gelas es jeruk'):
            delta = self.interpreter.interpret(text)
            self.assertEqual(delta.quantity, 2)
            self.assertIn('es jeruk', delta.entity_text)
            self.assertIsNone(delta.person_count)

        self.assertEqual(
            self.interpreter.interpret('dua es jeruk 20k').implicit_total, Decimal(20000)
        )
        self.assertIsNone(self.interpreter.interpret('dua es jeruk 20k per menu').implicit_total)

    def test_leading_money_is_not_quantity(self) -> None:
        for text in ('10 ribu ayam', 'sepuluh ribu ayam', '20 ribu untuk dua orang'):
            self.assertIsNone(self.interpreter.interpret(text).quantity)

    def test_role_binding_and_cancellation_are_explicit(self) -> None:
        delta = self.interpreter.interpret('minumannya es jeruk')
        self.assertEqual(delta.target_role, 'Minuman')
        self.assertEqual(delta.entity_text, 'mau es jeruk')
        self.assertEqual(self.interpreter.interpret('minumannya batal').cancel_role, 'Minuman')
        self.assertIsNone(self.interpreter.interpret('sekarang minuman').cancel_role)

    def test_category_and_distinct_budget_declarations(self) -> None:
        delta = self.interpreter.interpret('alokasi makanan 20k dan minuman 10k')
        self.assertEqual(delta.category_budgets, {'Makanan': '20000', 'Minuman': '10000'})
        delta = self.interpreter.interpret('budget total 60k dan 25k per orang untuk 3 orang')
        self.assertEqual(delta.total_budget, Decimal(60000))
        self.assertEqual(delta.per_person_budget, Decimal(25000))

    def test_fractional_zero_and_negative_counts_are_clarified(self) -> None:
        for text in ('jadi 0 orang', 'jadi -2 orang', 'jadi 2.5 porsi', 'jadi 100 porsi'):
            with self.subTest(text=text):
                self.assertIsNotNone(self.interpreter.interpret(text).clarification)

    def test_empty_category_inventory_does_not_crash(self) -> None:
        interpreter = PlanInterpreter(IndonesianPriceParser(), [])
        self.assertIsNone(interpreter.interpret('halo').clarification)

    def test_category_quantities_are_distinct_from_item_or_people_count(self) -> None:
        delta = self.interpreter.interpret('budget 50k untuk 2 makanan dan 1 minuman')
        self.assertEqual(delta.role_quantities, {'Makanan': 2, 'Minuman': 1})
        self.assertIsNone(delta.quantity)
        self.assertIsNone(delta.person_count)

    def test_mixed_named_quantities_are_clarified_instead_of_partially_selected(self) -> None:
        self.assertIsNotNone(
            self.interpreter.interpret('dua es jeruk dan satu ayam geprek').clarification
        )

    def test_natural_total_and_roles_request_existing_combination_planner(self) -> None:
        for text in (
            '30rb untuk makan dan minum',
            '25rb untuk makan dan minum',
            '20rb untuk dua minuman',
            '50rb untuk 2 makanan dan 1 minuman',
        ):
            with self.subTest(text=text):
                self.assertTrue(self.interpreter.interpret(text).combination_request)

    def test_combination_role_selection_retains_identity_without_losing_declaration(self) -> None:
        delta = self.interpreter.interpret('30rb makan minum, minumnya Es Kelapa')
        self.assertTrue(delta.combination_request)
        self.assertEqual(delta.target_role, 'Minuman')
        self.assertEqual(delta.entity_text, 'mau es kelapa')
        self.assertEqual(set(delta.requested_roles), {'Makanan', 'Minuman'})

    def test_natural_trigger_does_not_reinterpret_non_total_or_personal_finance(self) -> None:
        for text in (
            'uang bulananku 30rb makan minum',
            'jam 20 untuk dua minuman',
            '20rb untuk dua minuman per menu',
            'makanan sekitar 20rb',
            'makanan 20rb',
        ):
            with self.subTest(text=text):
                self.assertFalse(self.interpreter.interpret(text).combination_request)

    def test_multiple_selected_role_clauses_require_clarification(self) -> None:
        delta = self.interpreter.interpret(
            '30rb makan minum, minumnya es kelapa, minumnya es jeruk'
        )
        self.assertIsNotNone(delta.clarification)


class PlanStateTests(SimpleTestCase):
    def test_legacy5_upgrade_preserves_soft_target_pending_and_usage(self) -> None:
        session = SessionStore()
        state = ConversationSession(session)
        state.save_search(SearchConstraints(soft_target=Decimal(20000)))
        state.contexts()
        state.set_pending_budget(Decimal(30000))
        session[state.SCHEMA_KEY] = 5
        session[state.GEMINI_CALLS_KEY] = 8
        before = deepcopy(dict(session))
        draft = state.draft()
        self.assertEqual(draft[state.SCHEMA_KEY], 6)

        for key in (
            state.SEARCH_KEY,
            state.CONTEXTS_KEY,
            state.PENDING_BUDGET_KEY,
            state.GEMINI_CALLS_KEY,
        ):
            self.assertEqual(draft[key], before[key])

    def test_schema5_cannot_claim_new_plan_fields(self) -> None:
        session = SessionStore()
        state = ConversationSession(session)
        state.contexts()['plan']['serving_mode'] = 'individual'
        session[state.SCHEMA_KEY] = 5

        with self.assertRaises(ValueError):
            state.draft()

        with self.assertRaises(ConversationStoreUnavailable):
            ConversationStore._encode(dict(session))

    def test_invalid_plan_scope_and_allocation_fail_closed(self) -> None:
        session = SessionStore()
        state = ConversationSession(session)
        baseline = deepcopy(state.contexts())

        for mutate in (
            lambda graph: graph['plan'].update(
                scopes={'9': {'constraints': {}, 'focused_item_id': None, 'item_excluded_tags': []}}
            ),
            lambda graph: graph['plan'].update(serving_mode='whatever'),
            lambda graph: graph['overall'].update(
                category_budgets={'Minuman': 'NaN'}, explicitly_declared=True, plan_id=1
            ),
        ):
            graph = deepcopy(baseline)
            mutate(graph)

            with self.assertRaises((ValueError, ArithmeticError)):
                state.validate_contexts(graph)


class GroupPlanTests(TestCase):
    def setUp(self) -> None:
        self.food = Category.objects.create(name='Makanan')
        self.drinks = Category.objects.create(name='Minuman')
        self.ayam = MenuItem.objects.create(name='Ayam Geprek', price=20000, category=self.food)
        self.nasi = MenuItem.objects.create(name='Nasi Goreng', price=18000, category=self.food)
        self.jeruk = MenuItem.objects.create(name='Es Jeruk', price=10000, category=self.drinks)
        self.kelapa = MenuItem.objects.create(name='Es Kelapa', price=10000, category=self.drinks)
        self.session = SessionStore()
        self.provider = NoBudgetProvider()

    def reply(self, text: str) -> dict:
        return ChatbotService(self.session, gemini_client=self.provider).reply(text)

    def graph(self) -> dict:
        return ConversationSession(self.session).contexts()

    def quantities(self) -> dict[int, int]:
        return {entry['menu_id']: entry['quantity'] for entry in self.graph()['plan']['entries']}

    def test_N10_count_update_preserves_total_and_quantities(self) -> None:
        self.reply('budget 40k untuk 2 orang')
        self.reply('ayam geprek')
        before = self.quantities()
        self.reply('jadi 3 orang')
        self.assertEqual(self.graph()['overall']['total_budget'], '40000')
        self.assertEqual(self.graph()['overall']['person_count'], 3)
        self.assertEqual(self.quantities(), before)
        self.assertNotIn('budget', ConversationSession(self.session).load_constraints().to_dict())

    def test_N11_binding_drink_keeps_food_role(self) -> None:
        self.reply('30k untuk makan dan minum')
        food_choice = {
            key: value
            for key, value in self.quantities().items()
            if MenuItem.objects.get(pk=key).category_id == self.food.pk
        }
        self.assertTrue(food_choice)  # CR-04 now fills the food role immediately.
        result = self.reply('minumannya es jeruk')
        self.assertEqual([m.item.pk for m in result['recommendations']], [self.jeruk.pk])
        self.assertEqual(self.quantities(), {**food_choice, self.jeruk.pk: 1})
        self.assertEqual(self.graph()['plan']['unresolved_roles'], [])
        self.assertEqual(self.graph()['overall']['total_budget'], '30000')

    def test_N19_quantity_budget_is_total_without_person_inference(self) -> None:
        self.reply('dua es jeruk 20k')
        self.assertEqual(self.quantities(), {self.jeruk.pk: 2})
        self.assertEqual(self.graph()['overall']['total_budget'], '20000')
        self.assertNotIn('person_count', self.graph()['overall'])

    def test_explicit_per_menu_budget_does_not_become_total(self) -> None:
        self.reply('dua es jeruk 10k per menu')
        self.assertEqual(self.quantities(), {self.jeruk.pk: 2})
        self.assertFalse(self.graph()['overall'])
        self.assertEqual(ConversationSession(self.session).load_constraints().max_price, 10000)

    def test_quantity_only_updates_focus_but_not_people_or_budget(self) -> None:
        self.reply('budget 40k untuk 2 orang')
        self.reply('es jeruk')
        self.reply('jadi 3 porsi')
        self.assertEqual(self.quantities(), {self.jeruk.pk: 3})
        self.assertEqual(self.graph()['overall']['person_count'], 2)
        self.assertEqual(self.graph()['overall']['total_budget'], '40000')

    def test_over_budget_quantity_update_is_atomic(self) -> None:
        self.reply('budget total 20k')
        self.reply('es jeruk')
        before = deepcopy(self.graph()['plan'])
        result = self.reply('jadi 3 porsi')
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.graph()['plan'], before)
        self.assertIn('melebihi', result['message'])

    def test_ambiguous_quantity_without_owned_focus_is_not_guessed(self) -> None:
        result = self.reply('jadi 3 porsi')
        self.assertFalse(result['recommendations'])
        self.assertFalse(self.quantities())
        self.assertIn('menu', result['message'])

    def test_add_same_item_merges_quantity_and_respects_total(self) -> None:
        self.reply('budget total 30k')
        self.reply('es jeruk')
        self.reply('tambahkan dua es jeruk')
        self.assertEqual(self.quantities(), {self.jeruk.pk: 3})
        self.assertEqual(len(self.graph()['plan']['entries']), 1)
        before = deepcopy(self.graph()['plan'])
        self.reply('tambahkan satu es jeruk')
        self.assertEqual(self.graph()['plan'], before)

    def test_replace_role_keeps_quantity_and_unrelated_role(self) -> None:
        self.reply('budget total 50k untuk makan dan minum')
        self.reply('ayam geprek')
        self.reply('minumannya dua es jeruk')
        self.reply('minumannya es kelapa')
        self.assertEqual(self.quantities(), {self.ayam.pk: 1, self.kelapa.pk: 2})

    def test_role_quantity_targets_selected_drink_instead_of_food_focus(self) -> None:
        self.reply('budget total 50k untuk makan dan minum')
        self.reply('es jeruk')
        self.reply('ayam geprek')
        self.reply('minumannya jadi 2 gelas')
        self.assertEqual(self.quantities(), {self.ayam.pk: 1, self.jeruk.pk: 2})

    def test_search_switch_does_not_cancel_role_but_explicit_cancel_does(self) -> None:
        self.reply('budget total 40k untuk makan dan minum')
        self.reply('ayam geprek')
        self.reply('es jeruk')
        self.reply('sekarang minuman')
        self.assertEqual(self.quantities(), {self.ayam.pk: 1, self.jeruk.pk: 1})
        self.reply('minumannya batal')
        self.assertEqual(self.quantities(), {self.ayam.pk: 1})
        self.assertEqual(self.graph()['overall']['total_budget'], '40000')
        self.assertNotIn('Minuman', self.graph()['overall']['requested_categories'])

    def test_role_category_mismatch_cannot_mutate_plan(self) -> None:
        self.reply('budget total 30k untuk makan dan minum')
        before = deepcopy(self.graph())
        self.reply('minumannya ayam geprek')
        self.assertEqual(self.graph()['overall'], before['overall'])
        self.assertEqual(self.graph()['plan'], before['plan'])

    def test_total_and_per_person_are_distinct_and_both_preserved(self) -> None:
        self.reply('budget total 60k dan 25k per orang untuk 3 orang')
        self.assertEqual(self.graph()['overall']['total_budget'], '60000')
        self.assertEqual(self.graph()['overall']['per_person_budget'], '25000')
        self.assertEqual(self.graph()['overall']['person_count'], 3)
        self.reply('budget total 50k')
        self.assertEqual(self.graph()['overall']['per_person_budget'], '25000')
        self.assertEqual(self.graph()['overall']['total_budget'], '50000')

    def test_new_overall_declaration_preserves_existing_role_choice(self) -> None:
        self.reply('budget total 40k untuk makan dan minum')
        self.reply('ayam geprek')
        before = self.quantities()
        self.assertEqual(before, {self.ayam.pk: 1, self.jeruk.pk: 1})
        self.reply('budget total 50k')
        self.assertEqual(self.quantities(), before)
        self.assertEqual(self.graph()['plan']['unresolved_roles'], [])

    def test_individual_quantity_is_inferred_only_from_explicit_each(self) -> None:
        self.reply('budget 25k per orang untuk 3 orang')
        self.reply('masing-masing satu ayam geprek')
        self.assertEqual(self.quantities(), {self.ayam.pk: 3})
        self.assertEqual(self.graph()['plan']['serving_mode'], 'individual')
        before = deepcopy(self.graph()['plan'])
        self.reply('sekalian masing-masing satu es jeruk')
        self.assertEqual(self.graph()['plan'], before)

    def test_unspecified_distribution_is_not_claimed_per_person_compliant(self) -> None:
        self.reply('budget 25k per orang untuk 3 orang')
        result = self.reply('ayam geprek')
        self.assertEqual(self.quantities(), {self.ayam.pk: 1})
        self.assertIn('belum dipastikan', result['message'])

    def test_reducing_people_cannot_relax_other_limits_or_keep_invalid_plan(self) -> None:
        self.reply('budget 25k per orang untuk 3 orang')
        self.reply('tiga ayam geprek')
        before = deepcopy(self.graph()['overall'])
        self.reply('jadi 2 orang')
        self.assertEqual(self.graph()['overall'], before)
        self.assertEqual(self.quantities(), {self.ayam.pk: 3})

    def test_category_caps_apply_to_role_sum_not_each_item(self) -> None:
        self.reply('alokasi makanan 20k dan minuman 10k')
        self.reply('ayam geprek')
        self.reply('minumannya es jeruk')
        self.assertEqual(self.quantities(), {self.ayam.pk: 1, self.jeruk.pk: 1})
        before = deepcopy(self.graph()['plan'])
        self.reply('minumannya jadi 2 gelas')
        self.assertEqual(self.graph()['plan'], before)
        self.assertEqual(
            self.graph()['overall']['category_budgets'], {'Makanan': '20000', 'Minuman': '10000'}
        )

    def test_category_update_preserves_other_allocation_and_total(self) -> None:
        self.reply('budget total 40k, makanan 25k dan minuman 15k')
        self.reply('alokasi makanan 20k')
        overall = self.graph()['overall']
        self.assertEqual(overall['total_budget'], '40000')
        self.assertEqual(overall['category_budgets'], {'Makanan': '20000', 'Minuman': '15000'})

    def test_invalid_allocation_does_not_partially_commit(self) -> None:
        self.reply('budget total 40k untuk makan dan minum')
        self.reply('ayam geprek')
        before_choices = self.quantities()
        self.assertEqual(before_choices, {self.ayam.pk: 1, self.jeruk.pk: 1})
        before = deepcopy(self.graph()['overall'])
        self.reply('alokasi makanan 10k dan minuman 10k')
        self.assertEqual(self.graph()['overall'], before)
        self.assertEqual(self.quantities(), before_choices)

    def test_required_variant_cost_is_multiplied_by_quantity(self) -> None:
        group = VariantGroup.objects.create(menu_item=self.ayam, name='Wajib', is_required=True)
        VariantOption.objects.create(group=group, name='Reguler', price_adjustment=5000)
        self.reply('budget total 40k')
        before = deepcopy(self.graph()['plan'])
        self.reply('dua ayam geprek')
        self.assertEqual(self.graph()['plan'], before)

    def test_unknown_or_inactive_quantity_target_never_creates_entries(self) -> None:
        self.jeruk.is_available = False
        self.jeruk.save(update_fields=['is_available'])
        result = self.reply('dua es jeruk 20k')
        self.assertFalse(result['recommendations'])
        self.assertFalse(self.quantities())

    def test_count_quantity_and_roles_are_session_owned_and_resettable(self) -> None:
        self.reply('budget total 40k untuk 2 orang')
        self.reply('dua es jeruk')
        fresh = ChatbotService(SessionStore(), gemini_client=self.provider)
        fresh.reply('jadi 3 porsi')
        self.assertFalse(fresh._session_state.contexts()['plan']['entries'])
        self.reply('mulai lagi')
        self.assertFalse(self.quantities())
        self.assertFalse(self.graph()['overall'])

    def test_late_catalog_change_rejects_metadata_update_atomically(self) -> None:
        self.reply('budget total 30k untuk 2 orang')
        self.reply('ayam geprek')
        before = deepcopy(self.graph()['overall'])
        original = ChatbotService._finish_context
        changed = False

        def late(service, result):
            nonlocal changed

            if not changed:
                changed = True
                MenuItem.objects.filter(pk=self.ayam.pk).update(price=40000)

            return original(service, result)

        with patch.object(ChatbotService, '_finish_context', late):
            self.reply('jadi 3 orang')

        self.assertEqual(self.graph()['overall'], before)

    def test_http_quantity_and_role_have_no_order_side_effect(self) -> None:
        with patch(
            'recommendation.services.gemini.GeminiClient.generate',
            side_effect=AssertionError('No AI'),
        ):
            response = self.client.post(
                '/api/recommendation/chat/',
                {'message': 'dua es jeruk 20k'},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        from orders.models import Order

        self.assertEqual(Order.objects.count(), 0)

    def test_category_quantities_select_combination_and_allow_role_replacement(self) -> None:
        result = self.reply('budget 50k untuk 2 makanan dan 1 minuman')
        self.assertTrue(result['recommendations'])  # Approved CR-04 auto fulfillment.
        self.assertEqual(self.quantities(), {self.nasi.pk: 2, self.jeruk.pk: 1})
        self.assertEqual(self.graph()['plan']['role_quantities'], {'Makanan': 2, 'Minuman': 1})
        self.assertNotIn('person_count', self.graph()['overall'])
        self.reply('makanannya ayam geprek')
        self.reply('minumannya es jeruk')
        self.assertEqual(self.quantities(), {self.ayam.pk: 2, self.jeruk.pk: 1})
        self.assertFalse(self.graph()['plan']['unresolved_roles'])

    def test_ambiguous_overall_budget_correction_does_not_guess_between_two_limits(self) -> None:
        self.reply('budget total 60k dan 25k per orang untuk 3 orang')
        before = deepcopy(self.graph()['overall'])
        result = self.reply('ganti budget 30k')
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.graph()['overall'], before)
        self.assertIn('total atau per orang', result['message'])

    def test_eight_plan_scopes_survive_four_frame_conversation_archive(self) -> None:
        self.reply('budget total 100k')
        selected = []

        for letter in 'ABCDEFGH':
            category = Category.objects.create(name='Kategori ' + letter)
            item = MenuItem.objects.create(
                name='Menu Arunika ' + letter, price=1000, category=category
            )
            selected.append(item.pk)
            self.reply('sekalian menu arunika ' + letter)

        self.assertEqual(set(self.quantities()), set(selected))
        self.assertEqual(len(self.graph()['plan']['scopes']), 8)
        self.assertEqual(len(self.graph()['previous']), 4)
        self.reply('jadi 3 orang')
        self.assertEqual(set(self.quantities()), set(selected))
        self.assertEqual(self.graph()['overall']['person_count'], 3)

    def test_safety_declaration_is_not_suppressed_by_a_count_delta(self) -> None:
        self.reply('budget total 40k untuk 2 orang')
        self.reply('aku alergi udang jadi 3 orang')
        self.assertIn('shrimp', self.graph()['safety']['excluded_tags'])
        self.assertTrue(self.graph()['safety']['verification_required'])

    def test_nonnumeric_or_unknown_quantity_target_does_not_call_provider(self) -> None:
        result = self.reply('dua glorp 20k')
        self.assertFalse(result['recommendations'])
        self.assertFalse(self.quantities())
        self.assertFalse(self.graph()['overall'])

    def test_role_cancellation_removes_only_its_quantity_and_allocation(self) -> None:
        self.reply('budget total 50k, makanan 40k dan minuman 10k')
        self.reply('budget 50k untuk 2 makanan dan 1 minuman')
        self.reply('makanannya ayam geprek')
        self.reply('minumannya es jeruk')
        self.reply('minumannya batal')
        self.assertEqual(self.quantities(), {self.ayam.pk: 2})
        self.assertEqual(self.graph()['plan']['role_quantities'], {'Makanan': 2})
        self.assertEqual(self.graph()['overall']['category_budgets'], {'Makanan': '40000'})
