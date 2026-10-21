"""Offline regressions: no SDK client construction, credentials, or real transport."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.core.cache import caches
from django.test import SimpleTestCase, override_settings
from google.genai import types

from ..services.conversation_session import ConversationSession
from ..services.gemini import GeminiClient
from ..services.security import UsageGuard, request_context


@override_settings(
    GEMINI_ENABLED=True,
    GEMINI_MODEL='dummy-model',
    GEMINI_GLOBAL_CALLS_PER_DAY=100,
    GEMINI_CLIENT_CALLS_PER_DAY=20,
    GEMINI_MAX_CALLS_PER_SESSION=10,
    CHATBOT_REQUIRE_SHARED_CACHE=False,
    CHATBOT_CACHE_ALIAS='audit_regressions',
    CACHES={'audit_regressions': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'audit-regressions-only',
    }},
)
class ConversationQuotaTests(SimpleTestCase):
    def setUp(self):
        caches['audit_regressions'].clear()
        self.addCleanup(caches['audit_regressions'].clear)
        token = request_context.set({})
        self.addCleanup(request_context.reset, token)
        # Bypass __init__ entirely: even an inherited real key cannot create a client.
        self.provider = GeminiClient.__new__(GeminiClient)
        self.provider.last_event = None
        self.dispatch = Mock(return_value=SimpleNamespace(
            text='Dummy response', usage_metadata=None,
            candidates=[SimpleNamespace(content=types.Content(
                role='model', parts=[types.Part(text='Dummy response')],
            ))],
        ))
        self.provider.client = SimpleNamespace(models=SimpleNamespace(
            generate_content=self.dispatch,
        ))
        self.budget = Mock(return_value=True)
        self.handler = Mock(return_value={'ok': True})

    def converse(self, session='dummy-a', client='dummy-client'):
        token = request_context.set({
            'session': session, 'client': client, 'request_id': 'dummy-request',
        })
        try:
            return self.provider.converse(
                'Dummy message', 'Dummy instruction', [], self.handler, self.budget,
            )
        finally:
            request_context.reset(token)

    @override_settings(GEMINI_GLOBAL_CALLS_PER_DAY=1)
    def test_global_quota_spans_clients_and_conversations(self):
        self.assertEqual(self.converse()[0], 'Dummy response')
        self.assertEqual(self.converse('dummy-b', 'other-client'), (None, []))
        self.assertEqual(self.dispatch.call_count, 1)
        self.assertEqual(self.provider.last_event['outcome'], 'quota_exhausted')

    @override_settings(GEMINI_CLIENT_CALLS_PER_DAY=1)
    def test_client_quota_spans_fresh_conversations(self):
        self.assertEqual(self.converse()[0], 'Dummy response')
        self.assertEqual(self.converse('dummy-b'), (None, []))
        self.assertEqual(self.dispatch.call_count, 1)

    @override_settings(GEMINI_MAX_CALLS_PER_SESSION=1)
    def test_provider_session_quota_applies_to_conversation(self):
        self.assertEqual(self.converse()[0], 'Dummy response')
        self.assertEqual(self.converse(), (None, []))
        self.assertEqual(self.dispatch.call_count, 1)

    @override_settings(GEMINI_GLOBAL_CALLS_PER_DAY=1)
    def test_generate_and_converse_share_accounting_in_both_directions(self):
        for first in ('generate', 'converse'):
            with self.subTest(first=first):
                caches['audit_regressions'].clear()
                self.dispatch.reset_mock()
                if first == 'generate':
                    self.assertEqual(self.provider.generate('Dummy'), 'Dummy response')
                    self.assertEqual(self.converse(), (None, []))
                else:
                    self.assertEqual(self.converse()[0], 'Dummy response')
                    self.assertIsNone(self.provider.generate('Dummy'))
                self.assertEqual(self.dispatch.call_count, 1)

    @override_settings(GEMINI_GLOBAL_CALLS_PER_DAY=1)
    def test_each_tool_iteration_needs_shared_budget(self):
        self.dispatch.return_value = SimpleNamespace(candidates=[SimpleNamespace(
            content=types.Content(role='model', parts=[types.Part(
                function_call=types.FunctionCall(name='dummy_tool', args={}),
            )]),
        )])
        text, results = self.converse()
        self.assertIsNone(text)
        self.assertEqual(len(results), 1)
        self.handler.assert_called_once_with('dummy_tool', {})
        self.assertEqual(self.dispatch.call_count, 1)

    def test_local_budget_denial_does_not_dispatch_or_consume_daily_budget(self):
        self.budget.return_value = False
        self.assertEqual(self.converse(), (None, []))
        self.dispatch.assert_not_called()
        self.assertEqual(UsageGuard().snapshot()['provider_budget_attempts_current_utc_day'], 0)

    @override_settings(GEMINI_ENABLED=False)
    def test_disabled_provider_does_not_dispatch(self):
        self.assertEqual(self.converse(), (None, []))
        self.dispatch.assert_not_called()
        self.budget.assert_not_called()

    def test_unconfigured_provider_does_not_dispatch(self):
        self.provider.client = None
        self.assertEqual(self.converse(), (None, []))
        self.dispatch.assert_not_called()
        self.budget.assert_not_called()

    def test_cache_failure_fails_closed(self):
        with patch.object(caches['audit_regressions'], 'add', side_effect=RuntimeError):
            self.assertEqual(self.converse(), (None, []))
        self.dispatch.assert_not_called()
        self.assertEqual(self.provider.last_event['outcome'], 'guard_unavailable')

    @override_settings(GEMINI_GLOBAL_CALLS_PER_DAY=1)
    def test_failed_attempt_consumes_budget_without_retry(self):
        self.dispatch.side_effect = TimeoutError('dummy timeout')
        with self.assertLogs('recommendation.services.gemini', level='WARNING'):
            self.assertEqual(self.converse(), (None, []))
        self.assertEqual(self.converse('dummy-b'), (None, []))
        self.assertEqual(self.dispatch.call_count, 1)

    def test_response_tokens_are_logged_without_message_context_or_response(self):
        self.dispatch.return_value.usage_metadata = SimpleNamespace(
            prompt_token_count=100, candidates_token_count=30,
            thoughts_token_count=10, cached_content_token_count=20, total_token_count=140,
        )
        with self.assertLogs('recommendation.services.gemini', level='INFO') as logs:
            self.assertEqual(self.converse()[0], 'Dummy response')
        self.assertEqual(len(logs.records), 1)
        event = json.loads(logs.records[0].getMessage())
        self.assertEqual(event['event'], 'provider_attempt')
        self.assertEqual(event['outcome'], 'success')
        self.assertTrue(event['provider_called'])
        self.assertEqual(event['model'], 'dummy-model')
        self.assertEqual(event['request_id'], 'dummy-request')
        self.assertGreaterEqual(event['latency_ms'], 0)
        self.assertEqual(
            [event[k] for k in ('input_tokens', 'output_tokens', 'thinking_tokens',
                                'cached_tokens', 'total_tokens')],
            [100, 30, 10, 20, 140],
        )
        self.assertIsNone(event['estimated_cost'])
        self.assertEqual(self.provider.last_event, event)
        for private in ('Dummy message', 'Dummy instruction', 'Dummy response', 'dummy-client'):
            self.assertNotIn(private, str(logs.output))
        self.dispatch.assert_called_once()

    def test_tool_and_final_response_each_log_their_own_usage(self):
        tool_response = SimpleNamespace(
            usage_metadata=SimpleNamespace(total_token_count=12),
            candidates=[SimpleNamespace(content=types.Content(role='model', parts=[types.Part(
                function_call=types.FunctionCall(
                    name='dummy_tool', args={'note': 'PRIVATE_ARGUMENT'},
                ),
            )]))],
        )
        self.dispatch.return_value.usage_metadata = SimpleNamespace(total_token_count=25)
        self.dispatch.side_effect = [tool_response, self.dispatch.return_value]
        self.handler.return_value = {'ok': True, 'note': 'PRIVATE_TOOL_RESULT'}
        with self.assertLogs('recommendation.services.gemini', level='INFO') as logs:
            text, results = self.converse()
        self.assertEqual(text, 'Dummy response')
        self.assertEqual(len(results), 1)
        self.assertEqual(self.dispatch.call_count, 2)
        events = [json.loads(record.getMessage()) for record in logs.records]
        self.assertEqual([event['total_tokens'] for event in events], [12, 25])
        self.assertEqual([event['outcome'] for event in events], ['success', 'success'])
        self.assertEqual({event['request_id'] for event in events}, {'dummy-request'})
        self.assertNotIn('PRIVATE_', str(logs.output))

    def test_missing_or_invalid_usage_remains_unknown_in_logs(self):
        for metadata in (None, SimpleNamespace(total_token_count=True, prompt_token_count=-1)):
            with self.subTest(metadata=metadata):
                self.dispatch.return_value.usage_metadata = metadata
                with self.assertLogs('recommendation.services.gemini', level='INFO') as logs:
                    self.converse()
                event = json.loads(logs.records[0].getMessage())
                self.assertIsNone(event['total_tokens'])
                self.assertIsNone(event['input_tokens'])

    def test_response_without_candidate_still_logs_usage(self):
        self.dispatch.return_value = SimpleNamespace(
            candidates=[], usage_metadata=SimpleNamespace(total_token_count=7),
        )
        with self.assertLogs('recommendation.services.gemini', level='INFO') as logs:
            self.assertEqual(self.converse(), (None, []))
        event = json.loads(logs.records[0].getMessage())
        self.assertEqual(event['total_tokens'], 7)
        self.assertEqual(event['outcome'], 'empty_or_rejected')
        self.assertTrue(event['provider_called'])

    def test_failure_logs_one_attempt_and_safe_category_without_raw_exception(self):
        for exception, outcome, category in (
            (TimeoutError('PRIVATE_TIMEOUT'), 'TimeoutError', 'timeout'),
            (RuntimeError('PRIVATE_KEY PRIVATE_BODY'), 'provider_error', 'unexpected'),
        ):
            with self.subTest(outcome=outcome):
                self.dispatch.reset_mock()
                self.dispatch.side_effect = exception
                with self.assertLogs('recommendation.services.gemini', level='WARNING') as logs:
                    self.assertEqual(self.converse(), (None, []))
                events = [json.loads(record.getMessage()) for record in logs.records]
                self.assertEqual([e['event'] for e in events], ['provider_attempt', 'provider_failure'])
                self.assertEqual(events[0]['outcome'], outcome)
                self.assertTrue(events[0]['provider_called'])
                self.assertIsNone(events[0]['total_tokens'])
                self.assertEqual(events[1]['category'], category)
                self.assertNotIn('PRIVATE_', str(logs.output))
                self.dispatch.assert_called_once()


class ResetContextTests(SimpleTestCase):
    def test_reset_discards_recent_text_and_preserves_usage_and_other_session_data(self):
        session = SessionStore()
        session.update({
            'recommendation_last_message': 'Dummy customer text',
            'recommendation_last_response': 'Dummy assistant text',
            'gemini_calls': 3, 'chatbot_client_id': 'd' * 32,
            'cart': [{'dummy': True}], '_auth_user_id': 'dummy-user',
        })
        ConversationSession(session).reset()
        self.assertNotIn('recommendation_last_message', session)
        self.assertNotIn('recommendation_last_response', session)
        self.assertEqual(session['gemini_calls'], 3)
        self.assertEqual(session['chatbot_client_id'], 'd' * 32)
        self.assertEqual(session['cart'], [{'dummy': True}])
        self.assertEqual(session['_auth_user_id'], 'dummy-user')
