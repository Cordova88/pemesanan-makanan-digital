"""Phase4 shared payable facts, bounded solver and exact atomic draft validation."""
from copy import deepcopy
from decimal import Decimal
from itertools import product
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from menu.models import AddOn, Category, MenuItem, MenuTag, VariantGroup, VariantOption
from menu.selection import MenuSelection
from ..services.budget import BudgetConstraint
from ..services.chatbot import ChatbotService
from ..services.combination_planner import CombinationCandidate, CombinationPlanner
from ..services.conversation_session import ConversationSession
from ..services.conversation_store import ConversationStore
from ..services.plan_interpreter import PlanInterpreter
from ..services.language import IndonesianPriceParser
from ..services.recommendation import RecommendationService, SearchConstraints
from ..services.tag_extractor import Preferences
from .test_budget import NoBudgetProvider


class CombinationOracleTests(SimpleTestCase):
    def candidates(self, *prices):
        return [CombinationCandidate(index + 1, Decimal(price)) for index, price in enumerate(prices)]

    def test_small_multiset_feasibility_matches_independent_exhaustive_oracle(self):
        # Oracle enumerates ordered choices independently; production searches
        # multisets with branch bounds. 3^4 × budgets, including exact boundaries.
        pools = {'Food': self.candidates(0, 7, 13),
                 'Drink': [CombinationCandidate(4, Decimal(3)), CombinationCandidate(5, Decimal(9))]}
        for food_qty, drink_qty, cap, food_cap in product((1, 2, 3), (1, 2), range(0, 45, 3), (8, 35)):
            expected = any(sum(f) + sum(d) <= cap and sum(f) <= food_cap
                           for f in product((0, 7, 13), repeat=food_qty)
                           for d in product((3, 9), repeat=drink_qty))
            actual = CombinationPlanner().propose(pools, {'Food': food_qty, 'Drink': drink_qty},
                     maximum=Decimal(cap), category_limits={'Food': Decimal(food_cap)})
            self.assertEqual(actual.total is not None, expected, (food_qty, drink_qty, cap, food_cap))
            self.assertFalse(actual.limited)
            if expected:
                self.assertLessEqual(actual.total, cap)
                self.assertEqual(sum(actual.quantities.values()), food_qty + drink_qty)

    def test_automatic_slot_limit_is_explicit(self):
        result = CombinationPlanner().propose({'Food': self.candidates(1)}, {'Food': 9}, maximum=Decimal(10))
        self.assertEqual(result.reason, 'bounds')
        self.assertTrue(result.limited)

    def test_role_limit_is_explicit(self):
        result = CombinationPlanner().propose({str(i): [] for i in range(4)}, {str(i): 1 for i in range(4)}, maximum=None)
        self.assertEqual(result.reason, 'bounds')

    def test_truncated_candidates_cannot_prove_infeasibility(self):
        result = CombinationPlanner().propose({'Food': self.candidates(*([20]*16), 1)}, {'Food': 1}, maximum=Decimal(5))
        self.assertIsNone(result.total)
        self.assertTrue(result.limited)

    def test_valid_truncated_solution_is_labelled_limited(self):
        result = CombinationPlanner().propose({'Food': self.candidates(*range(17))}, {'Food': 1}, maximum=Decimal(5))
        self.assertEqual(result.total, 0)
        self.assertTrue(result.limited)

    def test_node_limit_is_enforced(self):
        planner = CombinationPlanner()
        with patch.object(planner, 'MAX_NODES', 2):
            result = planner.propose({'Food': self.candidates(4, 1)}, {'Food': 3}, maximum=Decimal(3))
        self.assertEqual(result.nodes, 2)
        self.assertTrue(result.limited)
        self.assertIsNone(result.total)

    def test_quantity_compression_keeps_decimal_total(self):
        result = CombinationPlanner().propose({'Food': self.candidates('10.25')}, {'Food': 3}, maximum=Decimal('30.75'))
        self.assertEqual(result.quantities, {1: 3})
        self.assertEqual(result.total, Decimal('30.75'))

    def test_individual_ceiling_does_not_claim_unproved_mixed_allocation(self):
        pools={'Food': self.candidates(20)}
        self.assertIsNone(CombinationPlanner().propose(pools, {'Food': 3}, maximum=Decimal(60),
                         people=2, per_person=Decimal(30), individual=True).total)
        self.assertEqual(CombinationPlanner().propose(pools, {'Food': 2}, maximum=Decimal(40),
                         people=2, per_person=Decimal(20), individual=True).total, 40)

    def test_empty_pool_and_zero_quantity_do_not_produce_partial_plan(self):
        self.assertIsNone(CombinationPlanner().propose({'Food': []}, {'Food': 1}, maximum=None).total)
        self.assertEqual(CombinationPlanner().propose({'Food': []}, {'Food': 0}, maximum=None).reason, 'bounds')

    def test_invalid_candidate_rejected(self):
        for value in ('NaN', '-1', 'Infinity'):
            with self.assertRaises(ValueError): CombinationCandidate(1, Decimal(value))


class PayableAndCombinationTests(TestCase):
    def test_selected_addon_request_explains_boundary_without_partial_plan(self):
        addon = AddOn.objects.create(name='Telur', price=5000)
        addon.menu_items.add(self.rice)
        before = deepcopy(self.graph())
        result = self.reply('30rb makan minum tapi tambah telur 5rb')
        self.assertIn('Lihat pilihan menu', result['message'])
        self.assertIn('belum diterapkan', result['message'])
        self.assertNotIn('Rp5.000', result['message'])
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.graph()['plan'], before['plan'])
        self.assertEqual(self.graph()['overall'], before['overall'])
        self.assertFalse(self.provider.calls)

    def test_option_boundary_preserves_existing_budget_scopes_and_choices(self):
        addon = AddOn.objects.create(name='Telur', price=5000)
        addon.menu_items.add(self.rice)
        self.reply('30rb untuk makan dan minum')
        before = deepcopy(self.graph())
        self.session['cart'] = ['sentinel']
        result = self.reply('nasi goreng tambah telur 1 rupiah')
        self.assertIn('belum diterapkan', result['message'])
        for key in ('plan', 'overall', 'safety', 'previous'):
            self.assertEqual(self.graph()[key], before[key], key)
        # Intent/time/transition describe this clarification, not a selection edit.
        for key in set(before['active']) - {'intent', 'updated_at'}:
            self.assertEqual(self.graph()['active'][key], before['active'][key], key)
        self.assertEqual(self.session['cart'], ['sentinel'])

    def test_explicit_unknown_variant_gets_boundary_without_price_or_selection(self):
        for text in ('pilih varian quantum 5000', 'tambahan alien 2rb', 'mau addon misteri',
                     'ganti ke opsi ukuran jumbo', 'varian ukuran besar'):
            with self.subTest(text=text):
                result = self.reply(text)
                self.assertIn('Lihat pilihan menu', result['message'])
                self.assertIn('belum diterapkan', result['message'])
                self.assertFalse(result['recommendations'])
                self.assertFalse(self.quantities())
                self.assertNotIn('Rp', result['message'])

    def test_catalog_option_names_are_dynamic_and_do_not_claim_availability(self):
        addon = AddOn.objects.create(name='Saus Arunika', price=7000, is_active=False, is_available=False)
        addon.menu_items.add(self.juice)  # Not allowed on the requested rice either.
        for text in ('nasi goreng tambah saus arunika 1000', 'pakai saus arunika'):
            with self.subTest(text=text):
                result = self.reply(text)
                self.assertIn('belum diterapkan', result['message'])
                self.assertFalse(result['recommendations'])
                self.assertNotIn('tersedia', result['message'].casefold())
                self.assertNotIn('Rp', result['message'])

    def test_selected_variant_name_is_not_a_final_required_option_choice(self):
        group, option = self.required()
        option.name = 'Arunika Besar'
        option.save(update_fields=['name'])
        result = self.reply('pilih arunika besar')
        self.assertIn('belum diterapkan', result['message'])
        self.assertFalse(self.quantities())
        self.assertFalse(result['recommendations'])

    def test_exact_menu_and_alias_with_addon_words_keep_catalog_identity(self):
        from menu.models import MenuItemAlias
        addon = AddOn.objects.create(name='Telur', price=5000)
        addon.menu_items.add(self.rice)
        item = MenuItem.objects.create(name='Nasi Tambah Telur', price=15000, category=self.food)
        MenuItemAlias.objects.create(menu_item=item, phrase='paket tambahan telur')
        for text in ('mau nasi tambah telur', 'mau paket tambahan telur'):
            with self.subTest(text=text):
                result = self.reply(text)
                self.assertEqual([match.item.pk for match in result['recommendations']], [item.pk])
                self.assertNotIn('belum diterapkan', result['message'])

    def test_adding_menu_and_quantity_is_not_an_addon_request(self):
        self.reply('30rb untuk makan dan minum')
        result = self.reply('tambahkan es jeruk')
        self.assertNotIn('belum diterapkan', result['message'])
        self.assertEqual(self.quantities(), {self.rice.pk: 1, self.juice.pk: 1})
        # Existing 30k total must reject adding another 10k drink.
        self.assertFalse(result['recommendations'])

    def test_ingredient_negation_and_past_consumption_do_not_trigger_boundary(self):
        addon = AddOn.objects.create(name='Telur', price=5000)
        addon.menu_items.add(self.rice)
        for text in ('tanpa telur', 'jangan tambah telur', 'gak usah tambah telur',
                     'tidak jadi pilih varian besar', 'bukan varian besar',
                     'tadi sudah makan nasi goreng tambah telur'):
            with self.subTest(text=text):
                result = self.reply(text)
                self.assertNotIn('belum diterapkan', result['message'])

    def test_allergy_instruction_is_not_swallowed_by_addon_boundary(self):
        result = self.reply('alergi udang, pilih varian besar')
        self.assertNotIn('belum diterapkan', result['message'])
        self.assertIn('staf', result['message'])
        self.assertIn('shrimp', self.graph()['safety']['excluded_tags'])

    def test_reset_action_overrides_option_text_and_still_clears_plan(self):
        self.reply('30rb untuk makan dan minum')
        result = ChatbotService(self.session, gemini_client=self.provider).reply('pilih varian besar', action='reset')
        self.assertFalse(self.quantities())
        self.assertFalse(self.graph()['overall'])
        self.assertNotIn('belum diterapkan', result['message'])

    def test_taste_word_shared_with_variant_keeps_preference_flow(self):
        group, option = self.required(0)
        option.name = 'Pedas'
        option.save(update_fields=['name'])
        for text in ('mau pedas', 'mau yang pedas', 'tambah pedas'):
            with self.subTest(text=text):
                result = self.reply(text)
                self.assertNotIn('belum diterapkan', result['message'])
        self.assertIn('belum diterapkan', self.reply('pilih varian pedas')['message'])

    def test_option_boundary_preserves_per_person_and_global_safety(self):
        self.reply('budget 25k per orang untuk 2 orang')
        self.reply('alergi udang')
        before = deepcopy(self.graph())
        result = self.reply('pilih varian quantum')
        self.assertIn('belum diterapkan', result['message'])
        for key in ('plan', 'overall', 'safety', 'previous'):
            self.assertEqual(self.graph()[key], before[key])

    def test_option_boundary_http_is_local_and_never_creates_order(self):
        from orders.models import Order
        addon = AddOn.objects.create(name='Telur', price=5000)
        addon.menu_items.add(self.rice)
        with patch('recommendation.services.gemini.GeminiClient.generate', side_effect=AssertionError('No AI')):
            response = self.client.post('/api/recommendation/chat/',
                {'message': '30rb makan minum tapi tambah telur 5rb'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('belum diterapkan', response.json()['message'])
        self.assertFalse(response.json()['recommendations'])
        self.assertEqual(Order.objects.count(), 0)

    def test_natural_category_allocations_select_exact_affordable_plan(self):
        for text in ('20rb makan dan 10rb minum', '20rb buat makan, 10rb buat minum.',
                     'Makan 20k, minum 10k.', 'Untuk minuman 10rb, makanan 20rb.',
                     '30rb total, 20rb makanan dan 10rb minuman.'):
            with self.subTest(text=text):
                self.reply('mulai lagi')
                result = self.reply(text)
                self.assertTrue(result['recommendations'])
                self.assertEqual(self.quantities(), {self.rice.pk: 1, self.juice.pk: 1})
                self.assertEqual(self.graph()['overall']['total_budget'], '30000')
                self.assertEqual(self.graph()['overall']['category_budgets'],
                                 {'Makanan': '20000', 'Minuman': '10000'})

    def test_conflicting_allocations_preserve_previous_plan_atomically(self):
        self.reply('30rb untuk makan dan minum')
        for text in ('25rb total, 20rb makan dan 10rb minum',
                     '20rb makan dan 10rb makan', '20rb makan dan 10rb minum dan 5rb',
                     'makanan sekitar 20rb dan minuman 10rb'):
            with self.subTest(text=text):
                self.assert_atomic_failure(text)

    def test_natural_allocations_cannot_borrow_between_categories(self):
        self.assert_atomic_failure('19rb makan dan 11rb minum')

    def test_natural_allocations_include_required_option_price(self):
        self.required()
        self.assert_atomic_failure('20rb makan dan 10rb minum')
        result = self.reply('25rb makan dan 10rb minum')
        self.assertTrue(result['recommendations'])
        self.assertEqual(self.graph()['overall']['total_budget'], '35000')

    def test_inferred_allocation_total_does_not_replace_explicit_existing_total(self):
        self.reply('budget total 40k')
        result = self.reply('20rb makan dan 10rb minum')
        self.assertTrue(result['recommendations'])
        self.assertEqual(self.graph()['overall']['total_budget'], '40000')

    def setUp(self):
        self.food=Category.objects.create(name='Makanan')
        self.drinks=Category.objects.create(name='Minuman')
        self.rice=MenuItem.objects.create(name='Nasi Goreng', price=20000, category=self.food)
        self.juice=MenuItem.objects.create(name='Es Jeruk', price=10000, category=self.drinks)
        self.session=SessionStore()
        self.provider=NoBudgetProvider()

    def reply(self, message):
        return ChatbotService(self.session, gemini_client=self.provider).reply(message)

    def graph(self):
        return ConversationSession(self.session).contexts()

    def quantities(self):
        return {entry['menu_id']:entry['quantity'] for entry in self.graph()['plan']['entries']}

    def required(self, price=5000):
        group=VariantGroup.objects.create(menu_item=self.rice, name='Size', is_required=True)
        option=VariantOption.objects.create(group=group, name='Normal', price_adjustment=price)
        return group, option

    def assert_atomic_failure(self, message, contains=None):
        before=deepcopy(self.graph())
        result=self.reply(message)
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.graph()['plan'],before['plan'])
        self.assertEqual(self.graph()['overall'],before['overall'])
        if contains: self.assertIn(contains,result['message'])

    def test_minimum_includes_required_cheapest_and_excludes_optional_addon(self):
        group, option=self.required()
        VariantOption.objects.create(group=group,name='Large',price_adjustment=8000)
        optional=VariantGroup.objects.create(menu_item=self.rice,name='Sauce',is_required=False)
        VariantOption.objects.create(group=optional,name='Sauce',price_adjustment=2000)
        addon=AddOn.objects.create(name='Extra',price=3000);addon.menu_items.add(self.rice)
        self.assertEqual(MenuSelection.minimum_payable(self.rice),25000)
        selection=MenuSelection.from_ids(self.rice,[option.pk],[addon.pk])
        self.assertEqual(selection.unit_price,28000)
        self.assertEqual(selection.total_price(2),56000)

    def test_required_without_active_option_is_not_payable(self):
        group, option=self.required();option.is_active=False;option.save()
        self.assertIsNone(MenuSelection.minimum_payable(self.rice))
        self.assert_atomic_failure('kombinasi makanan minuman budget total 30k')

    def test_inactive_required_group_does_not_add_cost(self):
        group, option=self.required();group.is_active=False;group.save()
        self.assertEqual(MenuSelection.minimum_payable(self.rice),20000)

    def test_inactive_menu_category_or_unavailable_has_no_minimum(self):
        for field in ('is_active','is_available'):
            setattr(self.rice,field,False)
            self.assertIsNone(MenuSelection.minimum_payable(self.rice))
            setattr(self.rice,field,True)
        self.food.is_active=False;self.food.save()
        self.assertIsNone(MenuSelection.minimum_payable(self.rice))

    def test_total_price_rejects_untrusted_quantity(self):
        selection=MenuSelection.from_ids(self.rice)
        for qty in (0,-1,100,True,Decimal(2),'2'):
            with self.assertRaises(ValidationError): selection.total_price(qty)

    def test_filter_uses_minimum_not_base_price(self):
        self.required()
        result=self.reply('makanan maksimal 20k')
        self.assertFalse(result['recommendations'])

    def test_exact_item_uses_minimum_not_base_price(self):
        self.required()
        result=self.reply('nasi goreng maksimal 20k')
        self.assertFalse(result['recommendations'])

    def test_lower_bound_uses_payable_not_base(self):
        self.required()
        matches=RecommendationService().rank(Preferences(),constraints=SearchConstraints(
            category='Makanan',budget=BudgetConstraint(minimum=Decimal(24000))),include_unscored=True)
        self.assertEqual([match.item.pk for match in matches],[self.rice.pk])

    def test_catalog_match_filter_uses_payable(self):
        tag=MenuTag.objects.create(name='rice');self.rice.tags.add(tag);self.required()
        self.assertFalse(RecommendationService().find_catalog_matches({'rice'},max_price=20000))

    def test_N20_total_budget_then_explicit_combination(self):
        self.reply('budget total 30k')
        result=self.reply('kombinasi makan dan minum')
        self.assertEqual(self.quantities(),{self.rice.pk:1,self.juice.pk:1})
        self.assertEqual(Decimal(result['combination']['minimum_total']),30000)
        self.assertIn('satu kombinasi',result['message'])
        self.assertFalse(result['combination']['final_price_confirmed'])
        self.assertEqual(self.provider.calls,0)

    def test_direct_food_drink_amount_creates_combination(self):
        result=self.reply('30 ribu buat makan dan minum')
        self.assertEqual(len(result['recommendations']),2)
        self.assertEqual(self.quantities(),{self.rice.pk:1,self.juice.pk:1})

    def test_natural_food_and_drink_total30k(self):
        result=self.reply('30rb untuk makan dan minum')
        self.assertEqual(self.quantities(),{self.rice.pk:1,self.juice.pk:1})
        self.assertEqual(Decimal(result['combination']['minimum_total']),30000)
        self.assertEqual(self.graph()['overall']['total_budget'],'30000')
        self.assertNotIn('cart',self.session)
        self.assertEqual(self.provider.calls,0)

    def test_natural_total25k_uses_available_cheaper_food(self):
        bubur=MenuItem.objects.create(name='Bubur Ayam',price=15000,category=self.food)
        result=self.reply('25rb untuk makan dan minum')
        self.assertEqual(self.quantities(),{bubur.pk:1,self.juice.pk:1})
        self.assertEqual(Decimal(result['combination']['minimum_total']),25000)

    def test_natural_two_drinks_means_two_units_under_one_total(self):
        result=self.reply('20rb untuk dua minuman')
        self.assertEqual(self.quantities(),{self.juice.pk:2})
        self.assertEqual(Decimal(result['combination']['minimum_total']),20000)
        self.assertNotIn('person_count',self.graph()['overall'])

    def test_natural_category_counts_do_not_collapse_to_one_each(self):
        result=self.reply('50rb untuk 2 makanan dan 1 minuman')
        self.assertEqual(self.quantities(),{self.rice.pk:2,self.juice.pk:1})
        self.assertEqual(Decimal(result['combination']['minimum_total']),50000)

    def test_natural_combination_pins_named_drink_without_spreading_its_tags(self):
        kelapa=MenuItem.objects.create(name='Es Kelapa',price=10000,category=self.drinks)
        kelapa.tags.add(MenuTag.objects.create(name='cold'),MenuTag.objects.create(name='sweet'))
        result=self.reply('30rb makan minum, minumnya Es Kelapa')
        self.assertEqual(self.quantities(),{self.rice.pk:1,kelapa.pk:1})
        self.assertEqual(Decimal(result['combination']['minimum_total']),30000)

    def test_named_drink_is_not_lost_beyond_automatic_candidate_shortlist(self):
        for number in range(17):
            MenuItem.objects.create(name=f'Air Kebun {number}',price=1000,category=self.drinks)
        kelapa=MenuItem.objects.create(name='Es Kelapa',price=10000,category=self.drinks)
        self.reply('30rb makan minum, minumnya es kelapa')
        self.assertEqual(self.quantities(),{self.rice.pk:1,kelapa.pk:1})

    def test_named_catalog_package_with_amount_and_roles_is_still_one_identity(self):
        item=MenuItem.objects.create(name='Paket Makan Minum 30rb',price=25000,category=self.food)
        result=self.reply('mau Paket Makan Minum 30rb')
        self.assertEqual({match.item.pk for match in result['recommendations']},{item.pk})
        self.assertNotIn('combination',result)

    def test_ambiguous_or_unknown_named_role_does_not_commit_a_combination(self):
        MenuItem.objects.create(name='Jus Jeruk',price=10000,category=self.drinks)
        for text in ('30rb makan minum, minumnya jeruk',
                     '30rb makan minum, minumnya quantum'):
            with self.subTest(text=text):self.assert_atomic_failure(text)

    def test_named_role_cannot_select_a_different_category(self):
        self.assert_atomic_failure('30rb makan minum, minumnya nasi goreng')

    def test_unavailable_pinned_drink_is_not_replaced_with_another_drink(self):
        MenuItem.objects.create(name='Es Kelapa',price=10000,category=self.drinks,is_available=False)
        self.assert_atomic_failure('30rb makan minum, minumnya es kelapa')

    def test_overbudget_pinned_drink_is_not_replaced_with_a_cheaper_drink(self):
        MenuItem.objects.create(name='Es Kelapa',price=15000,category=self.drinks)
        self.assert_atomic_failure('30rb makan minum, minumnya es kelapa')

    def test_natural_combination_includes_required_minimum_price(self):
        self.required(5000)
        result=self.reply('30rb untuk makan dan minum')
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.quantities(),{})
        self.assertEqual(self.graph()['overall']['total_budget'],'30000')
        self.assertEqual(set(self.graph()['plan']['unresolved_roles']),{'Makanan','Minuman'})

    def test_failed_natural_combination_preserves_previous_owned_plan(self):
        self.reply('budget total 40k')
        self.reply('nasi goreng')
        self.assert_atomic_failure('10rb untuk makan dan minum')

    def test_group_each_food_means_two_portions_not_two_people_as_money(self):
        result=self.reply('40 ribu untuk 2 orang, masing-masing mau makan')
        self.assertEqual(self.quantities(),{self.rice.pk:2},result)
        self.assertEqual(self.graph()['overall']['person_count'],2)
        self.assertEqual(Decimal(result['combination']['minimum_total']),40000)

    def test_unknown_group_sharing_clarifies_atomically(self):
        self.assert_atomic_failure('kombinasi makanan total 40k untuk 2 orang','masing-masing')

    def test_shared_unknown_quantity_does_not_assume_one(self):
        self.assert_atomic_failure('kombinasi makanan total 40k untuk 2 orang berbagi','berapa porsi')

    def test_group_shared_explicit_quantity_is_supported(self):
        result=self.reply('kombinasi 2 makanan total 40k untuk 2 orang berbagi')
        self.assertEqual(self.quantities(),{self.rice.pk:2})
        self.assertIn('combination',result)

    def test_quantities_and_category_caps(self):
        result=self.reply('kombinasi 2 makanan dan 1 minuman total 50k')
        self.assertEqual(self.quantities(),{self.rice.pk:2,self.juice.pk:1})
        self.assertEqual(Decimal(result['combination']['minimum_total']),50000)

    def test_category_allocation_cannot_be_borrowed_silently(self):
        self.assert_atomic_failure('kombinasi alokasi makanan 19k dan minuman 11k')

    def test_explicit_category_allocations_can_form_feasible_combination(self):
        result=self.reply('kombinasi alokasi makanan 20k dan minuman 10k')
        self.assertEqual(Decimal(result['combination']['minimum_total']),30000)
        self.assertEqual(self.graph()['overall']['category_budgets'],{'Makanan':'20000','Minuman':'10000'})

    def test_approximate_is_never_promoted_to_hard_total(self):
        self.assert_atomic_failure('kombinasi makanan sekitar 20k','Perkiraan')

    def test_explicit_per_menu_bound_is_not_promoted_to_total(self):
        self.assert_atomic_failure('kombinasi makanan maksimal 20k per menu','total')

    def test_new_combination_with_missing_count_does_not_drop_existing_per_person(self):
        self.reply('budget 20k per orang')
        self.assert_atomic_failure('kombinasi makanan','Berapa orang')

    def test_individual_budget_caps_each_person_and_total(self):
        result=self.reply('kombinasi makanan 20k per orang untuk 2 orang masing-masing')
        self.assertEqual(self.quantities(),{self.rice.pk:2})
        self.assertEqual(Decimal(result['combination']['minimum_total']),40000)

    def test_failed_replacement_keeps_existing_combination(self):
        self.reply('30 ribu buat makan dan minum')
        self.assert_atomic_failure('kombinasi 2 makanan dan 1 minuman')

    def test_required_cost_can_make_combination_infeasible(self):
        self.required()
        self.assert_atomic_failure('30 ribu buat makan dan minum')

    def test_new_cheaper_candidate_can_complete_plan(self):
        self.required()
        cheap=MenuItem.objects.create(name='Nasi Putih',price=15000,category=self.food)
        result=self.reply('30 ribu buat makan dan minum')
        self.assertEqual(self.quantities(),{cheap.pk:1,self.juice.pk:1})
        self.assertEqual(Decimal(result['combination']['minimum_total']),25000)

    def test_N21_price_change_before_finish_rejects_whole_draft(self):
        original=ChatbotService._finish_combination
        def changed(service,result):
            MenuItem.objects.filter(pk=self.rice.pk).update(price=21000)
            return original(service,result)
        with patch.object(ChatbotService,'_finish_combination',changed):
            self.assert_atomic_failure('30 ribu buat makan dan minum','melebihi')

    def test_price_change_still_within_budget_updates_final_response_facts(self):
        original=ChatbotService._finish_combination
        def changed(service,result):
            MenuItem.objects.filter(pk=self.rice.pk).update(price=19000)
            return original(service,result)
        with patch.object(ChatbotService,'_finish_combination',changed):
            result=self.reply('30 ribu buat makan dan minum')
        self.assertEqual(Decimal(result['combination']['minimum_total']),29000)
        self.assertIn('29.000',result['message'])

    def test_N22_unavailable_before_finish_rejects_whole_draft(self):
        original=ChatbotService._finish_combination
        def changed(service,result):
            MenuItem.objects.filter(pk=self.juice.pk).update(is_available=False)
            return original(service,result)
        with patch.object(ChatbotService,'_finish_combination',changed):
            self.assert_atomic_failure('30 ribu buat makan dan minum','belum tersedia')

    def test_N23_required_variant_rise_before_finish_rejects_whole_draft(self):
        group,option=self.required(0)
        original=ChatbotService._finish_combination
        def changed(service,result):
            VariantOption.objects.filter(pk=option.pk).update(price_adjustment=5000)
            return original(service,result)
        with patch.object(ChatbotService,'_finish_combination',changed):
            self.assert_atomic_failure('30 ribu buat makan dan minum','melebihi')

    def test_late_category_inactive_is_rejected(self):
        original=ChatbotService._finish_combination
        def changed(service,result):
            Category.objects.filter(pk=self.drinks.pk).update(is_active=False)
            return original(service,result)
        with patch.object(ChatbotService,'_finish_combination',changed):
            self.assert_atomic_failure('30 ribu buat makan dan minum')

    def test_local_drink_budget_does_not_filter_food_role(self):
        self.reply('minuman maksimal 10k')
        result=self.reply('kombinasi makanan minuman budget total 30k')
        self.assertEqual(len(result['recommendations']),2)
        scopes=self.graph()['plan']['scopes']
        self.assertEqual({scope['constraints']['category'] for scope in scopes.values()},{'Makanan','Minuman'})

    def test_global_exclusion_kept(self):
        tag=MenuTag.objects.create(name='shrimp');self.rice.tags.add(tag)
        self.reply('aku alergi udang')
        self.assert_atomic_failure('kombinasi makanan minuman budget total 30k')

    def test_new_explicit_exclusion_in_combo_is_honored(self):
        tag=MenuTag.objects.create(name='shrimp');self.rice.tags.add(tag)
        self.assert_atomic_failure('kombinasi makanan minuman total 30k tanpa udang')

    def test_single_role_positive_requirement_is_honored(self):
        self.assert_atomic_failure('kombinasi makanan ayam total 30k')

    def test_multirole_positive_taste_without_scope_clarifies(self):
        self.assert_atomic_failure('kombinasi makanan minuman pedas total 30k','kategori yang mana')

    def test_negated_combination_does_not_make_plan(self):
        self.assert_atomic_failure('jangan kombinasi makanan minuman total 30k','tanpa kombinasi')

    def test_released_unavailable_item_does_not_block_replacement(self):
        self.reply('budget total 30k');self.reply('nasi goreng')
        self.rice.is_available=False;self.rice.save()
        replacement=MenuItem.objects.create(name='Ayam Geprek',price=19000,category=self.food)
        self.reply('kombinasi makanan minuman')
        self.assertEqual(self.quantities(),{replacement.pk:1,self.juice.pk:1})

    def test_unrequested_role_is_retained_and_charged(self):
        self.reply('30 ribu buat makan dan minum')
        self.reply('kombinasi minuman')
        self.assertEqual(self.quantities(),{self.rice.pk:1,self.juice.pk:1})

    def test_out_of_bounds_is_honest_without_partial_commit(self):
        self.assert_atomic_failure('kombinasi 9 makanan total 200k','delapan')

    def test_no_category_no_fabricated_plan(self):
        self.assert_atomic_failure('kombinasi menu','Kategori')

    def test_schema6_canonical_round_trip_retains_owned_combo_scopes(self):
        self.reply('30 ribu buat makan dan minum')
        decoded=ConversationStore._decode(ConversationStore._encode(dict(self.session)))
        self.assertEqual(decoded[ConversationSession.CONTEXTS_KEY]['plan'],self.graph()['plan'])

    def test_named_paket_menu_stays_entity_not_combination(self):
        item=MenuItem.objects.create(name='Paket 20',price=21000,category=self.food)
        result=self.reply('mau paket 20')
        self.assertEqual([match.item.pk for match in result['recommendations']],[item.pk])
        self.assertNotIn('combination',result)

    @override_settings(GEMINI_ENABLED=False)
    def test_http_combination_is_additive_and_creates_no_transaction(self):
        from orders.models import Order
        with patch('google.genai.Client',side_effect=AssertionError('No SDK')), \
             patch('recommendation.services.gemini.GeminiClient.generate',side_effect=AssertionError('No provider')):
            response=self.client.post('/api/recommendation/chat/',{'message':'30 ribu buat makan dan minum'},content_type='application/json')
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(len(data['recommendations']),2)
        self.assertEqual(Decimal(data['combination']['minimum_total']),30000)
        self.assertEqual(data['recommendations'][0]['price_basis'],'base_price')
        self.assertIn('minimum_payable',data['recommendations'][0])
        self.assertFalse(data['combination']['final_price_confirmed'])
        self.assertEqual(Order.objects.count(),0)
        self.assertNotIn('cart',self.client.session)
