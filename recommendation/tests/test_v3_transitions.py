"""V3 Phase1 catalog language, state separation and draft-turn regressions."""

from copy import deepcopy
from decimal import Decimal
import json
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase

from menu.models import Category, MenuItem, MenuTag
from ..services.chatbot import ChatbotService
from ..services.conversation_interpreter import (
    ConversationInterpretation,
    ConversationIntent,
    ConversationInterpreter,
)
from ..services.conversation_session import ConversationSession
from ..services.entity_resolver import EntityResolver
from ..services.tag_extractor import Preferences
from .test_local_conversation import OfflineGenerator


class V3CatalogLanguageTests(SimpleTestCase):
    def setUp(self) -> None:
        self.resolver = EntityResolver(
            ((1, 'Es Jeruk'), (2, 'Es Kelapa'), (3, 'Es Jeruk Manis')), ('dingin', 'manis')
        )

    def test_fillers_and_correction_markers_are_not_full_sentence_special_cases(self) -> None:
        for text in (
            'eh yang es jeruk aja deh',
            'oh, pilih es jeruk dong',
            'maksudku es jeruk',
            'ganti ke es jeruk',
            'eh es jeruk aja',
            'es jeruk',
        ):
            with self.subTest(text=text):
                self.assertEqual(self.resolver.resolve(text).menu_ids, (1,))

    def test_negated_source_is_not_the_positive_target(self) -> None:
        for text in (
            'bukan es kelapa, es jeruk aja',
            'jangan es kelapa, pilih es jeruk',
            'aku tidak mau es kelapa, es jeruk saja',
        ):
            with self.subTest(text=text):
                result = self.resolver.resolve(text)
                self.assertEqual(result.menu_ids, (1,))
                self.assertEqual(result.rejected_menu_ids, (2,))

    def test_switch_source_is_not_automatically_rejected(self) -> None:
        result = self.resolver.resolve('ganti es kelapa ke es jeruk')
        self.assertEqual(result.menu_ids, (1,))
        self.assertFalse(result.rejected_menu_ids)

    def test_duplicate_names_and_multiple_positive_choices_clarify(self) -> None:
        duplicate = EntityResolver(((1, 'Es Jeruk'), (2, 'Es Jeruk')))
        self.assertEqual(duplicate.resolve('aku mau es jeruk').domain_status, 'AMBIGUOUS_CATALOG')
        self.assertEqual(
            self.resolver.resolve('aku mau es jeruk atau es kelapa').domain_status,
            'AMBIGUOUS_CATALOG',
        )

    def test_longest_catalog_name_has_priority_over_nested_name(self) -> None:
        self.assertEqual(self.resolver.resolve('eh yang es jeruk manis aja').menu_ids, (3,))

    def test_consumed_item_and_generic_reference_are_not_new_selections(self) -> None:
        self.assertIsNone(self.resolver.resolve('aku habis minum es jeruk lalu kerja'))
        self.assertIsNone(self.resolver.resolve('yang terakhir'))
        self.assertIsNone(self.resolver.resolve('yang lebih murah'))

    def test_alternatives_and_explicit_rejections_have_different_operations(self) -> None:
        interpreter = ConversationInterpreter()
        self.assertEqual(
            interpreter.interpret('yang lain').intent, ConversationIntent.REQUEST_ALTERNATIVES
        )
        self.assertEqual(
            interpreter.interpret('tidak cocok').intent, ConversationIntent.REJECT_RECOMMENDATION
        )

    def test_interpretation_target_and_source_are_typed_and_allowlisted(self) -> None:
        for kwargs in (
            {'target_menu_id': True},
            {'target_menu_id': -1},
            {'source': 'exec'},
            {'rejected_menu_ids': (True,)},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ConversationInterpretation(ConversationIntent.SELECT_RECOMMENDATION, **kwargs)

        local = ConversationInterpretation(
            ConversationIntent.SELECT_RECOMMENDATION, target_menu_id=1
        )
        other = ConversationInterpretation(
            ConversationIntent.SELECT_RECOMMENDATION, target_menu_id=2
        )
        self.assertNotEqual(local, other)


class V3DraftSessionTests(SimpleTestCase):
    def test_draft_has_no_nested_side_effect_before_commit(self) -> None:
        session = SessionStore()
        session[ConversationSession.STATE_KEY] = Preferences(tags={'drink'}).to_dict()
        original = deepcopy(dict(session))
        draft = ConversationSession(session).draft()
        draft[ConversationSession.STATE_KEY]['tags'].append('cold')
        self.assertEqual(dict(session), original)

    def test_commit_only_changes_owned_dialog_fields(self) -> None:
        session = SessionStore()
        session.update({'cart': [{'id': 1}], '_auth_user_id': '7', 'chatbot_client_id': 'nonce'})
        state = ConversationSession(session)
        draft = state.draft()
        draft['cart'] = []
        draft['_auth_user_id'] = '999'
        ConversationSession(draft).set_focus(42)
        state.commit(draft)
        self.assertEqual(session['cart'], [{'id': 1}])
        self.assertEqual(session['_auth_user_id'], '7')
        self.assertEqual(session['chatbot_client_id'], 'nonce')
        self.assertEqual(state.get_focus(), 42)
        self.assertEqual(session[state.REVISION_KEY], 1)

    def test_legacy_id_lock_migrates_to_focus_and_candidates(self) -> None:
        session = SessionStore()
        session.update(
            {'recommendation_entity_ids': [4], 'recommendation_shown': [3, 4], 'gemini_calls': 7}
        )
        draft = ConversationSession(session).draft()
        migrated = ConversationSession(draft)
        self.assertEqual(migrated.get_focus(), 4)
        self.assertEqual(migrated.get_candidates(), [3, 4])
        self.assertNotIn(ConversationSession.SCHEMA_KEY, session)
        self.assertEqual(draft['gemini_calls'], 7)

    def test_unknown_schema_clears_only_dialog_not_auth_cart_or_usage(self) -> None:
        session = SessionStore()
        session.update(
            {
                'recommendation_schema_version': 999,
                'recommendation_entity_ids': [4],
                'recommendation_search': {'category': 'Minuman'},
                'gemini_calls': 7,
                '_auth_user_id': '7',
                'cart': [1],
                'chatbot_client_id': 'nonce',
            }
        )
        draft = ConversationSession(session).draft()
        self.assertIsNone(ConversationSession(draft).get_focus())
        self.assertNotIn(ConversationSession.SEARCH_KEY, draft)
        self.assertEqual(
            (
                draft['gemini_calls'],
                draft['cart'],
                draft['_auth_user_id'],
                draft['chatbot_client_id'],
            ),
            (7, [1], '7', 'nonce'),
        )

    def test_candidates_and_focus_are_bounded_ids_not_raw_chat(self) -> None:
        session = SessionStore()
        state = ConversationSession(session)
        state.set_candidates(list(range(1, 200)) + [True, 'raw', -1])
        self.assertEqual(len(state.get_candidates()), 100)
        self.assertTrue(all(type(value) is int and value > 0 for value in state.get_candidates()))

        with self.assertRaises(ValueError):
            state.set_focus(True)


class V3TransitionIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.drinks = Category.objects.create(name='Minuman')
        cold = MenuTag.objects.create(name='cold')
        drink = MenuTag.objects.create(name='drink')
        sweet = MenuTag.objects.create(name='sweet')
        self.jeruk = MenuItem.objects.create(
            name='Es Jeruk', price=Decimal(10000), category=self.drinks
        )
        self.kelapa = MenuItem.objects.create(
            name='Es Kelapa', price=Decimal(10000), category=self.drinks
        )
        self.jeruk.tags.add(cold, drink, sweet)
        self.kelapa.tags.add(cold, sweet)
        self.session = SessionStore()
        self.provider = OfflineGenerator()

    def reply(self, text: str) -> dict:
        return ChatbotService(self.session, gemini_client=self.provider).reply(text)

    def business_state(self) -> dict:
        return {
            key: deepcopy(self.session.get(key))
            for key in (
                ConversationSession.SEARCH_KEY,
                ConversationSession.FOCUS_KEY,
                ConversationSession.CANDIDATES_KEY,
                ConversationSession.REJECTED_KEY,
                'last_recommendations',
            )
        }

    def test_required_trio_preserves_search_pool_and_switches_only_focus(self) -> None:
        self.reply('aku mau minuman 10k')
        search = deepcopy(self.session[ConversationSession.SEARCH_KEY])
        candidates = list(self.session[ConversationSession.CANDIDATES_KEY])
        self.reply('yang es kelapa')
        result = self.reply('eh yang es jeruk aja deh')
        self.assertEqual([match.item.pk for match in result['recommendations']], [self.jeruk.pk])
        self.assertEqual(ConversationSession(self.session).get_focus(), self.jeruk.pk)
        self.assertEqual(self.session[ConversationSession.SEARCH_KEY], search)
        self.assertEqual(self.session[ConversationSession.CANDIDATES_KEY], candidates)
        self.assertEqual(self.provider.calls, 0)

    def test_named_negation_rejects_only_the_item_not_all_cold_drinks(self) -> None:
        self.reply('minuman 10k')
        result = self.reply('jangan es kelapa, pilih es jeruk')
        self.assertEqual([match.item.pk for match in result['recommendations']], [self.jeruk.pk])
        self.assertIn(self.kelapa.pk, ConversationSession(self.session).get_explicit_rejections())
        self.assertNotIn('cold', self.session[ConversationSession.SEARCH_KEY]['excluded_tags'])

    def test_alternatives_release_focus_without_implicit_rejection(self) -> None:
        self.reply('minuman 10k')
        self.reply('yang es kelapa')
        result = self.reply('yang lain')
        self.assertEqual([match.item.pk for match in result['recommendations']], [self.jeruk.pk])
        self.assertIsNone(ConversationSession(self.session).get_focus())
        self.assertFalse(ConversationSession(self.session).get_explicit_rejections())

    def test_all_shown_without_focus_explains_exhaustion_without_blacklisting(self) -> None:
        self.reply('minuman 10k')
        result = self.reply('yang lain')
        self.assertFalse(result['recommendations'])
        self.assertIn('belum ada menu lain', result['message'].lower())
        self.assertFalse(ConversationSession(self.session).get_explicit_rejections())

    def test_explicit_rejection_of_focus_keeps_other_candidates(self) -> None:
        self.reply('minuman 10k')
        self.reply('yang es kelapa')
        result = self.reply('aku tidak mau es kelapa')
        self.assertEqual([match.item.pk for match in result['recommendations']], [self.jeruk.pk])
        self.assertEqual(
            ConversationSession(self.session).get_explicit_rejections(), [self.kelapa.pk]
        )

    def test_ambiguous_target_preserves_business_state(self) -> None:
        self.reply('minuman 10k')
        self.reply('yang es kelapa')
        before = self.business_state()
        result = self.reply('aku mau es jeruk atau es kelapa')
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.business_state(), before)

    def test_invalid_target_and_budget_do_not_partially_commit_new_constraints(self) -> None:
        self.reply('minuman 10k')
        self.reply('yang es kelapa')
        before = self.business_state()
        result = self.reply('eh yang es jeruk maksimal 5000')
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.business_state(), before)

    def test_unavailable_switch_does_not_replace_valid_focus(self) -> None:
        self.reply('minuman 10k')
        self.reply('yang es kelapa')
        before = self.business_state()
        self.jeruk.is_available = False
        self.jeruk.save(update_fields=['is_available'])
        self.assertFalse(self.reply('ganti ke es jeruk')['recommendations'])
        self.assertEqual(self.business_state(), before)

    def test_new_catalog_names_and_filler_words_in_names_need_no_special_cases(self) -> None:
        for name in ('Teh Melati Baru', 'Es Aja'):
            item = MenuItem.objects.create(name=name, price=Decimal(9000), category=self.drinks)
            result = self.reply('eh yang ' + name + ' aja deh')
            self.assertEqual([match.item.pk for match in result['recommendations']], [item.pk])

    def test_position_reference_sets_focus_without_overwriting_pool(self) -> None:
        first = self.reply('minuman 10k')
        expected = first['recommendations'][1].item.pk
        pool = list(ConversationSession(self.session).get_candidates())
        self.reply('yang kedua')
        self.assertEqual(ConversationSession(self.session).get_focus(), expected)
        self.assertEqual(ConversationSession(self.session).get_candidates(), pool)

    def test_number_inside_verified_menu_name_is_not_a_new_budget(self) -> None:
        item = MenuItem.objects.create(
            name='Menu 10000', price=Decimal(25000), category=self.drinks
        )
        result = self.reply('eh yang menu 10000 aja deh')
        self.assertEqual([match.item.pk for match in result['recommendations']], [item.pk])
        self.assertIsNone(result['active_search']['max_price'])
        result = self.reply('yang menu 10000 maksimal 20 ribu')
        self.assertFalse(result['recommendations'])

    def test_exception_rolls_back_draft_business_changes(self) -> None:
        self.reply('minuman 10k')
        before = deepcopy(dict(self.session))
        bot = ChatbotService(self.session, gemini_client=self.provider)

        with patch.object(
            bot.recommender, 'rank', side_effect=RuntimeError('synthetic failure')
        ), self.assertRaises(RuntimeError):
            bot.reply('maksimal 5000')

        self.assertEqual(dict(self.session), before)

    def test_reset_preserves_usage_auth_cart_and_monotonic_revision(self) -> None:
        self.reply('minuman 10k')
        self.session.update(
            {'gemini_calls': 99, 'cart': [1], '_auth_user_id': '7', 'chatbot_client_id': 'nonce'}
        )
        old_revision = self.session[ConversationSession.REVISION_KEY]
        self.reply('mulai lagi')
        self.assertEqual(
            (self.session['gemini_calls'], self.session['cart'], self.session['_auth_user_id']),
            (99, [1], '7'),
        )
        self.assertIsNone(ConversationSession(self.session).get_focus())
        self.assertFalse(ConversationSession(self.session).get_candidates())
        self.assertGreater(self.session[ConversationSession.REVISION_KEY], old_revision)

    def test_session_stores_ids_not_correction_transcript(self) -> None:
        self.reply('minuman 10k')
        self.reply('eh yang es kelapa aja deh')
        self.assertNotIn('eh yang', json.dumps(dict(self.session)))
        self.assertEqual(
            self.session[ConversationSession.SCHEMA_KEY], ConversationSession.SCHEMA_VERSION
        )

    def test_failed_turn_keeps_provider_attempt_but_rolls_back_business_state(self) -> None:
        self.reply('minuman 10k')
        before = self.business_state()
        used = self.session.get('gemini_calls', 0)
        bot = ChatbotService(self.session, gemini_client=self.provider)
        valid = json.dumps(
            {
                'intent': 'RECOMMEND',
                'add_tags': ['chicken'],
                'remove_tags': [],
                'excluded_tags': [],
                'soft_excluded_tags': [],
                'moods': [],
                'clear_moods': False,
                'max_price': None,
                'prefer_affordable': None,
                'clear_max_price': False,
                'clear_prefer_affordable': False,
                'message_is_meaningful': True,
            }
        )

        with patch.object(self.provider, 'generate', return_value=valid) as generated, patch.object(
            bot.recommender, 'rank', side_effect=RuntimeError('synthetic failure')
        ), self.assertRaises(RuntimeError):
            bot.reply('menu yang cocok dengan suasana santai')

        self.assertEqual(self.business_state(), before)
        self.assertGreater(self.session['gemini_calls'], used)
        generated.assert_called_once()

    def test_http_trio_and_alternative_have_the_same_state_contract(self) -> None:
        with patch(
            'recommendation.services.gemini.GeminiClient.generate',
            side_effect=AssertionError('No provider for local names'),
        ):
            for text in ('minuman 10k', 'yang es kelapa', 'eh yang es jeruk aja deh'):
                response = self.client.post(
                    '/api/recommendation/chat/', {'message': text}, content_type='application/json'
                )
                self.assertEqual(response.status_code, 200)

            self.assertEqual(
                [item['id'] for item in response.json()['recommendations']], [self.jeruk.pk]
            )
            response = self.client.post(
                '/api/recommendation/chat/',
                {'message': 'yang lain'},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item['id'] for item in response.json()['recommendations']], [self.kelapa.pk]
        )
