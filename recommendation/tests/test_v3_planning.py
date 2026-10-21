"""Verified response plans, local variants and optional grounded expression."""

from copy import deepcopy
from decimal import Decimal
import json

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import TestCase, override_settings
from menu.models import Category, MenuItem, MenuTag

from ..services.ai.explanations import RecommendationExplanationService
from ..services.budget import BudgetConstraint
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.recommendation import RecommendationService, SearchConstraints
from ..services.response_composer import LocalResponseComposer
from ..services.response_plan import ResponsePlan
from ..services.tag_extractor import Preferences


class FakeExpression:
    def __init__(self) -> None:
        self.ids: list[int] = []
        self.intro: object = 'Ini beberapa pilihan sesuai seleramu.'
        self.raw: str | None = None
        self.calls: list[str] = []
        self.on_wording = None
        self.on_ranking = None

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)

        if prompt.startswith('Rank the supplied'):
            if self.on_ranking is not None:
                self.on_ranking()

            return json.dumps(
                {
                    'ranked_candidates': [
                        {'id': identifier, 'score': 1 - index / 10}
                        for index, identifier in enumerate(self.ids)
                    ]
                }
            )

        if self.on_wording is not None:
            self.on_wording()

        if self.raw is not None:
            return self.raw

        return json.dumps({'intro': self.intro, 'explanations': []})


class ResponsePlanningTests(TestCase):
    def setUp(self) -> None:
        self.category = Category.objects.create(name='Minuman')
        self.a = MenuItem.objects.create(
            name='Es Alpha',
            category=self.category,
            price=Decimal('10000'),
            description='DESCRIPTION_PRIVATE',
        )
        self.b = MenuItem.objects.create(
            name='Es Beta', category=self.category, price=Decimal('15000')
        )
        tag = MenuTag.objects.create(name='drink')
        self.a.tags.add(tag)
        self.b.tags.add(tag)
        self.preferences = Preferences(tags={'drink'})
        self.constraints = SearchConstraints(
            required_tags=frozenset({'drink'}),
            category='Minuman',
            budget=BudgetConstraint(maximum=Decimal('20000')),
        )
        self.matches = RecommendationService().rank(self.preferences, constraints=self.constraints)
        self.session = SessionStore()
        self.provider = FakeExpression()
        self.provider.ids = [self.b.pk, self.a.pk]

    def plan(self, **kwargs: object) -> ResponsePlan:
        return ResponsePlan(
            'recommendation', self.matches, self.preferences, constraints=self.constraints, **kwargs
        )

    def test_plan_separates_facts_intent_style_and_claims(self) -> None:
        plan = self.plan(intent='RECOMMEND', tone='concise')
        data = plan.to_dict()
        self.assertEqual(data['intent'], 'RECOMMEND')
        self.assertEqual(data['tone'], 'concise')
        self.assertEqual(plan.selected_menu_ids, (self.a.pk, self.b.pk))
        self.assertTrue(all(fact['available'] for fact in plan.facts))
        self.assertNotIn('allergen_free', plan.allowed_claims)
        self.assertNotIn('DESCRIPTION_PRIVATE', json.dumps(data))

    def test_plan_facts_constraints_and_quick_replies_are_copied(self) -> None:
        quick = [{'label': 'Cari lagi', 'value': 'yang lain', 'action': 'more'}]
        plan = self.plan(quick_replies=quick)
        original = deepcopy(plan.to_dict())
        quick[0]['value'] = 'malicious'
        data = plan.to_dict()
        data['items'][0]['price'] = '1'
        data['constraints']['budget']['maximum'] = '1'
        data['quick_replies'].clear()
        self.assertEqual(plan.to_dict(), original)

    def test_unsupported_purpose_and_tone_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.plan(tone='invented')

        with self.assertRaises(ValueError):
            ResponsePlan('checkout', [], Preferences())

    def test_clarification_is_required_literal_text_and_never_ai(self) -> None:
        plan = ResponsePlan(
            'clarification',
            self.matches,
            self.preferences,
            required_clarification='Menu yang mana?',
        )
        self.assertEqual(LocalResponseComposer(self.session).compose(plan), 'Menu yang mana?')
        self.assertEqual(
            RecommendationExplanationService(self.provider).from_plan(
                plan, self.matches, self.preferences
            ),
            (None, {}),
        )
        self.assertEqual(self.provider.calls, [])

    def test_local_openings_vary_without_repeating_category(self) -> None:
        composer = LocalResponseComposer(self.session)
        messages = [composer.compose(self.plan()) for _ in range(4)]
        self.assertEqual(len(set(message.split('\n')[0] for message in messages)), 4)

        for message in messages:
            self.assertEqual(message.casefold().count('minuman'), 1)
            self.assertIn('Rp20.000', message)
            self.assertNotIn('Rp20.000,00', message)
            self.assertLess(len(message), 600)

    def test_local_selection_and_switching_include_exact_current_name(self) -> None:
        composer = LocalResponseComposer(self.session)

        for switching in (True, False):
            values = [composer.selection('Nama Baru', switching=switching) for _ in range(3)]
            self.assertEqual(len(set(values)), 3)
            self.assertTrue(all('Nama Baru' in value for value in values))

    def test_plan_rejects_mismatched_expression_ids_before_provider(self) -> None:
        self.assertEqual(
            RecommendationExplanationService(self.provider).from_plan(
                self.plan(), [], self.preferences
            ),
            (None, {}),
        )
        self.assertEqual(self.provider.calls, [])

    def test_live_chat_constructs_plan_without_exposing_it_on_wire(self) -> None:
        bot = ChatbotService(self.session, gemini_client=self.provider)
        result = bot.reply('minuman 20k')
        self.assertEqual(bot.response_plan.purpose, 'budget')
        self.assertEqual(
            bot.response_plan.selected_menu_ids,
            tuple(match.item.pk for match in result['recommendations']),
        )
        self.assertEqual(bot.response_plan.quick_replies, result['quick_replies'])
        self.assertNotIn('response_plan', result)
        self.assertNotIn('allowed_claims', result)

    def test_switching_plan_tracks_selected_identity(self) -> None:
        bot = ChatbotService(self.session, gemini_client=self.provider)
        bot.reply('yang es alpha')
        result = bot.reply('ganti ke es beta')
        self.assertEqual(bot.response_plan.purpose, 'switching')
        self.assertEqual(bot.response_plan.selected_menu_ids, (self.b.pk,))
        self.assertIn('Es Beta', result['message'])
        self.assertEqual(self.provider.calls, [])

    def test_local_greetings_nonfood_and_clarification_have_plans(self) -> None:
        for message, purpose in [
            ('halo', 'greeting'),
            ('aku mau motor', 'nonfood'),
            ('yang pertama', 'clarification'),
        ]:
            bot = ChatbotService(SessionStore(), gemini_client=self.provider)
            bot.reply(message)
            self.assertEqual(bot.response_plan.purpose, purpose)

        self.assertEqual(self.provider.calls, [])

    def test_empathy_tone_does_not_export_emotion_or_raw_message(self) -> None:
        bot = ChatbotService(self.session, gemini_client=self.provider)
        bot.reply('aku sedih, mau es alpha')
        data = bot.response_plan.to_dict()
        self.assertEqual(data['tone'], 'empathetic')
        self.assertNotIn('sedih', json.dumps(data))
        self.assertEqual(self.provider.calls, [])

    def test_unscored_fallback_does_not_assert_subjective_suitability(self) -> None:
        matches = RecommendationService().rank(
            Preferences(), constraints=SearchConstraints(), include_unscored=True
        )
        text = RecommendationExplanationService.fallback(matches[0])
        self.assertIn('katalog', text)
        self.assertNotIn('sesuai dengan preferensimu', text)


@override_settings(
    CHATBOT_AI_WORDING_ENABLED=True,
    CHATBOT_SEMANTIC_RERANKING_ENABLED=True,
    GEMINI_MAX_CALLS_PER_SESSION=50,
)
class OptionalExpressionTests(TestCase):
    setUp = ResponsePlanningTests.setUp
    plan = ResponsePlanningTests.plan

    def reply(self, message: str = 'enak buat nemenin nugas maksimal 20k') -> dict:
        return ChatbotService(self.session, gemini_client=self.provider).reply(message)

    @staticmethod
    def ids(result: dict) -> list[int]:
        return [match.item.pk for match in result['recommendations']]

    def expression(self) -> tuple:
        # Keep unit coverage of the dormant validator separate from reply routing.
        return RecommendationExplanationService(self.provider).from_plan(
            self.plan(), self.matches, self.preferences
        )

    def test_wording_cannot_spend_a_second_call_after_ranking(self) -> None:
        result = self.reply()
        self.assertEqual(len(self.provider.calls), 1)
        self.assertFalse(result['message'].startswith(self.provider.intro))
        self.assertIn('Rp20.000', result['message'])
        self.assertNotIn('Rp20.000,00', result['message'])
        self.assertIn('varian', result['message'])
        self.assertEqual(self.ids(result), [self.b.pk, self.a.pk])

    def test_wording_is_off_by_default_and_does_not_change_rank(self) -> None:
        with override_settings(CHATBOT_AI_WORDING_ENABLED=False):
            result = self.reply()

        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.ids(result), [self.b.pk, self.a.pk])

    def test_objective_requests_never_spend_wording_calls_even_when_enabled(self) -> None:
        self.reply('minuman 20k')
        self.reply('yang es alpha')
        self.assertEqual(self.provider.calls, [])

    def test_invalid_wording_preserves_selected_ids_constraints_and_cards(self) -> None:
        for intro in (
            'Harga Rp1',
            'Stok tersedia',
            'Siap dalam dua menit',
            'Menu aman untuk alergi',
            'Pembayaran berhasil',
            'Pesanan sudah dikirim',
            'Sushi Istimewa cocok',
            '<b>Ini pilihan</b>',
            'Lihat https://example.invalid',
            'Ini pilihan\x00',
            'Ini pilihan\u202e',
            'Ini pilihan\ud800',
        ):
            with self.subTest(intro=repr(intro)):
                self.provider.intro = intro
                self.assertEqual(self.expression(), (None, {}))
                result = self.reply()
                self.assertEqual(self.ids(result), [self.b.pk, self.a.pk])
                self.assertNotIn(intro, result['message'])
                self.assertEqual(result['active_search']['budget']['maximum'], '20000')
                self.assertEqual(result['recommendations'][0].item.price, Decimal('15000'))

    def test_raw_invalid_json_and_duplicate_keys_are_never_displayed(self) -> None:
        for raw in (
            '{RAW_CANARY',
            '{"intro":"RAW_CANARY","intro":"Ini pilihan","explanations":[]}',
            '{"intro":"Ini pilihan","explanations":[],"action":"checkout"}',
        ):
            self.provider.raw = raw
            self.assertEqual(self.expression(), (None, {}))
            result = self.reply()
            self.assertEqual(self.ids(result), [self.b.pk, self.a.pk])
            self.assertNotIn('RAW_CANARY', result['message'])

    def test_provider_timeout_uses_local_expression_with_same_selection(self) -> None:
        def timeout() -> None:
            raise TimeoutError('PRIVATE_PROVIDER_ERROR')

        self.provider.on_wording = timeout
        self.assertEqual(self.expression(), (None, {}))
        result = self.reply()
        self.assertEqual(self.ids(result), [self.b.pk, self.a.pk])
        self.assertNotIn('PRIVATE_PROVIDER_ERROR', result['message'])

    def test_wording_quota_refusal_keeps_semantic_order(self) -> None:
        with override_settings(GEMINI_MAX_CALLS_PER_SESSION=1):
            result = self.reply()

        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.ids(result), [self.b.pk, self.a.pk])

    def test_failed_semantic_ranking_does_not_trigger_wording(self) -> None:
        self.provider.ids = [99999]
        result = self.reply()
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.ids(result), [self.a.pk, self.b.pk])

    def test_expression_component_payload_excludes_raw_chat_history_and_description(self) -> None:
        self.session.update(
            {
                'cart': {'secret': 'CART_PRIVATE'},
                '_auth_user_id': 'AUTH_PRIVATE',
                'chatbot_client_id': 'NONCE_PRIVATE',
            }
        )
        self.expression()
        prompt = self.provider.calls[-1]

        for value in (
            'CART_PRIVATE',
            'AUTH_PRIVATE',
            'NONCE_PRIVATE',
            'DESCRIPTION_PRIVATE',
            'nugas',
        ):
            self.assertNotIn(value, prompt)

        self.assertIn('selected_menu_ids', prompt)
        self.assertIn('allowed_claims', prompt)

    def test_replies_use_varied_local_opening_after_ranking(self) -> None:
        first = self.reply()
        second = self.reply()
        self.assertFalse(first['message'].startswith(self.provider.intro))
        self.assertFalse(second['message'].startswith(self.provider.intro))
        self.assertNotEqual(first['message'].split('\n')[0], second['message'].split('\n')[0])
        self.assertEqual(len(self.provider.calls), 2)
        self.assertEqual(self.ids(first), self.ids(second))

    def test_catalog_change_during_only_call_refilters_before_local_wording(self) -> None:
        self.provider.on_ranking = lambda: MenuItem.objects.filter(pk=self.b.pk).update(
            price=Decimal('25000')
        )
        result = self.reply()
        self.assertEqual(self.ids(result), [self.a.pk])
        self.assertFalse(result['message'].startswith(self.provider.intro))
        self.assertEqual(self.session['last_recommendations'], [self.a.pk])

    def test_current_price_is_used_after_in_range_change(self) -> None:
        self.provider.on_ranking = lambda: MenuItem.objects.filter(pk=self.b.pk).update(
            price=Decimal('16000')
        )
        result = self.reply()
        self.assertEqual(self.ids(result), [self.a.pk, self.b.pk])
        self.assertEqual(result['recommendations'][1].item.price, Decimal('16000'))
        self.assertFalse(result['message'].startswith(self.provider.intro))

    def test_required_clarification_and_allergy_never_use_wording(self) -> None:
        self.reply('yang pertama')
        result = self.reply('aku alergi udang')
        self.assertEqual(self.ids(result), [])
        self.assertIn('staf', result['message'])
        self.assertEqual(self.provider.calls, [])

    def test_unknown_id_explanation_rejects_generated_intro_as_well(self) -> None:
        self.provider.raw = json.dumps(
            {'intro': self.provider.intro, 'explanations': [{'id': 99999, 'text': 'Menu palsu'}]}
        )
        self.assertEqual(self.expression(), (None, {}))
        result = self.reply()
        self.assertFalse(result['message'].startswith(self.provider.intro))
        self.assertEqual(self.ids(result), [self.b.pk, self.a.pk])

    def test_generated_history_contains_only_numeric_fingerprints(self) -> None:
        self.reply()
        history = self.session[LocalResponseComposer.HISTORY_KEY]
        self.assertTrue(all(type(value) is int for values in history.values() for value in values))
        self.assertNotIn(self.provider.intro, json.dumps(dict(self.session)))
