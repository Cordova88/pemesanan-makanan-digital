"""H4: authoritative lower bounds, required-option provenance and stale AI."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import TestCase, override_settings
from menu.models import AddOn, Category, MenuItem, VariantGroup, VariantOption
from menu.selection import MenuSelection

from ..services.chatbot import ChatbotService
from ..services.recommendation import RecommendationService, SearchConstraints
from ..services.response_plan import ResponsePlan
from ..services.tag_extractor import Preferences
from .test_v3_reranking import FakeRanker, ranked


@override_settings(GEMINI_MAX_CALLS_PER_SESSION=50, CHATBOT_AI_WORDING_ENABLED=True)
class MinimumQuoteTests(TestCase):
    def setUp(self) -> None:
        self.category = Category.objects.create(name='Minuman')
        self.a = MenuItem.objects.create(
            name='Es Alpha', category=self.category, price=Decimal('10000')
        )
        self.b = MenuItem.objects.create(
            name='Es Beta', category=self.category, price=Decimal('15000')
        )
        self.group = VariantGroup.objects.create(menu_item=self.a, name='Ukuran', is_required=True)
        self.option = VariantOption.objects.create(
            group=self.group, name='Normal', price_adjustment=Decimal('2000')
        )
        self.provider = FakeRanker(ranked(self.b.pk, self.a.pk))
        self.session = SessionStore()

    def reply(self) -> dict:
        return ChatbotService(self.session, gemini_client=self.provider).reply(
            'enak buat nemenin nugas maksimal 20k'
        )

    def ids(self, result: dict) -> list[int]:
        return [m.item.pk for m in result['recommendations']]

    def plan(self, **kwargs: object) -> ResponsePlan:
        matches = RecommendationService().rank(Preferences(), include_unscored=True)

        return ResponsePlan('recommendation', matches, Preferences(), **kwargs)

    def test_quote_reuses_complete_selection_with_multiple_required_groups(self) -> None:
        group = VariantGroup.objects.create(menu_item=self.a, name='Kemasan', is_required=True)
        option = VariantOption.objects.create(
            group=group, name='Box', price_adjustment=Decimal('500')
        )
        quote = MenuSelection.minimum_quote(self.a)
        self.assertIsNotNone(quote)
        expected = MenuSelection.from_ids(self.a, [self.option.pk, option.pk]).unit_price
        self.assertEqual(quote.minimum_payable, expected)
        self.assertEqual(quote.base_price, Decimal('10000'))
        self.assertEqual(expected, Decimal('12500'))

    def test_incomplete_or_unavailable_quote_is_not_a_base_price_fallback(self) -> None:
        self.option.is_active = False
        self.option.save()
        self.assertIsNone(MenuSelection.minimum_quote(self.a))
        self.option.is_active = True
        self.option.save()
        self.category.is_active = False
        self.category.save()
        self.assertIsNone(MenuSelection.minimum_quote(self.a))  # stale item/category object

    def test_quote_reads_current_base_price_even_from_stale_item(self) -> None:
        MenuItem.objects.filter(pk=self.a.pk).update(price=Decimal('11000'))
        quote = MenuSelection.minimum_quote(self.a)
        self.assertEqual(quote.base_price, Decimal('11000'))
        self.assertEqual(quote.minimum_payable, Decimal('13000'))

    def test_quote_rejects_mutation_during_capture(self) -> None:
        original = MenuSelection.minimum_payable

        def changed(item: MenuItem) -> Decimal | None:
            amount = original(item)
            VariantOption.objects.filter(pk=self.option.pk).update(price_adjustment=Decimal('3000'))

            return amount

        with patch.object(MenuSelection, 'minimum_payable', side_effect=changed):
            self.assertIsNone(MenuSelection.minimum_quote(self.a))

    def test_response_facts_distinguish_base_and_minimum_without_final_claim(self) -> None:
        plan = self.plan(quantities={self.a.pk: 2}, verified_plan_minimum=Decimal('24000'))
        fact = next(row for row in plan.facts if row['id'] == self.a.pk)
        self.assertEqual(fact['price'], '10000.00')
        self.assertEqual(fact['base_price'], '10000.00')
        self.assertEqual(fact['minimum_payable'], '12000.00')
        self.assertEqual(fact['quantity'], 2)
        self.assertEqual(fact['price_basis'], 'minimum_payable')
        self.assertIs(fact['final_price_confirmed'], False)
        self.assertEqual(plan.to_dict()['verified_plan_minimum'], '24000.00')
        facts = plan.facts
        facts[0]['minimum_payable'] = '1'
        self.assertNotEqual(plan.facts, facts)

    def test_alternative_cards_are_not_summed_into_a_joint_plan(self) -> None:
        data = self.plan().to_dict()
        self.assertEqual(len(data['items']), 2)
        self.assertIsNone(data['verified_plan_minimum'])
        self.assertTrue(all(row['quantity'] == 1 for row in data['items']))

    def test_projection_rejects_boolean_or_invalid_quantity_and_total(self) -> None:
        for kwargs in (
            {'quantities': {self.a.pk: True}},
            {'quantities': {self.a.pk: 100}},
            {'verified_plan_minimum': Decimal('NaN')},
            {'verified_plan_minimum': Decimal('-1')},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.plan(**kwargs)

    def test_required_cost_change_within_cap_rejects_stale_semantic_order(self) -> None:
        self.provider.during_call = lambda: VariantOption.objects.filter(pk=self.option.pk).update(
            price_adjustment=Decimal('3000')
        )
        result = self.reply()
        self.assertEqual(self.ids(result), [self.a.pk, self.b.pk])
        self.assertEqual(len(self.provider.prompts), 1)

    def test_same_total_option_replacement_also_rejects_stale_order(self) -> None:
        VariantOption.objects.create(
            group=self.group, name='Pengganti', price_adjustment=Decimal('2000')
        )
        self.provider.during_call = lambda: VariantOption.objects.filter(pk=self.option.pk).update(
            is_active=False
        )
        result = self.reply()
        self.assertEqual(self.ids(result), [self.a.pk, self.b.pk])
        self.assertEqual(MenuSelection.minimum_payable(self.a), Decimal('12000'))

    def test_new_zero_cost_required_group_changes_provenance(self) -> None:
        def add_group() -> None:
            group = VariantGroup.objects.create(
                menu_item=self.a, name='Wajib baru', is_required=True
            )
            VariantOption.objects.create(group=group, name='Gratis')

        self.provider.during_call = add_group
        self.assertEqual(self.ids(self.reply()), [self.a.pk, self.b.pk])

    def test_required_cost_over_cap_is_filtered_after_provider(self) -> None:
        self.provider.during_call = lambda: VariantOption.objects.filter(pk=self.option.pk).update(
            price_adjustment=Decimal('11000')
        )
        result = self.reply()
        self.assertEqual(self.ids(result), [self.b.pk])
        self.assertEqual(len(self.provider.prompts), 1)

    def test_missing_last_required_option_is_filtered_after_provider(self) -> None:
        self.provider.during_call = lambda: VariantOption.objects.filter(pk=self.option.pk).update(
            is_active=False
        )
        self.assertEqual(self.ids(self.reply()), [self.b.pk])

    def test_optional_addon_price_is_not_part_of_unselected_minimum(self) -> None:
        addon = AddOn.objects.create(name='Tambahan', price=Decimal('1000'))
        addon.menu_items.add(self.a)
        self.provider.during_call = lambda: AddOn.objects.filter(pk=addon.pk).update(
            price=Decimal('9000')
        )
        self.assertEqual(self.ids(self.reply()), [self.b.pk, self.a.pk])
        self.assertEqual(MenuSelection.minimum_payable(self.a), Decimal('12000'))

    def test_final_plan_projects_owned_quantity_and_verified_minimum(self) -> None:
        service = ChatbotService(self.session, gemini_client=self.provider)
        service.reply('2 es alpha')
        data = service.response_plan.to_dict()
        self.assertEqual(data['verified_plan_minimum'], '24000.00')
        self.assertEqual(data['items'][0]['quantity'], 2)
        self.assertFalse(data['items'][0]['final_price_confirmed'])
        self.assertEqual(self.provider.prompts, [])

    def test_unstable_pre_call_capture_skips_provider_and_refilters(self) -> None:
        original = MenuSelection.minimum_quote

        def changed(item: MenuItem):
            if item.pk == self.a.pk:
                VariantOption.objects.filter(pk=self.option.pk).update(is_active=False)

            return original(item)

        with patch.object(MenuSelection, 'minimum_quote', side_effect=changed):
            result = self.reply()

        self.assertEqual(self.ids(result), [self.b.pk])
        self.assertEqual(self.provider.prompts, [])

    def test_group_deactivation_rejects_order_even_when_base_is_unchanged(self) -> None:
        self.provider.during_call = lambda: VariantGroup.objects.filter(pk=self.group.pk).update(
            is_active=False
        )
        self.assertEqual(self.ids(self.reply()), [self.a.pk, self.b.pk])
        self.assertEqual(MenuSelection.minimum_quote(self.a).minimum_payable, Decimal('10000'))

    def test_quote_provenance_is_local_and_copied_out_of_response_plan(self) -> None:
        plan = self.plan()
        signatures = plan.quote_signatures
        original = signatures[self.a.pk]
        signatures.clear()
        self.assertEqual(plan.quote_signatures[self.a.pk], original)
        self.assertNotIn('quote_signatures', plan.to_dict())
        self.reply()
        self.assertNotIn('Normal', self.provider.prompts[0])
        self.assertNotIn('price_adjustment', self.provider.prompts[0])

    def test_dormant_wording_boundary_rejects_same_price_provenance_change(self) -> None:
        service = ChatbotService(self.session, gemini_client=self.provider)
        preferences = Preferences()
        constraints = SearchConstraints()
        matches = service.recommender.rank(preferences, include_unscored=True)
        plan = ResponsePlan('recommendation', matches, preferences)

        def changed(*args):
            VariantOption.objects.create(
                group=self.group, name='Pilihan baru', price_adjustment=Decimal('2000')
            )

            return 'Kalimat usang', {}

        with patch.object(service.explanation_service, 'from_plan', side_effect=changed):
            fresh, intro, explanations, unchanged = service._wording_for_plan(
                plan, matches, preferences, constraints
            )

        self.assertEqual([m.item.pk for m in fresh], [self.a.pk, self.b.pk])
        self.assertIsNone(intro)
        self.assertEqual(explanations, {})
        self.assertFalse(unchanged)
        self.assertEqual(self.provider.prompts, [])

    def test_candidate_over_cap_during_pre_call_quote_is_never_sent(self) -> None:
        original = MenuSelection.minimum_quote

        def changed(item: MenuItem):
            if item.pk == self.a.pk:
                VariantOption.objects.filter(pk=self.option.pk).update(
                    price_adjustment=Decimal('11000')
                )

            return original(item)

        with patch.object(MenuSelection, 'minimum_quote', side_effect=changed):
            result = self.reply()

        self.assertEqual(self.ids(result), [self.b.pk])
        self.assertEqual(self.provider.prompts, [])
