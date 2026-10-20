"""Two-stage recommendation safety with isolated catalog and fake provider."""
from decimal import Decimal
import json

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase, override_settings
from menu.models import Category, MenuItem, MenuTag

from ..services.ai.semantic_reranker import SemanticReranker
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.recommendation import RecommendationService, SearchConstraints
from ..services.tag_extractor import Preferences


def ranked(*identifiers: int) -> str:
    return json.dumps({'ranked_candidates': [{'id': value, 'score': 1 - index / 100}
                                            for index, value in enumerate(identifiers)]})


class FakeRanker:
    def __init__(self, raw: str | None = None) -> None:
        self.raw = raw
        self.prompts: list[str] = []
        self.during_call = None

    def generate(self, prompt: str) -> str | None:
        self.prompts.append(prompt)
        if self.during_call is not None:
            self.during_call()
        return self.raw


class RankingValidationTests(SimpleTestCase):
    def test_partial_proposal_appends_omissions_in_baseline_order(self) -> None:
        self.assertEqual(SemanticReranker.validate({'ranked_candidates': [{'id': 3, 'score': .9}]}, [1, 2, 3]),
                         [3, 1, 2])

    def test_equal_scores_keep_local_order(self) -> None:
        data = {'ranked_candidates': [{'id': 3, 'score': .5}, {'id': 1, 'score': .5}]}
        self.assertEqual(SemanticReranker.validate(data, [1, 2, 3]), [1, 3, 2])

    def test_unknown_duplicate_and_boolean_ids_are_rejected(self) -> None:
        for rows in ([{'id': 99, 'score': 1}], [{'id': True, 'score': 1}],
                     [{'id': 1, 'score': .5}, {'id': 1, 'score': .4}]):
            self.assertIsNone(SemanticReranker.validate({'ranked_candidates': rows}, [1, 2]))

    def test_scores_must_be_finite_numbers_between_zero_and_one(self) -> None:
        for score in (True, '0.8', None, -1, 1.01, 10 ** 400, float('nan'), float('inf'), -float('inf')):
            with self.subTest(score=score):
                self.assertIsNone(SemanticReranker.validate({'ranked_candidates': [{'id': 1, 'score': score}]}, [1]))

    def test_claim_price_and_action_fields_are_rejected(self) -> None:
        for row in ({'id': 1, 'score': 1, 'price': 1}, {'id': 1, 'score': 1, 'allergen_free': True}):
            self.assertIsNone(SemanticReranker.validate({'ranked_candidates': [row]}, [1]))
        self.assertIsNone(SemanticReranker.validate({'ranked_candidates': [], 'action': 'checkout'}, [1]))

    def test_empty_or_wrong_shape_is_rejected(self) -> None:
        for value in (None, [], {'ranked_candidates': []}, {'ranked_candidates': '1'}, {'ids': [1]}):
            self.assertIsNone(SemanticReranker.validate(value, [1]))

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            json.loads('{"id":1,"id":2}', object_pairs_hook=SemanticReranker._unique_object)


@override_settings(GEMINI_MAX_CALLS_PER_SESSION=50, CHATBOT_SEMANTIC_RERANKING_ENABLED=True)
class SemanticRankingIntegrationTests(TestCase):
    def test_exhausted_session_is_diagnosed_without_spending_or_dispatch(self) -> None:
        self.session['gemini_calls'] = 50
        with self.assertLogs('recommendation.services.gemini', level='INFO') as logs:
            self.reply()
        self.assertTrue(any(json.loads(r.message).get('outcome') == 'session_limit_reached' for r in logs.records))
        self.assertEqual(self.session['gemini_calls'], 50)
        self.assertEqual(self.provider.prompts, [])

    def test_disabled_feature_and_insufficient_candidates_have_distinct_reasons(self) -> None:
        cases = [('enak buat nemenin nugas', False, 'feature_disabled'),
                 ('enak buat nemenin nugas maksimal 10 ribu', True, 'insufficient_candidates')]
        for text, enabled, reason in cases:
            self.session = SessionStore()
            with self.subTest(reason=reason), override_settings(CHATBOT_SEMANTIC_RERANKING_ENABLED=enabled):
                with self.assertLogs('recommendation.services.gemini', level='INFO') as logs:
                    self.reply(text)
                self.assertTrue(any(json.loads(r.message).get('outcome') == reason for r in logs.records))
                self.assertEqual(self.session.get('gemini_calls', 0), 0)
        self.assertEqual(self.provider.prompts, [])

    def test_turn_reservation_blocks_are_diagnosed_without_provider_dispatch(self) -> None:
        for reason in ('private_turn', 'turn_slot_used', 'provider_unavailable', 'context_protected'):
            with self.subTest(reason=reason):
                self.session = SessionStore()
                self.provider.available = reason != 'provider_unavailable'
                service = ChatbotService(self.session, gemini_client=self.provider)
                if reason == 'private_turn':
                    service._turn_generator.protect('private@example.invalid')
                elif reason == 'turn_slot_used':
                    self.assertTrue(service._turn_generator.reserve(lambda: True))
                elif reason == 'context_protected':
                    service._current_context = object()
                matches = service.recommender.rank(Preferences(), include_unscored=True)
                with self.assertLogs('recommendation.services.gemini', level='INFO') as logs:
                    service._semantic_order(matches, Preferences(), SearchConstraints())
                self.assertTrue(any(json.loads(r.message).get('outcome') == reason for r in logs.records))
                self.assertNotIn('private@example.invalid', '\n'.join(logs.output))
                self.assertEqual(self.session.get('gemini_calls', 0), 0)
        self.assertEqual(self.provider.prompts, [])

    def test_preflight_rejection_is_diagnosed_without_provider_dispatch(self) -> None:
        from unittest.mock import patch
        from menu.selection import MenuSelection
        with patch.object(MenuSelection, 'minimum_quote', return_value=None):
            with self.assertLogs('recommendation.services.gemini', level='INFO') as logs:
                self.reply()
        self.assertTrue(any(json.loads(r.message).get('outcome') == 'preflight_rejected' for r in logs.records))
        self.assertEqual(self.provider.prompts, [])

    def test_single_complete_json_or_unlabeled_fence_keeps_valid_ranking(self) -> None:
        for label in ('json', ''):
            with self.subTest(label=label):
                self.session = SessionStore()
                self.provider.raw = ' \n```' + label + '\r\n' + ranked(self.c.pk, self.a.pk) + '\r\n```\n '
                result = self.reply()
                self.assertEqual(self.ids(result), [self.c.pk, self.a.pk, self.b.pk])
                self.assertIn('bersifat subjektif', result['message'])
        self.assertEqual(len(self.provider.prompts), 2)

    def test_fence_does_not_allow_prose_extra_documents_or_other_languages(self) -> None:
        valid = ranked(self.c.pk)
        for raw in ('Here is JSON:\n```json\n' + valid + '\n```',
                    '```json\n' + valid + '\n```\nDone',
                    '```json\n' + valid + '\n```\n```json\n' + valid + '\n```',
                    '```python\n' + valid + '\n```',
                    '```json\n' + valid + '\n' + valid + '\n```',
                    '```json\n' + valid, '```json ' + valid + '```'):
            with self.subTest(raw=raw):
                self.session = SessionStore()
                self.provider.raw = raw
                self.assertEqual(self.ids(self.reply()), [self.a.pk, self.b.pk, self.c.pk])
        self.assertEqual(len(self.provider.prompts), 7)

    def test_fenced_json_retains_duplicate_key_and_candidate_validation(self) -> None:
        duplicate = '{"ranked_candidates":[],"ranked_candidates":[{"id":' + str(self.c.pk) + ',"score":1}]}'
        for raw in (duplicate, ranked(99999),
                    json.dumps({'ranked_candidates': [{'id': self.c.pk, 'score': True}]}),
                    json.dumps({'ranked_candidates': [{'id': self.c.pk, 'score': 1, 'price': 1}]})):
            with self.subTest(raw=raw):
                self.session = SessionStore()
                self.provider.raw = '```json\n' + raw + '\n```'
                self.assertEqual(self.ids(self.reply()), [self.a.pk, self.b.pk, self.c.pk])
        self.assertEqual(len(self.provider.prompts), 4)

    def test_fence_does_not_bypass_original_response_size_limit(self) -> None:
        self.provider.raw = '```json\n' + ranked(self.c.pk) + ' ' * SemanticReranker.MAX_RESPONSE_CHARS + '\n```'
        with self.assertLogs('recommendation.services.gemini', level='INFO') as captured:
            result = self.reply()
        self.assertEqual(self.ids(result), [self.a.pk, self.b.pk, self.c.pk])
        events = [json.loads(record.message) for record in captured.records]
        self.assertTrue(any(event['event'] == 'ranking_validation' and event['outcome'] == 'response_rejected'
                            for event in events))

    def test_invalid_json_has_safe_ranking_diagnostic(self) -> None:
        self.provider.raw = '```json\nPRIVATE_RESPONSE_CANARY\n```'
        with self.assertLogs('recommendation.services.gemini', level='INFO') as captured:
            result = self.reply()
        events = [json.loads(record.message) for record in captured.records]
        self.assertTrue(any(event['event'] == 'ranking_validation' and event['outcome'] == 'invalid_json'
                            for event in events))
        self.assertNotIn('PRIVATE_RESPONSE_CANARY', '\n'.join(captured.output))
        self.assertNotIn('nemenin nugas', '\n'.join(captured.output))
        self.assertIn('belum bisa kupastikan', result['message'])

    def test_wrong_schema_has_safe_ranking_diagnostic(self) -> None:
        self.provider.raw = json.dumps({'ranked_candidates': [{'id': 99999, 'score': 0.5}]})
        with self.assertLogs('recommendation.services.gemini', level='INFO') as captured:
            self.reply()
        events = [json.loads(record.message) for record in captured.records]
        self.assertTrue(any(event['event'] == 'ranking_validation' and event['outcome'] == 'invalid_schema'
                            for event in events))

    def test_valid_ranking_is_logged_accepted_after_final_checks(self) -> None:
        self.provider.raw = ranked(self.c.pk, self.a.pk, self.b.pk)
        with self.assertLogs('recommendation.services.gemini', level='INFO') as captured:
            result = self.reply()
        events = [json.loads(record.message) for record in captured.records]
        self.assertTrue(any(event['event'] == 'ranking_validation' and event['outcome'] == 'accepted'
                            for event in events))
        self.assertEqual(self.ids(result)[0], self.c.pk)

    def test_catalog_change_is_not_logged_as_accepted_ranking(self) -> None:
        self.provider.raw = ranked(self.c.pk, self.a.pk, self.b.pk)
        self.provider.during_call = lambda: MenuItem.objects.filter(pk=self.c.pk).update(is_available=False)
        with self.assertLogs('recommendation.services.gemini', level='INFO') as captured:
            result = self.reply()
        events = [json.loads(record.message) for record in captured.records]
        outcomes = [event['outcome'] for event in events if event['event'] == 'ranking_validation']
        self.assertIn('catalog_changed', outcomes)
        self.assertNotIn('accepted', outcomes)
        self.assertNotIn(self.c.pk, self.ids(result))

    def setUp(self) -> None:
        self.category = Category.objects.create(name='Makanan')
        self.a = MenuItem.objects.create(name='Menu A', category=self.category, price=Decimal('10000'))
        self.b = MenuItem.objects.create(name='Menu B', category=self.category, price=Decimal('15000'))
        self.c = MenuItem.objects.create(name='Menu C', category=self.category, price=Decimal('20000'))
        self.rich = MenuTag.objects.create(name='rich')
        self.filling = MenuTag.objects.create(name='filling')
        self.b.tags.add(self.filling)
        self.c.tags.add(self.rich)
        self.provider = FakeRanker()
        self.session = SessionStore()

    def reply(self, text: str = 'enak buat nemenin nugas') -> dict:
        return ChatbotService(self.session, gemini_client=self.provider).reply(text)

    @staticmethod
    def ids(response: dict) -> list[int]:
        return [match.item.pk for match in response['recommendations']]

    def sent_ids(self) -> list[int]:
        data = json.loads(self.provider.prompts[-1].split('Data: ', 1)[1])
        return [row['id'] for row in data['candidates']]

    def test_valid_semantic_order_can_differ_from_local_baseline(self) -> None:
        self.provider.raw = ranked(self.c.pk, self.a.pk, self.b.pk)
        result = self.reply()
        self.assertEqual(self.ids(result), [self.c.pk, self.a.pk, self.b.pk])
        self.assertEqual(len(self.provider.prompts), 1)
        self.assertIn('bersifat subjektif', result['message'])
        self.assertEqual([match.score for match in result['recommendations']], [0, 0, 0])

    def test_subjective_light_and_filling_are_not_mandatory_tags(self) -> None:
        self.provider.raw = ranked(self.a.pk, self.b.pk)
        result = self.reply('yang ringan tapi tetap mengenyangkan maksimal 25 ribu')
        self.assertEqual(set(self.ids(result)), {self.a.pk, self.b.pk, self.c.pk})
        self.assertNotIn('light', result['active_search']['required_tags'])
        self.assertNotIn('filling', result['active_search']['required_tags'])
        self.assertEqual(self.ids(result)[0], self.a.pk)

    def test_price_range_and_hard_ban_filter_before_provider(self) -> None:
        self.provider.raw = ranked(self.b.pk, self.a.pk)
        result = self.reply('enak buat nemenin nugas jangan berlemak budget 10-18 ribu')
        self.assertEqual(set(self.sent_ids()), {self.a.pk, self.b.pk})
        self.assertEqual(self.ids(result), [self.b.pk, self.a.pk])
        self.assertIn('rich', result['active_search']['excluded_tags'])

    def test_inactive_unavailable_and_inactive_category_never_reach_provider(self) -> None:
        bad_category = Category.objects.create(name='Arsip', is_active=False)
        hidden = MenuItem.objects.create(name='Hidden', category=bad_category, price=Decimal('1'))
        inactive = MenuItem.objects.create(name='Inactive', category=self.category, price=Decimal('1'), is_active=False)
        unavailable = MenuItem.objects.create(name='Unavailable', category=self.category, price=Decimal('1'), is_available=False)
        self.provider.raw = ranked(self.b.pk)
        result = self.reply()
        self.assertTrue(set(self.sent_ids()).isdisjoint({hidden.pk, inactive.pk, unavailable.pk}))
        self.assertTrue(set(self.ids(result)).isdisjoint({hidden.pk, inactive.pk, unavailable.pk}))

    def test_fabricated_or_filtered_id_rejects_whole_proposal(self) -> None:
        self.provider.raw = ranked(self.c.pk, self.b.pk)
        result = self.reply('enak buat nemenin nugas maksimal 15 ribu')
        self.assertEqual(self.ids(result), [self.a.pk, self.b.pk])
        self.assertNotIn(self.c.pk, self.sent_ids())
        self.assertIn('belum bisa kupastikan', result['message'])

    def test_invalid_json_and_unsupported_claims_use_local_fallback(self) -> None:
        for raw in ('{', ranked(99999), '{"ranked_candidates":[],"nutrition":"healthy"}'):
            self.provider.raw = raw
            self.assertEqual(self.ids(self.reply()), [self.a.pk, self.b.pk, self.c.pk])

    def test_duplicate_json_output_uses_local_fallback(self) -> None:
        self.provider.raw = '{"ranked_candidates":[{"id":' + str(self.b.pk) + ',"id":' + str(self.a.pk) + ',"score":1}]}'
        self.assertEqual(self.ids(self.reply()), [self.a.pk, self.b.pk, self.c.pk])

    def test_timeout_uses_valid_local_results(self) -> None:
        def timeout() -> None:
            raise TimeoutError('synthetic only')
        self.provider.during_call = timeout
        result = self.reply()
        self.assertEqual(self.ids(result), [self.a.pk, self.b.pk, self.c.pk])
        self.assertIn('belum bisa kupastikan', result['message'])

    def test_feature_flag_disables_only_optional_ranking(self) -> None:
        self.provider.raw = ranked(self.c.pk)
        with override_settings(CHATBOT_SEMANTIC_RERANKING_ENABLED=False):
            result = self.reply()
        self.assertEqual(self.ids(result), [self.a.pk, self.b.pk, self.c.pk])
        self.assertEqual(self.provider.prompts, [])

    def test_quota_exhaustion_keeps_local_fallback(self) -> None:
        self.session['gemini_calls'] = 999
        self.assertEqual(self.ids(self.reply()), [self.a.pk, self.b.pk, self.c.pk])
        self.assertEqual(self.provider.prompts, [])

    def test_single_or_empty_candidate_set_does_not_spend_provider_call(self) -> None:
        self.assertEqual(self.ids(self.reply('enak buat nemenin nugas maksimal 10 ribu')), [self.a.pk])
        self.assertEqual(self.ids(self.reply('enak buat nemenin nugas maksimal 1 rupiah')), [])
        self.assertEqual(self.provider.prompts, [])

    def test_objective_request_does_not_rerank(self) -> None:
        self.provider.raw = ranked(self.c.pk)
        result = self.reply('makanan maksimal 20 ribu')
        self.assertEqual(self.ids(result), [self.a.pk, self.b.pk, self.c.pk])
        self.assertEqual(self.provider.prompts, [])

    def test_price_change_during_call_rejects_order_and_refilters(self) -> None:
        self.provider.raw = ranked(self.a.pk, self.b.pk)
        self.provider.during_call = lambda: MenuItem.objects.filter(pk=self.a.pk).update(price=Decimal('30000'))
        result = self.reply('enak buat nemenin nugas maksimal 20 ribu')
        self.assertEqual(self.ids(result), [self.b.pk, self.c.pk])
        self.assertNotIn(self.a.pk, self.session[ConversationSession.CANDIDATES_KEY])

    def test_in_range_price_change_returns_fresh_price_and_local_order(self) -> None:
        self.provider.raw = ranked(self.a.pk, self.c.pk, self.b.pk)
        self.provider.during_call = lambda: MenuItem.objects.filter(pk=self.a.pk).update(price=Decimal('16000'))
        result = self.reply('enak buat nemenin nugas maksimal 20 ribu')
        self.assertEqual(self.ids(result), [self.b.pk, self.a.pk, self.c.pk])
        self.assertEqual(result['recommendations'][1].item.price, Decimal('16000'))

    def test_unavailability_during_provider_call_is_revalidated(self) -> None:
        self.provider.raw = ranked(self.b.pk)
        self.provider.during_call = lambda: MenuItem.objects.filter(pk=self.b.pk).update(is_available=False)
        self.assertNotIn(self.b.pk, self.ids(self.reply()))

    def test_tag_change_during_call_is_revalidated(self) -> None:
        self.provider.raw = ranked(self.a.pk, self.b.pk)
        self.provider.during_call = lambda: self.a.tags.add(self.rich)
        result = self.reply('enak buat nemenin nugas jangan berlemak')
        self.assertEqual(self.ids(result), [self.b.pk])

    def test_candidate_payload_is_bounded_and_excludes_session_secrets(self) -> None:
        for number in range(10):
            MenuItem.objects.create(name=f'Extra {number}', category=self.category, price=Decimal('11000'))
        self.session.update({'_auth_user_id': 'private-user', 'cart': {'secret': 'cart-private'},
                             'chatbot_client_id': 'nonce-private'})
        self.provider.raw = ranked(self.a.pk)
        self.reply()
        self.assertEqual(len(self.sent_ids()), 8)
        self.assertLessEqual(len(self.provider.prompts[0].encode('utf-8')), SemanticReranker.MAX_PROMPT_BYTES)
        for secret in ('private-user', 'cart-private', 'nonce-private'):
            self.assertNotIn(secret, self.provider.prompts[0])
        self.assertFalse(any('nugas' in str(value) for key, value in self.session.items() if key != 'cart'))

    def test_remaining_candidates_keep_order_after_bounded_prefix(self) -> None:
        for number in range(9):
            MenuItem.objects.create(name=f'Extra {number}', category=self.category, price=Decimal('11000'))
        baseline = RecommendationService().rank(Preferences(), limit=100, constraints=SearchConstraints(), include_unscored=True)
        provider = FakeRanker(ranked(baseline[7].item.pk))
        result = SemanticReranker(provider).rerank(baseline, 'nemenin nugas')
        self.assertIsNotNone(result)
        self.assertEqual([match.item.pk for match in result[8:]], [match.item.pk for match in baseline[8:]])

    def test_allergy_request_does_not_make_safety_claim_or_call_ai(self) -> None:
        result = self.reply('aku alergi udang, enak buat nemenin nugas')
        self.assertEqual(self.ids(result), [])
        self.assertIn('staf', result['message'])
        self.assertEqual(self.provider.prompts, [])

    def test_explicit_target_over_budget_stays_local_and_cannot_be_reranked(self) -> None:
        self.reply('maksimal 10 ribu')
        result = self.reply('aku mau Menu C')
        self.assertEqual(self.ids(result), [])
        self.assertEqual(self.provider.prompts, [])
        self.assertEqual(result['active_search']['budget']['maximum'], '10000')

    def test_soft_wishes_affect_local_baseline_when_provider_unavailable(self) -> None:
        with override_settings(CHATBOT_SEMANTIC_RERANKING_ENABLED=False):
            result = self.reply('yang ringan tapi cukup mengenyangkan')
        self.assertEqual(self.ids(result)[0], self.b.pk)
        self.assertEqual(set(self.ids(result)), {self.a.pk, self.b.pk, self.c.pk})

    def test_reused_service_does_not_reuse_previous_subjective_query(self) -> None:
        bot = ChatbotService(self.session, gemini_client=self.provider)
        bot.reply('enak buat nemenin nugas')
        calls = len(self.provider.prompts)
        bot.reply('makanan maksimal 20 ribu')
        self.assertEqual(len(self.provider.prompts), calls)
        self.assertIsNone(bot._semantic_query)

    def test_partial_ranking_does_not_replace_local_score_or_explanation(self) -> None:
        self.provider.raw = ranked(self.c.pk)
        result = self.reply()
        self.assertEqual(self.ids(result), [self.c.pk, self.a.pk, self.b.pk])
        self.assertEqual(result['recommendations'][0].score, 0)
        self.assertNotIn('score', result['message'])

    def test_oversized_catalog_payload_skips_provider_and_falls_back(self) -> None:
        tags = [MenuTag.objects.create(name=f't{number}' + 'x' * 45) for number in range(20)]
        for number in range(8):
            item = MenuItem.objects.create(name=f'Unicode {number}', description='😀' * 240,
                                           category=self.category, price=Decimal('9000'))
            item.tags.add(*tags)
        result = self.reply()
        self.assertTrue(result['recommendations'])
        self.assertEqual(self.provider.prompts, [])
