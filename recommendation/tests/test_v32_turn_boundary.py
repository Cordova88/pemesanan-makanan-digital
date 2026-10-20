"""H3 fake-provider integration: one attempt, privacy, explicit v3 boundary."""

from decimal import Decimal
import json

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import TestCase, override_settings
from menu.models import Category, MenuItem, MenuTag

from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession


class PacketProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.raw: str | None = None
        self.during_call = None

    def generate(self, prompt: str) -> str | None:
        self.calls.append(prompt)

        if self.during_call is not None:
            self.during_call()

        if self.raw is not None:
            return self.raw

        if prompt.startswith('Rank the supplied'):
            return json.dumps({'ranked_candidates': []})

        packet = json.loads(prompt.split('Data: ', 1)[1])

        return json.dumps(
            dict(
                proposal_version=3,
                intent='RECOMMEND',
                context_action=packet['context_action'],
                constraint_scope=packet['constraint_scope'],
                context_ref=packet['context_ref'],
                preference_operations=[
                    {'action': 'ADD', 'tag_ids': ['drink'], 'remove_tag_ids': []}
                ],
                entity_roles=[],
                numeric_bindings=[],
                clarification_key=None,
            )
        )


@override_settings(
    CHATBOT_PROPOSAL_V3_ENABLED=True,
    CHATBOT_AI_WORDING_ENABLED=True,
    GEMINI_MAX_CALLS_PER_SESSION=50,
)
class TurnBoundaryTests(TestCase):
    def setUp(self) -> None:
        category = Category.objects.create(name='Minuman')
        tag = MenuTag.objects.create(name='drink')
        self.a = MenuItem.objects.create(
            name='Es Alpha',
            price=Decimal('10000'),
            category=category,
            description='DESCRIPTION_PRIVATE email@example.invalid',
        )
        self.b = MenuItem.objects.create(name='Es Beta', price=Decimal('15000'), category=category)
        self.a.tags.add(tag)
        self.b.tags.add(tag)
        self.session = SessionStore()
        self.provider = PacketProvider()
        self.service = ChatbotService(self.session, gemini_client=self.provider)

    def test_v3_packet_filters_locally_and_preserves_saved_price(self) -> None:
        self.service.reply('maksimal 10k')
        result = self.service.reply('menu yang cocok dengan suasana santai')
        self.assertEqual([m.item.pk for m in result['recommendations']], [self.a.pk])
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(result['active_search']['budget']['maximum'], '10000')
        packet = json.loads(self.provider.calls[0].split('Data: ', 1)[1])
        self.assertEqual(packet['proposal_version'], 3)

        for key in ('history', 'moods', 'last_question', 'active_search', 'max_price'):
            self.assertNotIn(key, packet)

    def test_invalid_v3_never_retries_legacy_or_changes_preferences(self) -> None:
        self.provider.raw = '{"proposal_version": 2}'
        result = self.service.reply('menu yang cocok dengan suasana santai')
        self.assertEqual(result['recommendations'], [])
        self.assertEqual(len(self.provider.calls), 1)
        self.assertNotIn(
            'drink', self.session.get(ConversationSession.STATE_KEY, {}).get('tags', [])
        )

    def test_provider_exception_is_one_attempt_with_local_clarification(self) -> None:
        def fail() -> None:
            raise TimeoutError('PRIVATE_TIMEOUT')

        self.provider.during_call = fail
        result = self.service.reply('menu yang cocok dengan suasana santai')
        self.assertEqual(result['recommendations'], [])
        self.assertEqual(len(self.provider.calls), 1)
        self.assertNotIn('PRIVATE_TIMEOUT', result['message'])
        self.assertEqual(self.session['gemini_calls'], 1)

    def test_quota_refusal_makes_no_call(self) -> None:
        self.session['gemini_calls'] = 50
        self.service.reply('menu yang cocok dengan suasana santai')
        self.assertEqual(self.provider.calls, [])

    def test_local_actions_make_no_call(self) -> None:
        for text in (
            'halo',
            'minuman 10k',
            'yang es alpha',
            'yang pertama',
            'mulai lagi',
            'budget 20k',
            'maksimal 5k minimal 10k',
            'aku alergi udang',
        ):
            self.service.reply(text)

        self.assertEqual(self.provider.calls, [])

    def test_one_slot_is_shared_with_wording_and_resets_next_turn(self) -> None:
        self.provider.raw = json.dumps({'ranked_candidates': [{'id': self.b.pk, 'score': 1}]})

        for expected in (1, 2):
            result = self.service.reply('enak buat nemenin nugas maksimal 20k')
            self.assertEqual(len(self.provider.calls), expected)
            self.assertEqual(result['recommendations'][0].item.pk, self.b.pk)

        self.assertEqual(self.session['gemini_calls'], 2)

    def test_private_session_and_catalog_description_are_not_in_ranking_packet(self) -> None:
        self.session.update(
            {
                'cart': {'note': 'CART_PRIVATE'},
                '_auth_user_id': 'AUTH_PRIVATE',
                'last_question': 'QUESTION_PRIVATE',
            }
        )
        self.service.reply('enak buat nemenin nugas maksimal 20k')
        self.assertEqual(len(self.provider.calls), 1)

        for value in (
            'CART_PRIVATE',
            'AUTH_PRIVATE',
            'QUESTION_PRIVATE',
            'DESCRIPTION_PRIVATE',
            'email@example.invalid',
            'maksimal',
            '20k',
        ):
            self.assertNotIn(value, self.provider.calls[0])

        packet = json.loads(self.provider.calls[0].split('Data: ', 1)[1])
        self.assertTrue(all(set(row) == {'id', 'tags'} for row in packet['candidates']))

    def test_sensitive_residual_is_kept_local(self) -> None:
        for text in (
            'menu untuk email saya me@example.invalid',
            'menu yang cocok nomor telepon 081234567890',
            'menu yang cocok alamat jalan merdeka 12',
            'menu yang cocok api_key SECRET_CANARY',
            'enak buat nemenin nugas saya depresi',
        ):
            with self.subTest(text=text):
                self.service.reply(text)
                self.assertEqual(self.provider.calls, [])

    def test_changed_canonical_revision_rejects_delayed_proposal(self) -> None:
        self.provider.during_call = lambda: self.session.__setitem__(
            ConversationSession.REVISION_KEY, 99
        )
        result = self.service.reply('menu yang cocok dengan suasana santai')
        self.assertEqual(result['recommendations'], [])
        self.assertEqual(len(self.provider.calls), 1)

    def test_catalog_deactivation_during_call_cannot_return_inactive_menu(self) -> None:
        self.provider.during_call = lambda: MenuItem.objects.filter(pk=self.a.pk).update(
            is_available=False
        )
        result = self.service.reply('menu yang cocok dengan suasana santai')
        self.assertNotIn(self.a.pk, [m.item.pk for m in result['recommendations']])
        self.assertEqual(len(self.provider.calls), 1)

    def test_disabled_adapter_never_dispatches_or_consumes_session_quota(self) -> None:
        from unittest.mock import patch
        from ..services.gemini import GeminiClient

        with override_settings(GEMINI_ENABLED=False), patch.object(
            GeminiClient, 'generate'
        ) as generate:
            service = ChatbotService(self.session)
            service.reply('menu yang cocok dengan suasana santai')
            service.reply('enak buat nemenin nugas')

        generate.assert_not_called()
        self.assertEqual(self.session.get('gemini_calls', 0), 0)

    def test_no_consumer_can_bypass_unreserved_or_used_turn_slot(self) -> None:
        from ..services.ai.turn_generator import TurnGenerator

        provider = PacketProvider()
        provider.raw = 'invalid'
        boundary = TurnGenerator(provider)
        self.assertIsNone(boundary.generate('unreserved'))
        self.assertTrue(boundary.reserve(lambda: True))
        self.assertEqual(boundary.generate('first'), 'invalid')
        self.assertFalse(boundary.reserve(lambda: True))
        self.assertIsNone(boundary.generate('second'))
        self.assertEqual(provider.calls, ['first'])

    def test_timeout_does_not_refund_slot_or_allow_second_task(self) -> None:
        from ..services.ai.turn_generator import TurnGenerator

        provider = PacketProvider()

        def fail() -> None:
            raise TimeoutError()

        provider.during_call = fail
        boundary = TurnGenerator(provider)
        self.assertTrue(boundary.reserve(lambda: True))
        self.assertIsNone(boundary.generate('interpret'))
        self.assertIsNone(boundary.generate('classify'))
        self.assertFalse(boundary.reserve(lambda: True))
        self.assertEqual(provider.calls, ['interpret'])

    def test_v3_wrong_scope_and_invented_amount_are_rejected_atomically(self) -> None:
        for changes in (
            {'constraint_scope': 'PLAN_TOTAL'},
            {'context_ref': 'previous1'},
            {'amount': 1},
            {'intent': 'RESET'},
        ):
            packet = dict(
                proposal_version=3,
                intent='RECOMMEND',
                context_action='NEW_REQUEST',
                constraint_scope='CURRENT_SEARCH',
                context_ref='active',
                preference_operations=[
                    {'action': 'ADD', 'tag_ids': ['drink'], 'remove_tag_ids': []}
                ],
                entity_roles=[],
                numeric_bindings=[],
                clarification_key=None,
            )
            packet.update(changes)
            self.provider.raw = json.dumps(packet)
            result = self.service.reply('menu yang cocok dengan suasana santai')
            self.assertEqual(result['recommendations'], [])
            self.assertEqual(
                self.session.get(ConversationSession.STATE_KEY, {}).get('tags', []), []
            )

        self.assertEqual(len(self.provider.calls), 4)
