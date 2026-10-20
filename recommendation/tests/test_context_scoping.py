"""Approved intent-scoped search, overall plan and safety contracts.

Fixtures are synthetic. R15's genuinely parallel HTTP race is also exercised by
the isolated acceptance harness; the store test below checks the winning graph.
"""
from copy import deepcopy
from decimal import Decimal
import json
from unittest.mock import patch
from collections.abc import Callable

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.core import signing
from django.test import TestCase, override_settings

from menu.models import Category, MenuItem, MenuTag, VariantGroup, VariantOption
from ..services.ai.GeminiInterpreter import GeminiInterpreter, validate
from ..services.chatbot import ChatbotService
from ..services.conversation_interpreter import ConversationInterpretation, PreferenceOperation
from ..services.conversation_session import ConversationSession
from ..services.conversation_store import ConversationStore, ConversationConflict, ConversationStoreUnavailable
from ..services.decision_router import DecisionRouter
from .test_local_conversation import OfflineGenerator


class ContextScopingTests(TestCase):
    def setUp(self) -> None:
        categories = {name: Category.objects.create(name=name) for name in ('Makanan', 'Minuman')}
        tags = {name: MenuTag.objects.create(name=name) for name in ('drink', 'sweet', 'rice', 'chicken', 'spicy', 'shrimp')}
        self.items: dict[str, MenuItem] = {}
        for name, price, category, names in (
            ('Ayam Geprek', 20000, 'Makanan', ('chicken', 'rice', 'spicy')),
            ('Nasi Goreng', 20000, 'Makanan', ('rice',)),
            ('Bubur Ayam', 15000, 'Makanan', ('rice', 'chicken')),
            ('Udang Goreng', 18000, 'Makanan', ('shrimp',)),
            ('Es Jeruk', 10000, 'Minuman', ('drink', 'sweet')),
            ('Es Kelapa', 10000, 'Minuman', ('sweet',)),
            ('Minuman Mahal', 15000, 'Minuman', ('drink',)),
        ):
            item = MenuItem.objects.create(name=name, price=price, category=categories[category])
            item.tags.add(*(tags[tag] for tag in names))
            self.items[name] = item
        self.session = SessionStore()
        self.generator = OfflineGenerator()

    def reply(self, text: str, *, action: str | None = None) -> dict:
        result = ChatbotService(self.session, gemini_client=self.generator).reply(text, action=action)
        self.assertEqual(self.generator.calls, 0)
        self.assertNotIn('cart', self.session)
        ConversationSession.validate_contexts(self.contexts)
        return result

    @property
    def contexts(self) -> dict:
        return self.session[ConversationSession.CONTEXTS_KEY]

    @staticmethod
    def names(result: dict) -> set[str]:
        return {match.item.name for match in result['recommendations']}

    def test_allergy_does_not_capture_ingredients_from_questioned_menu(self) -> None:
        for text in ('aku alergi telur, ayam geprek aman?',
                     'aku alergi telur; ayam geprek aman?',
                     'aku alergi telur. ayam geprek aman?',
                     'aku alergi telur apakah ayam geprek aman?',
                     'ayam geprek aman? aku alergi telur',
                     'aku alergi terhadap telur, boleh makan ayam geprek?',
                     'aku alergi telur tapi mau ayam geprek',
                     'aku alergi: telur ya, ayam geprek aman?',
                     'aku alergi telur, ayam aman?',
                     'aku alergi telur, udang aman?',
                     'aku alergi telur, udang boleh?'):
            with self.subTest(text=text):
                self.session = SessionStore()
                self.reply(text)
                self.assertEqual(self.contexts['safety']['excluded_tags'], ['egg'])
                self.assertTrue(self.contexts['safety']['verification_required'])

    def test_allergy_list_retains_each_explicit_known_ingredient(self) -> None:
        cases = (
            ('aku alergi telur dan udang, ayam geprek aman?', {'egg', 'shrimp'}),
            ('aku alergi telur, udang, dan ikan; ayam geprek aman?', {'egg', 'shrimp', 'fish'}),
            ('aku alergi daging ayam / telur, nasi goreng aman?', {'chicken', 'egg'}),
            ('aku alergi telur, udang, ikan aman?', {'egg', 'shrimp'}),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.session = SessionStore()
                self.reply(text)
                self.assertEqual(set(self.contexts['safety']['excluded_tags']), expected)

    def test_multiple_allergy_declarations_in_one_message_are_preserved(self) -> None:
        self.reply('aku alergi telur dan alergi udang, ayam geprek aman?')
        self.assertEqual(set(self.contexts['safety']['excluded_tags']), {'egg', 'shrimp'})

    def test_allergy_followup_keeps_only_declared_ban_and_staff_warning(self) -> None:
        egg = MenuTag.objects.create(name='egg')
        self.items['Nasi Goreng'].tags.add(egg)
        self.reply('aku alergi telur, ayam geprek aman?')
        result = self.reply('kalau begitu rekomendasikan makanan lain')
        self.assertEqual(self.contexts['safety']['excluded_tags'], ['egg'])
        self.assertNotIn('Nasi Goreng', self.names(result))
        self.assertIn('Ayam Geprek', self.names(result))
        self.assertNotIn('menghindari ayam', result['message'])
        self.assertIn('kontak silang', result['message'])
        self.assertIn('tidak menjamin', result['message'])

    def test_unmapped_allergen_does_not_become_questioned_menu_ingredient(self) -> None:
        for text in ('aku alergi kentang, ayam geprek aman?',
                     'aku alergi susu, ayam geprek aman?',
                     'aku alergi susu dan telur, ayam geprek aman?'):
            with self.subTest(text=text):
                self.session = SessionStore()
                result = self.reply(text)
                self.assertEqual(self.contexts['safety']['excluded_tags'], ['egg'] if 'telur' in text else [])
                self.assertTrue(self.contexts['safety']['verification_required'])
                self.assertIn('staf', result['message'])
                self.assertEqual(result['recommendations'], [])

    def test_new_allergy_adds_to_existing_safety_without_menu_contamination(self) -> None:
        self.reply('aku alergi udang')
        self.reply('aku alergi telur, ayam geprek aman?')
        self.reply('telur boleh')
        self.assertEqual(set(self.contexts['safety']['excluded_tags']), {'egg', 'shrimp'})
        self.assertTrue(self.contexts['safety']['verification_required'])

    def test_linked_comparison_carries_budget_to_named_cross_category_item(self) -> None:
        for question in ('kalau ayam geprek?', 'bagaimana dengan ayam geprek?', 'gimana kalau ayam geprek?'):
            with self.subTest(question=question):
                self.session = SessionStore()
                self.reply('minuman maksimal 10 ribu')
                result = self.reply(question)
                self.assertEqual(result['active_search']['max_price'], 10000)
                self.assertEqual(result['recommendations'], [])
                self.assertIn('10.000', result['message'])
                self.assertEqual(self.contexts['overall'], {})

    def test_category_only_linked_comparison_keeps_budget_but_not_drink_tags(self) -> None:
        self.reply('minuman maksimal 10 ribu')
        result = self.reply('kalau makanan?')
        self.assertEqual(result['active_search']['category'], 'Makanan')
        self.assertEqual(result['active_search']['max_price'], 10000)
        self.assertEqual(result['recommendations'], [])
        self.assertNotIn('drink', result['active_search']['required_tags'])

    def test_linked_comparison_with_new_price_replaces_instead_of_inherits(self) -> None:
        self.reply('minuman maksimal 10 ribu')
        result = self.reply('kalau ayam geprek maksimal 25 ribu?')
        self.assertEqual(result['active_search']['max_price'], 25000)
        self.assertEqual(self.names(result), {'Ayam Geprek'})

    def test_new_minimum_replaces_entire_old_maximum(self) -> None:
        self.reply('minuman maksimal 10 ribu')
        result = self.reply('minimal 1 juta rupiah')
        budget = result['active_search']['budget']
        self.assertEqual(budget['minimum'], '1000000')
        self.assertIsNone(budget['maximum'])
        self.assertEqual(result['recommendations'], [])

    def test_no_price_followup_keeps_budget_but_unlinked_food_switch_drops_it(self) -> None:
        self.reply('minuman maksimal 10 ribu')
        same = self.reply('yang lain')
        self.assertEqual(same['active_search']['max_price'], 10000)
        switched = self.reply('sekarang makanan')
        self.assertIsNone(switched['active_search']['max_price'])
        self.assertEqual(switched['active_search']['category'], 'Makanan')

    def test_comparison_does_not_bypass_global_allergy(self) -> None:
        self.reply('aku alergi ayam')
        self.reply('minuman maksimal 25 ribu')
        result = self.reply('kalau ayam geprek?')
        self.assertEqual(result['recommendations'], [])
        self.assertIn('chicken', self.contexts['safety']['excluded_tags'])

    def test_named_price_question_answers_catalog_without_changing_search_scope(self) -> None:
        self.reply('minuman maksimal 10 ribu')
        before = deepcopy(self.contexts)
        result = self.reply('berapa harga ayam geprek?')
        self.assertIn('Ayam Geprek', result['message'])
        self.assertIn('20.000', result['message'])
        self.assertEqual(result['recommendations'], [])
        self.assertEqual(self.contexts['active']['id'], before['active']['id'])
        self.assertEqual(self.contexts['active']['constraints'], before['active']['constraints'])
        self.assertEqual(self.contexts['previous'], before['previous'])
        self.assertEqual(self.contexts['plan'], before['plan'])
        self.assertEqual(self.contexts['transition']['action'], 'CONTINUE_CONTEXT')

    def test_named_price_question_does_not_quote_unavailable_item(self) -> None:
        self.items['Ayam Geprek'].is_available = False
        self.items['Ayam Geprek'].save(update_fields=['is_available'])
        result = self.reply('berapa harga ayam geprek?')
        self.assertEqual(result['recommendations'], [])
        self.assertNotIn('20.000', result['message'])
        self.assertIn('tersedia', result['message'])

    def test_bagaimana_dengan_preserves_exact_menu_identity(self) -> None:
        self.reply('minuman maksimal 10 ribu')
        result = self.reply('bagaimana dengan ayam geprek maksimal 25 ribu?')
        self.assertEqual(self.names(result), {'Ayam Geprek'})
        self.assertEqual(result['active_search']['max_price'], 25000)

    def test_R01_cross_category_item_ignores_only_archived_local_cap(self) -> None:
        self.reply('minuman 10k')
        result = self.reply('aku mau ayam geprek')
        self.assertEqual(self.names(result), {'Ayam Geprek'})
        self.assertIsNone(result['active_search']['max_price'])
        self.assertEqual(self.contexts['transition']['action'], 'SWITCH_CONTEXT')
        self.assertEqual(self.contexts['previous'][-1]['constraints']['budget']['maximum'], '10000')
        self.assertTrue(self.contexts['transition']['ignored_constraint_ids'])

    def test_R02_same_category_item_keeps_cap_even_without_drink_tag(self) -> None:
        self.reply('minuman 10k')
        result = self.reply('yang es kelapa')
        self.assertEqual(self.names(result), {'Es Kelapa'})
        self.assertEqual(result['active_search']['max_price'], 10000)
        self.assertEqual(self.contexts['transition']['action'], 'CONTINUE_CONTEXT')

    def test_R03_explicit_restore_recovers_beverage_context(self) -> None:
        self.reply('minuman 10k')
        self.reply('ayam geprek')
        result = self.reply('balik ke minuman tadi')
        self.assertEqual(result['active_search']['category'], 'Minuman')
        self.assertEqual(result['active_search']['max_price'], 10000)
        self.assertEqual(self.contexts['transition']['action'], 'REFER_TO_PREVIOUS')
        self.assertTrue(all(match.item.category.name == 'Minuman' for match in result['recommendations']))

    def test_R04_add_creates_draft_without_applying_drink_cap_to_food(self) -> None:
        self.reply('minuman 10k')
        self.reply('es kelapa')
        result = self.reply('sekalian ayam geprek')
        self.assertEqual(self.names(result), {'Ayam Geprek'})
        self.assertIsNone(result['active_search']['max_price'])
        self.assertEqual(self.contexts['transition']['action'], 'ADD_TO_CONTEXT')
        self.assertEqual({entry['menu_id'] for entry in self.contexts['plan']['entries']},
                         {self.items['Es Kelapa'].pk, self.items['Ayam Geprek'].pk})

    def test_R05_total_is_not_per_item_cap(self) -> None:
        self.reply('budget total 30k untuk makanan dan minuman')
        result = self.reply('ayam geprek')
        self.assertEqual(self.names(result), {'Ayam Geprek'})
        self.assertEqual(self.contexts['overall']['total_budget'], '30000')
        self.assertIsNone(result['active_search']['max_price'])
        self.assertIn('sementara', result['message'])

    def test_R06_new_drink_request_applies_its_own_budget(self) -> None:
        self.reply('ayam geprek')
        result = self.reply('minuman 10k')
        self.assertEqual(self.names(result), {'Es Jeruk', 'Es Kelapa'})
        self.assertEqual(result['active_search']['max_price'], 10000)
        self.assertEqual(self.contexts['transition']['action'], 'SWITCH_CONTEXT')

    def test_R07_fresh_beverage_search_does_not_reactivate_archive(self) -> None:
        self.reply('minuman 10k')
        self.reply('nasi goreng')
        result = self.reply('es jeruk')
        self.assertEqual(self.names(result), {'Es Jeruk'})
        self.assertIsNone(result['active_search']['max_price'])

    def test_R08_correction_same_scope_retains_budget(self) -> None:
        self.reply('minuman 10k')
        result = self.reply('eh es kelapa aja')
        self.assertEqual(self.names(result), {'Es Kelapa'})
        self.assertEqual(result['active_search']['max_price'], 10000)
        self.assertEqual(self.contexts['transition']['action'], 'CORRECT_PREVIOUS')

    def test_R09_alternatives_are_same_scope(self) -> None:
        self.reply('minuman 10k')
        self.reply('es jeruk')
        result = self.reply('yang lain')
        self.assertNotIn('Es Jeruk', self.names(result))
        self.assertNotIn('Minuman Mahal', self.names(result))
        self.assertEqual(result['active_search']['max_price'], 10000)

    def test_R10_overall_sum_blocks_add_and_preserves_plan(self) -> None:
        self.reply('budget total 30k untuk makanan dan minuman')
        self.reply('ayam geprek')
        before = deepcopy(self.contexts['plan'])
        result = self.reply('sekalian nasi goreng')
        self.assertFalse(result['recommendations'])
        self.assertIn('melebihi', result['message'])
        self.assertEqual(self.contexts['plan'], before)
        self.assertEqual(self.contexts['overall']['total_budget'], '30000')
        self.assertEqual(self.contexts['transition']['action'], 'CLARIFY')

    def test_R11_specific_item_ban_does_not_leak_to_new_item(self) -> None:
        self.reply('bubur ayam')
        self.reply('jangan pedas untuk makanan ini')
        result = self.reply('sekarang ayam geprek')
        self.assertEqual(self.names(result), {'Ayam Geprek'})
        self.assertNotIn('spicy', result['active_search']['excluded_tags'])

    def test_R12_safety_persists_across_new_search_and_restore(self) -> None:
        self.reply('aku alergi udang')
        result = self.reply('makanan')
        self.assertNotIn('Udang Goreng', self.names(result))
        self.assertIn('staf', result['message'])
        self.assertIn('shrimp', self.contexts['safety']['excluded_tags'])
        result = self.reply('aku mau udang goreng')
        self.assertFalse(result['recommendations'])
        self.assertIn('kontak silang', result['message'])

    def test_R13_reset_clears_context_not_usage_or_other_owned_session(self) -> None:
        self.reply('minuman 10k')
        self.reply('aku alergi udang')
        self.session['gemini_calls'] = 7
        self.session['_auth_user_id'] = 'synthetic'
        result = self.reply('', action='reset')
        self.assertIn('Sampaikan kembali alergi', result['message'])
        self.assertEqual(self.contexts['previous'], [])
        self.assertEqual(self.contexts['safety']['excluded_tags'], [])
        self.assertEqual(self.session['gemini_calls'], 7)
        self.assertEqual(self.session['_auth_user_id'], 'synthetic')
        self.assertEqual(self.names(self.reply('ayam geprek')), {'Ayam Geprek'})

    def test_R14_missing_reference_clarifies_without_target(self) -> None:
        result = self.reply('yang itu')
        self.assertFalse(result['recommendations'])
        self.assertIsNone(ConversationSession(self.session).get_focus())
        self.assertEqual(self.contexts['transition']['action'], 'CLARIFY')

    def test_R15_losing_writer_cannot_mix_context_and_safety(self) -> None:
        self.reply('minuman 10k')
        initial = ConversationStore('context-test', self.session)
        base_revision = initial.commit()
        first = ConversationStore('context-test', self.session, base_revision)
        second = ConversationStore('context-test', self.session, base_revision)
        ChatbotService(first.session, gemini_client=self.generator).reply('ayam geprek')
        ChatbotService(second.session, gemini_client=self.generator).reply('alergi udang')
        first.commit()
        with self.assertRaises(ConversationConflict):
            second.commit()
        current = ConversationStore('context-test', self.session)
        graph = current.session[ConversationSession.CONTEXTS_KEY]
        self.assertEqual(graph['active']['focused_item_id'], self.items['Ayam Geprek'].pk)
        self.assertEqual(graph['safety']['excluded_tags'], [])
        self.assertEqual(current.revision, base_revision + 1)

    def test_history_is_bounded_and_does_not_capture_auth_or_cart(self) -> None:
        self.session['_auth_user_id'] = 'PRIVATE_CANARY'
        for text in ['minuman 10k', 'ayam geprek', 'es jeruk', 'nasi goreng', 'es kelapa', 'bubur ayam', 'minuman']:
            self.reply(text)
        self.assertEqual(len(self.contexts['previous']), 4)
        self.assertNotIn('PRIVATE_CANARY', json.dumps(self.contexts))
        self.assertLess(len(ConversationStore._encode(dict(self.session_without_auth()))), ConversationStore.MAX_BYTES * 2)

    def session_without_auth(self) -> dict:
        return {key: value for key, value in self.session.items() if ConversationSession._owned_key(key)}

    def test_schema3_migration_preserves_quota_and_does_not_invent_total_or_safety(self) -> None:
        self.session.update({ConversationSession.SCHEMA_KEY: 3, 'gemini_calls': 5,
                             ConversationSession.SEARCH_KEY: {'category': 'Minuman', 'max_price': 10000, 'excluded_tags': ['spicy']}})
        result = self.reply('ayam geprek')
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.contexts['overall'], {})
        self.assertEqual(self.contexts['safety']['excluded_tags'], [])
        self.assertTrue(self.contexts['active']['legacy_unresolved'])
        self.assertEqual(self.session['gemini_calls'], 5)

    def test_invalid_graph_is_rejected_on_encode_and_decode(self) -> None:
        self.reply('minuman 10k')
        valid = deepcopy(self.session_without_auth())
        mutations = (
            lambda graph: graph['safety'].update(verification_required='false'),
            lambda graph: graph['overall'].update(total_budget='NaN'),
            lambda graph: graph['previous'].extend([deepcopy(graph['active'])] * 5),
            lambda graph: graph['active']['projection'].update(cart={'secret': True}),
            lambda graph: graph['active']['projection'].update(recommendation_candidate_ids=[True]),
            lambda graph: graph['active']['constraints'].update(excluded_tags='shrimp'),
            lambda graph: graph['plan'].update(unresolved_roles=[{}]),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                state = deepcopy(valid)
                mutate(state[ConversationSession.CONTEXTS_KEY])
                with self.assertRaises(ConversationStoreUnavailable):
                    ConversationStore._encode(state)
                encoded = signing.dumps({'schema': 1, 'state': state}, salt=ConversationStore.SALT)
                with self.assertRaises(ConversationStoreUnavailable):
                    ConversationStore._decode(encoded)

    def test_group_budget_correction_changes_total_without_per_menu_division(self) -> None:
        self.reply('40 ribu buat berdua')
        self.reply('maksudku 50 ribu')
        self.assertEqual(self.contexts['overall']['total_budget'], '50000')
        self.assertEqual(self.contexts['overall']['person_count'], 2)
        self.assertIsNone(ConversationSession(self.session).load_constraints().max_price)

    def test_local_caps_switch_inside_plan_without_erasing_overall(self) -> None:
        self.reply('budget total 30k untuk makanan dan minuman')
        self.reply('ayam geprek')
        result = self.reply('minuman 10k')
        self.assertEqual(result['active_search']['max_price'], 10000)
        result = self.reply('bubur ayam')
        self.assertEqual(self.names(result), {'Bubur Ayam'})
        self.assertIsNone(result['active_search']['max_price'])
        self.assertEqual(self.contexts['overall']['total_budget'], '30000')

    def test_required_variant_minimum_prevents_false_affordable_plan(self) -> None:
        group = VariantGroup.objects.create(menu_item=self.items['Ayam Geprek'], name='Porsi', is_required=True)
        VariantOption.objects.create(group=group, name='Wajib', price_adjustment=15000)
        self.reply('budget total 30k untuk makanan dan minuman')
        before = deepcopy(self.contexts['plan'])
        result = self.reply('ayam geprek')
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.contexts['plan'], before)
        self.assertIn('45.000', result['message'])  # Required food35000 + retained drink10000.

    def test_changed_availability_blocks_next_plan_add(self) -> None:
        self.reply('budget total 30k untuk makanan dan minuman')
        self.reply('ayam geprek')
        self.items['Ayam Geprek'].is_available = False
        self.items['Ayam Geprek'].save(update_fields=['is_available'])
        before = deepcopy(self.contexts['plan'])
        result = self.reply('sekalian es kelapa')
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.contexts['plan'], before)
        self.assertIn('belum tersedia', result['message'])

    def test_failure_after_transition_rolls_back_all_business_state(self) -> None:
        self.reply('minuman 10k')
        before = deepcopy(dict(self.session))
        with patch.object(ChatbotService, '_reply_turn', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                self.reply('ayam geprek')
        self.assertEqual(dict(self.session), before)

    def test_generic_search_obeys_overall_without_choosing_every_card(self) -> None:
        self.reply('budget total 10k untuk makanan dan minuman')
        result = self.reply('makanan')
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.contexts['plan']['entries'], [])
        result = self.reply('minuman')
        self.assertEqual(self.names(result), {'Es Jeruk', 'Es Kelapa'})
        self.assertEqual(self.contexts['plan']['entries'], [])
        self.assertIsNone(result['active_search']['max_price'])

    def test_generic_add_checks_remaining_total_but_does_not_commit_cards(self) -> None:
        self.reply('budget total 30k untuk makanan dan minuman')
        self.reply('ayam geprek')
        before = deepcopy(self.contexts['plan'])
        result = self.reply('sekalian minuman')
        self.assertFalse(result['recommendations'])  # The auto-filled drink already uses the remaining total.
        self.assertEqual(self.contexts['plan'], before)
        self.assertNotIn('Minuman Mahal', self.names(result))

    def test_generic_add_remembers_explicit_focus_then_fills_selected_role(self) -> None:
        self.reply('ayam geprek')
        result = self.reply('sekalian minuman')
        self.assertTrue(result['recommendations'])
        self.assertEqual([entry['menu_id'] for entry in self.contexts['plan']['entries']], [self.items['Ayam Geprek'].pk])
        self.reply('es kelapa')
        self.assertEqual({entry['menu_id'] for entry in self.contexts['plan']['entries']},
                         {self.items['Ayam Geprek'].pk, self.items['Es Kelapa'].pk})
        self.assertEqual(self.contexts['plan']['unresolved_roles'], [])

    def test_deferred_tag_is_removed_without_becoming_global_ban(self) -> None:
        self.reply('minuman manis 10k')
        result = self.reply('yang manis nanti aja')
        self.assertNotIn('sweet', result['active_search']['required_tags'])
        self.assertNotIn('sweet', result['active_search']['excluded_tags'])
        self.assertEqual(result['active_search']['max_price'], 10000)
        self.assertEqual(self.contexts['safety']['excluded_tags'], [])

    def test_new_million_budget_is_local_and_does_not_change_catalog_price(self) -> None:
        self.reply('minuman 10k')
        result = self.reply('ayam geprek budget 1 juta')
        self.assertEqual(self.names(result), {'Ayam Geprek'})
        self.assertEqual(result['active_search']['max_price'], 1000000)
        self.assertEqual(result['recommendations'][0].item.price, Decimal(20000))
        self.assertEqual(self.contexts['overall'], {})

    def test_legacy_scope_question_can_be_resolved_once_naturally(self) -> None:
        self.session.update({ConversationSession.SCHEMA_KEY: 3,
                             ConversationSession.SEARCH_KEY: {'category': 'Minuman', 'max_price': 10000, 'excluded_tags': ['spicy']}})
        self.assertFalse(self.reply('ayam geprek')['recommendations'])
        self.reply('hanya untuk pilihan tadi')
        result = self.reply('ayam geprek')
        self.assertEqual(self.names(result), {'Ayam Geprek'})
        self.assertFalse(self.contexts['active']['legacy_unresolved'])

    def test_unknown_future_scoped_schema_fails_closed_instead_of_reset(self) -> None:
        self.reply('alergi udang')
        self.session[ConversationSession.SCHEMA_KEY] = 99
        before = deepcopy(dict(self.session))
        with self.assertRaises(ValueError):
            self.reply('udang goreng')
        self.assertEqual(dict(self.session), before)

    def test_correction_replaces_focused_plan_item_not_all_items_of_category(self) -> None:
        self.reply('budget total 60k untuk makanan dan minuman')
        self.reply('ayam geprek')
        self.reply('sekalian bubur ayam')
        self.reply('eh nasi goreng aja')
        self.assertEqual({entry['menu_id'] for entry in self.contexts['plan']['entries']},
                         {self.items['Ayam Geprek'].pk, self.items['Nasi Goreng'].pk, self.items['Es Jeruk'].pk})
        self.assertEqual(self.contexts['transition']['action'], 'CORRECT_PREVIOUS')

    def test_cross_category_correction_clears_local_scope_and_keeps_overall(self) -> None:
        self.reply('budget total 60k untuk makanan dan minuman')
        self.reply('minuman 10k')
        self.reply('es kelapa')
        result = self.reply('eh ayam geprek aja')
        self.assertEqual(self.names(result), {'Ayam Geprek'})
        self.assertIsNone(result['active_search']['max_price'])
        self.assertEqual({entry['menu_id'] for entry in self.contexts['plan']['entries']},
                         {self.items['Bubur Ayam'].pk,self.items['Ayam Geprek'].pk})

    def reply_after_catalog_change(self, text: str, mutate: Callable[[], object]) -> dict:
        original = ChatbotService._reply_turn

        def changed(service: ChatbotService, *args: object, **kwargs: object) -> dict:
            result = original(service, *args, **kwargs)
            mutate()
            return result

        with patch.object(ChatbotService, '_reply_turn', changed):
            return self.reply(text)

    def prepare_two_foods(self) -> dict:
        self.reply('budget total 50k untuk makanan dan minuman')
        self.reply('ayam geprek')
        self.reply('sekalian bubur ayam')
        return deepcopy(self.contexts['plan'])

    def test_late_price_change_validates_exact_corrected_plan(self) -> None:
        before = self.prepare_two_foods()
        result = self.reply_after_catalog_change('eh nasi goreng aja',
            lambda: MenuItem.objects.filter(pk=self.items['Ayam Geprek'].pk).update(price=35000))
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.contexts['plan'], before)
        self.assertEqual(ConversationSession(self.session).get_focus(), self.items['Bubur Ayam'].pk)
        self.assertEqual(self.contexts['transition']['action'], 'CLARIFY')

    def test_late_unavailability_does_not_commit_corrected_plan(self) -> None:
        before = self.prepare_two_foods()
        result = self.reply_after_catalog_change('eh nasi goreng aja',
            lambda: MenuItem.objects.filter(pk=self.items['Ayam Geprek'].pk).update(is_available=False))
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.contexts['plan'], before)

    def test_late_required_variant_change_obeys_overall(self) -> None:
        group = VariantGroup.objects.create(menu_item=self.items['Ayam Geprek'], name='Porsi', is_required=True)
        option = VariantOption.objects.create(group=group, name='Reguler', price_adjustment=0)
        before = self.prepare_two_foods()
        result = self.reply_after_catalog_change('eh nasi goreng aja',
            lambda: VariantOption.objects.filter(pk=option.pk).update(price_adjustment=15000))
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.contexts['plan'], before)

    def test_late_allergen_tag_change_revalidates_remaining_plan_item(self) -> None:
        self.reply('aku alergi udang')
        before = self.prepare_two_foods()
        shrimp = MenuTag.objects.get(name='shrimp')
        result = self.reply_after_catalog_change('eh nasi goreng aja',
            lambda: self.items['Ayam Geprek'].tags.add(shrimp))
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.contexts['plan'], before)
        self.assertIn('shrimp', self.contexts['safety']['excluded_tags'])

    def test_late_affordable_price_change_refreshes_card(self) -> None:
        self.reply('budget total 60k untuk makanan dan minuman')
        self.reply('ayam geprek')
        result = self.reply_after_catalog_change('eh nasi goreng aja',
            lambda: MenuItem.objects.filter(pk=self.items['Nasi Goreng'].pk).update(price=25000))
        self.assertEqual(self.names(result), {'Nasi Goreng'})
        self.assertEqual(result['recommendations'][0].item.price, Decimal(25000))
        self.assertIn('35.000', result['message'])  # Nasi25000 + existing drink10000.

    def test_archived_beverage_cap_is_checked_when_plan_price_changes(self) -> None:
        self.reply('budget total 60k untuk makanan dan minuman')
        self.reply('minuman 10k')
        self.reply('es kelapa')
        before = deepcopy(self.contexts['plan'])
        result = self.reply_after_catalog_change('sekalian ayam geprek',
            lambda: MenuItem.objects.filter(pk=self.items['Es Kelapa'].pk).update(price=15000))
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.contexts['plan'], before)

    def test_group_correction_retains_people_and_plan_entries(self) -> None:
        self.reply('50 ribu buat berdua')
        self.reply('ayam geprek')
        before = deepcopy(self.contexts['plan'])
        self.reply('maksudku 60 ribu')
        self.assertEqual(self.contexts['plan'], before)
        self.assertEqual(self.contexts['overall']['person_count'], 2)
        self.assertEqual(self.contexts['overall']['total_budget'], '60000')
        self.assertIsNone(ConversationSession(self.session).load_constraints().max_price)

    def test_lower_overall_correction_rejects_without_partial_budget_commit(self) -> None:
        before = self.prepare_two_foods()
        result = self.reply('maksudku 30 ribu')
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.contexts['plan'], before)
        self.assertEqual(self.contexts['overall']['total_budget'], '50000')

    def test_unavailable_replaced_item_does_not_block_valid_exact_replacement(self) -> None:
        self.reply('budget total 50k untuk makanan dan minuman')
        self.reply('ayam geprek')
        self.reply('sekalian es kelapa')
        result = self.reply_after_catalog_change('eh bubur ayam aja',
            lambda: MenuItem.objects.filter(pk=self.items['Es Kelapa'].pk).update(is_available=False))
        self.assertEqual(self.names(result), {'Bubur Ayam'})
        self.assertEqual({entry['menu_id'] for entry in self.contexts['plan']['entries']},
                         {self.items['Ayam Geprek'].pk, self.items['Bubur Ayam'].pk,self.items['Es Jeruk'].pk})

    def test_final_plan_checks_do_not_apply_item_ban_to_other_entries(self) -> None:
        before = self.prepare_two_foods()
        self.reply('jangan pedas untuk makanan ini')
        self.assertEqual(self.contexts['plan'], before)
        self.assertEqual(ConversationSession(self.session).get_focus(), self.items['Bubur Ayam'].pk)
        result = self.reply('eh nasi goreng aja')
        self.assertEqual(self.names(result), {'Nasi Goreng'})
        self.assertEqual({entry['menu_id'] for entry in self.contexts['plan']['entries']},
                         {self.items['Ayam Geprek'].pk, self.items['Nasi Goreng'].pk,self.items['Es Jeruk'].pk})
        self.assertNotIn('spicy', result['active_search']['excluded_tags'])

    def test_http_late_failure_commits_only_clarification_and_usage(self) -> None:
        with patch('recommendation.services.gemini.GeminiClient.generate', side_effect=AssertionError('No real provider')) as provider:
            for text in ('budget total 50k untuk makanan dan minuman', 'ayam geprek', 'sekalian bubur ayam'):
                response = self.client.post('/api/recommendation/chat/', {'message': text}, content_type='application/json')
                self.assertEqual(response.status_code, 200)
            revision = response.json()['revision']
            main = self.client.session
            store = ConversationStore(main['chatbot_client_id'], main)
            before = deepcopy(store.session[ConversationSession.CONTEXTS_KEY])
            original = ChatbotService._reply_turn

            def changed(service: ChatbotService, *args: object, **kwargs: object) -> dict:
                result = original(service, *args, **kwargs)
                service._session_state.consume_gemini_call(8)  # Simulated charged attempt, no SDK/network.
                MenuItem.objects.filter(pk=self.items['Ayam Geprek'].pk).update(price=35000)
                return result

            with patch.object(ChatbotService, '_reply_turn', changed):
                response = self.client.post('/api/recommendation/chat/',
                    {'message': 'eh nasi goreng aja', 'revision': revision}, content_type='application/json')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['revision'], revision + 1)
            self.assertFalse(response.json()['recommendations'])
            current = ConversationStore(main['chatbot_client_id'], self.client.session)
            after = current.session[ConversationSession.CONTEXTS_KEY]
            for key in ('previous', 'overall', 'safety', 'plan'):
                self.assertEqual(after[key], before[key])
            self.assertEqual(after['active']['focused_item_id'], self.items['Bubur Ayam'].pk)
            self.assertEqual(after['transition']['action'], 'CLARIFY')
            self.assertEqual(current.session['gemini_calls'], 1)
            self.assertNotIn('cart', self.client.session)
            provider.assert_not_called()

    @override_settings(CHATBOT_CONTEXT_SWITCHING_ENABLED=False)
    def test_rollback_flag_retains_graph_and_constraints(self) -> None:
        with override_settings(CHATBOT_CONTEXT_SWITCHING_ENABLED=True):
            self.reply('minuman 10k')
            self.reply('aku alergi udang')
        before = deepcopy(self.contexts)
        result = self.reply('ayam geprek')
        self.assertFalse(result['recommendations'])
        self.assertIn('pemeliharaan', result['message'])
        for key in ('previous', 'overall', 'safety', 'plan'):
            self.assertEqual(self.contexts[key], before[key])
        self.assertEqual(self.contexts['active']['constraints'], before['active']['constraints'])


class ContextProposalTests(TestCase):
    def test_v2_proposal_metadata_is_strict_and_cannot_override_local_scope(self) -> None:
        wire = {'intent': 'RECOMMEND', 'add_tags': ['sweet'], 'remove_tags': [], 'excluded_tags': [],
                'soft_excluded_tags': [], 'moods': [], 'clear_moods': False, 'max_price': None,
                'prefer_affordable': None, 'clear_max_price': False, 'clear_prefer_affordable': False,
                'message_is_meaningful': True, 'proposal_version': 2,
                'context_action': 'CONTINUE_CONTEXT', 'constraint_scope': 'CURRENT_SEARCH'}
        self.assertTrue(validate(wire, {'sweet'}, set()))
        for invalid in ({'proposal_version': True}, {'context_action': 'DELETE'}, {'constraint_scope': 'GLOBAL'}, {'unknown': 1}):
            self.assertFalse(validate(wire | invalid, {'sweet'}, set()))
        generator = OfflineGenerator()
        interpreter = GeminiInterpreter(generator, allowed_tags={'sweet', 'shrimp'})
        with patch.object(generator, 'generate', return_value=json.dumps(wire)):
            proposal = interpreter.interpret('synthetic', {'context_action': 'CONTINUE_CONTEXT', 'constraint_scope': 'CURRENT_SEARCH'})
        self.assertIsNotNone(proposal)
        local = ConversationInterpretation('RECOMMEND', operations=[PreferenceOperation('KEEP')],
                                          context_action='CONTINUE_CONTEXT', constraint_scope='CURRENT_SEARCH')
        self.assertTrue(DecisionRouter.accepts_proposal(proposal, allowed_tags={'sweet'}, local=local, hard_exclusions=set()))
        proposal.context_action = 'SWITCH_CONTEXT'
        self.assertFalse(DecisionRouter.accepts_proposal(proposal, allowed_tags={'sweet'}, local=local, hard_exclusions=set()))
        proposal.context_action = local.context_action
        proposal.clear_max_price = True
        self.assertFalse(DecisionRouter.accepts_proposal(proposal, allowed_tags={'sweet'}, local=local, hard_exclusions=set()))
        proposal.clear_max_price = False
        self.assertFalse(DecisionRouter.accepts_proposal(proposal, allowed_tags={'sweet'}, local=local, hard_exclusions={'sweet'}))
