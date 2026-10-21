"""Routing outcomes and provider trust boundaries, using synthetic catalog only."""

from copy import deepcopy
from decimal import Decimal
import json
from unittest.mock import patch

from django.contrib.sessions.backends.db import SessionStore
from django.test import SimpleTestCase, TestCase
from menu.models import Category, MenuItem, MenuTag

from ..services.budget import BudgetRequest
from ..services.chatbot import ChatbotService
from ..services.conversation_interpreter import (
    ConversationInterpretation,
    ConversationInterpreter,
    ConversationIntent,
    PreferenceOperation,
)
from ..services.conversation_session import ConversationSession
from ..services.decision_router import DecisionRouter, RoutingDecision
from ..services.entity_resolver import EntityResolution


def proposal(**changes: object) -> str:
    data = dict(
        intent='RECOMMEND',
        add_tags=['drink'],
        remove_tags=[],
        excluded_tags=[],
        soft_excluded_tags=[],
        moods=[],
        clear_moods=False,
        max_price=None,
        prefer_affordable=None,
        clear_max_price=False,
        clear_prefer_affordable=False,
        message_is_meaningful=True,
    )
    data.update(changes)

    return json.dumps(data)


class FakeProvider:
    def __init__(self, raw: str | None = None, *, fails: bool = False) -> None:
        self.raw = raw
        self.fails = fails
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str | None:
        self.calls.append(prompt)

        if self.fails:
            raise TimeoutError('synthetic timeout')

        return self.raw


class DecisionRouterTests(SimpleTestCase):
    def test_objective_messages_use_resolved_actions(self) -> None:
        for text in ('halo', 'jangan pedas', 'aku mau ayam', 'minuman', 'yang lain'):
            with self.subTest(text=text):
                local = ConversationInterpreter().interpret(text)
                self.assertEqual(DecisionRouter.decide(text, local).route, RoutingDecision.LOCAL)

    def test_subjective_examples_need_assistance_even_with_partial_local_tags(self) -> None:
        for text in (
            'enak buat nemenin nugas',
            'yang ringan tapi nggak bikin cepat lapar',
            'aku ingin yang nggak bikin eneg tapi cukup mengenyangkan',
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    DecisionRouter.decide(text, ConversationInterpreter().interpret(text)).route,
                    RoutingDecision.AI_ASSISTED,
                )

    def test_known_entity_wins_over_generic_food_cues(self) -> None:
        entity = EntityResolution('Es Kelapa', 'IN_CATALOG', 'beverage', menu_ids=(7,))
        self.assertEqual(
            DecisionRouter.decide(
                'yang es kelapa', ConversationInterpretation('SELECT_RECOMMENDATION'), entity=entity
            ).route,
            RoutingDecision.LOCAL,
        )

    def test_ambiguous_catalog_needs_clarification_without_provider(self) -> None:
        entity = EntityResolution('Es', 'AMBIGUOUS_CATALOG', 'beverage', menu_ids=(1, 2))
        self.assertEqual(
            DecisionRouter.decide('es', ConversationInterpretation('UNKNOWN'), entity=entity).route,
            RoutingDecision.CLARIFY,
        )

    def test_missing_antecedent_cannot_be_invented_by_ai(self) -> None:
        local = ConversationInterpretation(
            'UNKNOWN', contextual_reference='first', contextual_revision=True
        )
        self.assertEqual(
            DecisionRouter.decide('yang tadi terlalu berat', local).reason, 'missing_reference'
        )

    def test_valid_antecedent_allows_unresolved_revision_assistance(self) -> None:
        local = ConversationInterpretation(
            'UNKNOWN', contextual_reference='first', contextual_revision=True
        )
        self.assertEqual(
            DecisionRouter.decide('yang tadi terlalu berat', local, has_reference=True).route,
            RoutingDecision.AI_ASSISTED,
        )

    def test_conflicting_money_cannot_be_repaired_by_ai(self) -> None:
        budget = BudgetRequest(clarification='Batas bertentangan')
        self.assertEqual(
            DecisionRouter.decide(
                'enak buat nugas', ConversationInterpretation('UNKNOWN'), budget=budget
            ).reason,
            'budget_conflict',
        )

    def test_unresolved_entity_uses_only_classification_task(self) -> None:
        entity = EntityResolution('xyz', 'AMBIGUOUS_REQUEST', 'unknown')
        decision = DecisionRouter.decide(
            'mau xyz', ConversationInterpretation('UNKNOWN'), entity=entity
        )
        self.assertEqual(
            (decision.route, decision.task), (RoutingDecision.AI_ASSISTED, 'classify_entity')
        )

    def test_gibberish_needs_clarification_without_spending_calls(self) -> None:
        self.assertEqual(
            DecisionRouter.decide('asdfgh', ConversationInterpretation('UNKNOWN')).route,
            RoutingDecision.CLARIFY,
        )

    def test_shared_contract_rejects_operation_injection_and_inconsistent_delta(self) -> None:
        local = ConversationInterpretation('UNKNOWN')

        for operations in (
            [PreferenceOperation('EXECUTE')],
            [PreferenceOperation('ADD', ('spicy',))],
        ):
            ai = ConversationInterpretation(
                'RECOMMEND', source='gemini', tags={'drink'}, operations=operations
            )
            self.assertFalse(
                DecisionRouter.accepts_proposal(
                    ai, allowed_tags={'drink', 'spicy'}, local=local, hard_exclusions=set()
                )
            )


class RoutingIntegrationTests(TestCase):
    def setUp(self) -> None:
        category = Category.objects.create(name='Minuman')
        self.item = MenuItem.objects.create(
            name='Es Kelapa', price=Decimal('10000'), category=category
        )
        self.other = MenuItem.objects.create(
            name='Es Jeruk', price=Decimal('12000'), category=category
        )
        self.item.tags.add(MenuTag.objects.create(name='drink'))
        self.other.tags.add(MenuTag.objects.get(name='drink'))
        self.session = SessionStore()
        self.provider = FakeProvider()

    def reply(self, text: str) -> dict:
        return ChatbotService(self.session, gemini_client=self.provider).reply(text)

    def business(self) -> dict:
        keys = (
            ConversationSession.STATE_KEY,
            ConversationSession.SEARCH_KEY,
            ConversationSession.FOCUS_KEY,
            ConversationSession.CANDIDATES_KEY,
            ConversationSession.REJECTED_KEY,
            ConversationSession.SHOWN_KEY,
            'last_recommendations',
            'last_question',
        )

        return {key: deepcopy(self.session.get(key)) for key in keys}

    def test_clear_catalog_budget_and_dialog_never_call_provider(self) -> None:
        for text in (
            'halo',
            'minuman 10k',
            'yang es kelapa',
            'yang pertama',
            'yang lain',
            'jangan pedas',
            'pilihan minuman apa aja?',
            'mulai lagi',
        ):
            self.reply(text)

        self.assertEqual(self.provider.calls, [])

    def test_valid_interpretation_proposal_reuses_existing_local_filter(self) -> None:
        self.reply('maksimal 10k')
        self.provider.raw = proposal()
        result = self.reply('menu yang cocok dengan suasana santai')
        self.assertEqual([match.item.pk for match in result['recommendations']], [self.item.pk])
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.session[ConversationSession.SEARCH_KEY]['budget']['maximum'], '10000')

    def test_timeout_clarifies_without_partial_preference_or_focus_changes(self) -> None:
        self.reply('yang es kelapa')
        saved = self.business()
        self.provider.fails = True
        result = self.reply('menu yang cocok dengan suasana santai')
        self.assertEqual(result['recommendations'], [])
        self.assertEqual(self.business(), saved)
        self.assertEqual(len(self.provider.calls), 1)
        self.assertIn('belum bisa memastikan', result['message'])

    def test_missing_reference_is_local_clarification(self) -> None:
        result = self.reply('yang pertama')
        self.assertEqual(result['recommendations'], [])
        self.assertEqual(self.provider.calls, [])
        self.assertIn('pilihan sebelumnya', result['message'])

    def test_ambiguous_names_do_not_choose_arbitrarily(self) -> None:
        result = self.reply('aku mau es kelapa atau es jeruk')
        self.assertEqual(result['recommendations'], [])
        self.assertEqual(self.provider.calls, [])

    def test_invalid_wire_output_cannot_corrupt_business_state(self) -> None:
        self.reply('yang es kelapa')
        saved = self.business()

        for raw in (
            '{',
            proposal(target_menu_id=999),
            proposal(intent='RESET'),
            proposal(add_tags=['not_in_catalog']),
            proposal(max_price=True),
            proposal(stock='available'),
            proposal(add_tags='drink'),
        ):
            with self.subTest(raw=raw):
                self.provider.raw = raw
                result = self.reply('menu yang cocok dengan suasana santai')
                self.assertEqual(result['recommendations'], [])
                self.assertEqual(self.business(), saved)

    def test_ai_cannot_invent_or_clear_money_even_when_schema_valid(self) -> None:
        self.reply('minuman 10k')
        saved = self.business()

        for raw in (proposal(max_price=20000), proposal(clear_max_price=True)):
            self.provider.raw = raw
            self.assertEqual(
                self.reply('menu yang cocok dengan suasana santai')['recommendations'], []
            )
            self.assertEqual(self.business(), saved)

    def test_ai_cannot_relax_saved_hard_exclusion(self) -> None:
        self.reply('jangan manis')
        saved = self.business()
        self.provider.raw = proposal(add_tags=['sweet'])
        self.assertEqual(self.reply('menu yang cocok dengan suasana santai')['recommendations'], [])
        self.assertEqual(self.business(), saved)

    def test_explicit_hard_ban_cannot_be_dropped_from_subjective_message(self) -> None:
        self.provider.raw = proposal()
        self.reply('enak buat nemenin nugas tapi jangan pedas')
        self.assertIn('spicy', self.session[ConversationSession.SEARCH_KEY]['excluded_tags'])
        self.assertIn('spicy', self.session[ConversationSession.STATE_KEY]['excluded_tags'])

    def test_unavailable_catalog_is_still_filtered_after_ai(self) -> None:
        self.item.is_available = False
        self.item.save(update_fields=['is_available'])
        self.provider.raw = proposal()
        result = self.reply('menu yang cocok dengan suasana santai')
        self.assertEqual([match.item.pk for match in result['recommendations']], [self.other.pk])

    def test_session_quota_refusal_clarifies_without_call(self) -> None:
        self.session['gemini_calls'] = 999
        self.assertEqual(self.reply('menu yang cocok dengan suasana santai')['recommendations'], [])
        self.assertEqual(self.provider.calls, [])

    def test_ambiguous_object_attempts_one_classifier_not_second_interpreter(self) -> None:
        self.reply('aku mau beli xyzabc')
        self.assertEqual(len(self.provider.calls), 1)

    def test_shared_contract_defense_rejects_internal_fabricated_id(self) -> None:
        ai = ConversationInterpretation(
            'RECOMMEND',
            source='gemini',
            target_menu_id=999,
            tags={'drink'},
            operations=[PreferenceOperation('ADD', ('drink',))],
        )

        with patch(
            'recommendation.services.ai.GeminiInterpreter.GeminiInterpreter.interpret',
            return_value=ai,
        ):
            self.assertEqual(
                self.reply('menu yang cocok dengan suasana santai')['recommendations'], []
            )

    def test_single_candidate_subjective_budget_skips_provider(self) -> None:
        self.provider.raw = proposal()
        result = self.reply('enak buat nemenin nugas maksimal 10k')
        self.assertEqual([match.item.pk for match in result['recommendations']], [self.item.pk])
        self.assertEqual(len(self.provider.calls), 0)
