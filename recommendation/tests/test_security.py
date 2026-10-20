"""Phase7 bounded inputs, isolated cache guards, fake SDK metrics and privacy."""

import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from ..checks import chatbot_deployment_checks
from ..services.ai.GeminiInterpreter import GeminiInterpreter
from ..services.conversation_session import ConversationSession
from ..services.gemini import GeminiClient
from ..services.security import ChatInput, ChatInputError, UsageGuard, request_context
from ..services.telemetry import token_count
from ..services.telemetry import ranking_event, provider_event
from ..services.tag_extractor import Preferences
from ..services.chatbot import ChatbotService
from ..views import chat


class RankingTelemetryTests(SimpleTestCase):
    def test_catalog_privacy_check_reuses_the_existing_turn_bypass(self) -> None:
        from ..services.ai.turn_generator import TurnGenerator

        for text, private in (
            ('Nasi Goreng', False),
            ('Camilan', False),
            ('private@example.invalid', True),
            ('telepon 081234567890', True),
            ('api_key PRIVATE_CANARY', True),
        ):
            with self.subTest(text=text):
                generator = TurnGenerator(Mock())
                generator.protect(text)
                self.assertEqual(TurnGenerator.contains_private_data(text), private)
                self.assertEqual(
                    generator.reservation_block_reason, 'private_turn' if private else None
                )

    def test_reasons_are_allowlisted_and_only_attached_to_schema_rejections(self) -> None:
        for outcome, reason in (
            ('invalid_schema', 'PRIVATE_RESPONSE'),
            ('accepted', 'score'),
            ('proposal_validated', 'shape'),
            ('PRIVATE_OUTCOME', None),
        ):
            with self.subTest(outcome=outcome), patch(
                'recommendation.services.telemetry.logger.info'
            ) as log, self.assertRaises(ValueError):
                ranking_event(outcome, reason=reason)

            log.assert_not_called()

    def test_diagnostics_contain_only_fixed_metadata_and_request_correlation(self) -> None:
        token = request_context.set({'request_id': 'test-correlation', 'client': 'PRIVATE_CLIENT'})

        try:
            with self.assertLogs('recommendation.services.gemini', level='INFO') as logs:
                ranking_event('invalid_schema', reason='unknown_id')
                ranking_event('proposal_validated')
                ranking_event('accepted')
        finally:
            request_context.reset(token)

        events = [json.loads(record.message) for record in logs.records]
        base_keys = {'timestamp', 'request_id', 'event', 'outcome'}
        self.assertEqual(set(events[0]), base_keys | {'reason'})
        self.assertEqual(set(events[1]), base_keys)
        self.assertEqual(set(events[2]), base_keys)
        self.assertEqual({event['request_id'] for event in events}, {'test-correlation'})
        self.assertNotIn('PRIVATE_', '\n'.join(logs.output))


@override_settings(GEMINI_MAX_CALLS_PER_SESSION=50, CHATBOT_SEMANTIC_RERANKING_ENABLED=True)
class RankingRequestDiagnosticsTests(TestCase):
    def setUp(self) -> None:
        from menu.models import Category, MenuItem

        cache.clear()
        category = Category.objects.create(name='Makanan')
        self.first = MenuItem.objects.create(name='Pilihan A', category=category, price=10000)
        self.second = MenuItem.objects.create(name='Pilihan B', category=category, price=15000)
        self.session = SessionStore()
        self.provider = Mock(available=True)
        self.provider.generate.side_effect = self.generate

    def generate(self, prompt: str) -> str:
        # Synthetic provider metadata exercises the existing request ID pipeline.
        provider_event('test-ranking', 'success', 0)

        return json.dumps({'ranked_candidates': [{'id': self.second.pk, 'score': 1}]})

    def send_ranked(self, *, conflict: bool = False):
        from contextlib import ExitStack
        from ..services.conversation_store import ConversationConflict, ConversationStore

        request = RequestFactory().post(
            '/api/recommendation/chat/',
            data=json.dumps({'message': 'enak buat nemenin nugas'}),
            content_type='application/json',
            HTTP_X_REQUEST_ID='PRIVATE_HEADER',
        )
        request.session = self.session

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    'recommendation.views.ChatbotService',
                    side_effect=lambda session: ChatbotService(
                        session, gemini_client=self.provider
                    ),
                )
            )

            if conflict:
                stack.enter_context(
                    patch.object(
                        ConversationStore,
                        'commit',
                        side_effect=ConversationConflict(9),
                    )
                )

            logs = stack.enter_context(
                self.assertLogs('recommendation.services.gemini', level='INFO')
            )
            response = chat(request)

        events = [json.loads(record.message) for record in logs.records]
        self.assertEqual({event['request_id'] for event in events}, {response['X-Request-ID']})
        self.assertRegex(response['X-Request-ID'], r'^[0-9a-f]{32}$')
        self.assertNotIn('PRIVATE_', '\n'.join(logs.output))
        self.assertNotIn('nemenin nugas', '\n'.join(logs.output))
        self.assertEqual(self.provider.generate.call_count, 1)
        self.assertEqual(request_context.get(), {})

        return response, events

    def test_ranking_application_and_final_request_success_have_same_request_id(self) -> None:
        response, events = self.send_ranked()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['recommendations'][0]['id'], self.second.pk)
        self.assertEqual(
            [(event['event'], event['outcome']) for event in events],
            [
                ('provider_attempt', 'success'),
                ('ranking_validation', 'proposal_validated'),
                ('ranking_validation', 'accepted'),
                ('chat_request', 'success'),
            ],
        )

    def test_accepted_ranking_does_not_imply_commit_success(self) -> None:
        from ..services.conversation_store import ConversationStore

        response, events = self.send_ranked(conflict=True)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.content)['revision'], 9)
        self.assertEqual(
            [(event['event'], event['outcome']) for event in events],
            [
                ('provider_attempt', 'success'),
                ('ranking_validation', 'proposal_validated'),
                ('ranking_validation', 'accepted'),
                ('chat_request', 'revision_conflict'),
            ],
        )
        self.assertNotIn('recommendations', json.loads(response.content))
        stored = ConversationStore(self.session['chatbot_client_id'], self.session).session
        self.assertNotIn(ConversationSession.SEARCH_KEY, stored)


class ChatBoundaryTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.factory = RequestFactory()
        self.session = SessionStore()

    def send(
        self,
        data: object,
        *,
        raw: bytes | str | None = None,
        session: SessionStore | None = None,
        **meta: str
    ) -> object:
        meta.setdefault('CONTENT_TYPE', 'application/json')
        request = self.factory.post(
            '/api/recommendation/chat/',
            data=json.dumps(data) if raw is None else raw,
            content_type='application/json',
            **meta
        )
        request.session = session if session is not None else self.session

        return chat(request)

    def test_malformed_shapes_types_unknown_fields_and_actions_are_client_errors(self) -> None:
        for value in (
            [],
            None,
            3,
            {'message': 3},
            {'message': []},
            {'message': {}},
            {'message': None},
            {'action': None},
            {'action': True},
            {'action': 'purchase'},
            {'message': 'hi', 'extra': 'PRIVATE_CANARY'},
        ):
            with self.subTest(value=value), patch('recommendation.views.ChatbotService') as service:
                response = self.send(value)
                self.assertEqual(response.status_code, 400)
                service.assert_not_called()
                self.assertNotIn('PRIVATE_CANARY', response.content.decode())

    def test_invalid_json_duplicate_keys_utf8_surrogates_and_depth_fail_safely(self) -> None:
        for raw in (
            '{',
            '',
            '{"message":"a","message":"b"}',
            '{"message":"\\ud800"}',
            '[' * 1500 + ']' * 1500,
            b'\xff',
        ):
            response = self.send({}, raw=raw)
            self.assertEqual(response.status_code, 400)

    def test_message_and_body_limits_enforced_before_service(self) -> None:
        for raw in (json.dumps({'message': 'x' * 501}), ' ' * 9000):
            with patch('recommendation.views.ChatbotService') as service:
                self.assertEqual(self.send({}, raw=raw).status_code, 413)
                service.assert_not_called()

        self.assertEqual(self.send({'message': 'x' * 500}).status_code, 200)

    def test_content_type_and_method_are_checked(self) -> None:
        request = self.factory.post(
            '/api/recommendation/chat/', data='{}', content_type='text/plain'
        )
        request.session = self.session
        self.assertEqual(chat(request).status_code, 415)
        self.assertEqual(chat(self.factory.get('/api/recommendation/chat/')).status_code, 405)

    def test_empty_greeting_more_and_reset_are_valid(self) -> None:
        for payload in (
            {},
            {'message': ''},
            {'message': 'halo'},
            {'message': '', 'action': 'more'},
            {'message': 'mulai lagi', 'action': 'reset'},
        ):
            self.assertEqual(self.send(payload).status_code, 200)

    def test_request_identifiers_are_server_generated_and_response_is_not_cacheable(self) -> None:
        with self.assertLogs('recommendation.services.gemini', level='INFO') as logs:
            response = self.send({'message': 'halo'}, HTTP_X_REQUEST_ID='PRIVATE_CANARY')

        self.assertRegex(response['X-Request-ID'], r'^[0-9a-f]{32}$')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(request_context.get(), {})
        self.assertNotIn('PRIVATE_CANARY', response.content.decode())
        self.assertNotIn('PRIVATE_CANARY', str(logs.output))
        self.assertIn('"event": "chat_request"', str(logs.output))

    @override_settings(CHATBOT_REQUESTS_SESSION_PER_MINUTE=2)
    def test_reset_does_not_reset_request_limit(self) -> None:
        self.assertEqual(self.send({'message': 'halo'}).status_code, 200)
        self.assertEqual(self.send({'message': 'reset', 'action': 'reset'}).status_code, 200)
        response = self.send({'message': 'halo'})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '60')

    @override_settings(CHATBOT_REQUESTS_CLIENT_PER_MINUTE=2)
    def test_new_sessions_do_not_bypass_client_limit(self) -> None:
        for _ in range(2):
            self.assertEqual(
                self.send(
                    {'message': 'halo'},
                    session=SessionStore(),
                    HTTP_X_FORWARDED_FOR='192.0.2.' + str(_),
                ).status_code,
                200,
            )

        self.assertEqual(
            self.send(
                {'message': 'halo'}, session=SessionStore(), HTTP_X_FORWARDED_FOR='192.0.2.99'
            ).status_code,
            429,
        )

    @override_settings(CHATBOT_REQUESTS_GLOBAL_PER_MINUTE=1)
    def test_global_limit_applies_across_distinct_clients(self) -> None:
        self.assertEqual(self.send({'message': 'halo'}, REMOTE_ADDR='192.0.2.1').status_code, 200)
        self.assertEqual(
            self.send(
                {'message': 'halo'}, REMOTE_ADDR='192.0.2.2', session=SessionStore()
            ).status_code,
            429,
        )

    def test_cache_failure_and_internal_error_have_generic_response(self) -> None:
        guard = UsageGuard()
        guard.cache = Mock()
        guard.cache.add.side_effect = RuntimeError('PRIVATE_CANARY')

        with patch('recommendation.views.UsageGuard', return_value=guard):
            response = self.send({'message': 'halo'})

        self.assertEqual(response.status_code, 503)
        self.assertNotIn('PRIVATE_CANARY', response.content.decode())

        with patch(
            'recommendation.views.ChatbotService', side_effect=RuntimeError('PRIVATE_CANARY')
        ), self.assertLogs('recommendation.views', level='WARNING') as logs:
            response = self.send({'message': 'halo'})

        self.assertEqual(response.status_code, 503)
        self.assertNotIn('PRIVATE_CANARY', str(logs.output))

    @override_settings(DEBUG=False, CHATBOT_REQUIRE_SHARED_CACHE=True)
    def test_production_rejects_process_local_cache(self) -> None:
        self.assertEqual(self.send({'message': 'halo'}).status_code, 503)

    def test_csrf_middleware_rejects_missing_token_and_allows_valid_token(self) -> None:
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(
            client.post(
                '/api/recommendation/chat/', data='{}', content_type='application/json'
            ).status_code,
            403,
        )
        from django.middleware.csrf import _get_new_csrf_string

        token = _get_new_csrf_string()
        client.cookies['csrftoken'] = token
        response = client.post(
            '/api/recommendation/chat/',
            data='{}',
            content_type='application/json',
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)

    def test_ai_notice_matches_enabled_flag_without_constructing_provider(self) -> None:
        with patch('recommendation.services.gemini.genai.Client') as sdk:
            with override_settings(GEMINI_ENABLED=False):
                self.assertContains(self.client.get('/chatbot/'), 'Mode lokal aktif')

            with override_settings(GEMINI_ENABLED=True):
                self.assertContains(self.client.get('/chatbot/'), 'Google Gemini')

            sdk.assert_not_called()


class UsageGuardTests(SimpleTestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_concurrent_atomic_local_counter_never_exceeds_limit(self) -> None:
        guard = UsageGuard(cache)

        with patch(
            'recommendation.services.security.time.time', return_value=1000
        ), ThreadPoolExecutor(max_workers=8) as pool:
            allowed = list(pool.map(lambda _: guard.consume('concurrent-test', 7, 60), range(40)))

        self.assertEqual(sum(allowed), 7)

    def test_window_rolls_over_and_invalid_limit_fails_closed(self) -> None:
        guard = UsageGuard(cache)

        with patch('recommendation.services.security.time.time', return_value=1000):
            self.assertTrue(guard.consume('window-test', 1, 60))
            self.assertFalse(guard.consume('window-test', 1, 60))

        with patch('recommendation.services.security.time.time', return_value=1060):
            self.assertTrue(guard.consume('window-test', 1, 60))

        self.assertFalse(guard.consume('invalid', 0, 60))
        self.assertFalse(guard.consume('invalid', 1, 0))

    def test_identity_is_hmac_and_forwarded_headers_are_not_identity_authority(self) -> None:
        identity = UsageGuard.identity('192.0.2.1')
        self.assertRegex(identity, r'^[a-f0-9]{64}$')
        self.assertNotIn('192.0.2.1', identity)
        self.assertNotEqual(identity, UsageGuard.identity('192.0.2.2'))

    def test_idle_expiry_clears_dialog_not_quota_auth_or_identity(self) -> None:
        session = SessionStore()
        state = ConversationSession(session)
        state.save_preferences(Preferences(tags={'rice'}), 'RECOMMENDING')
        session['gemini_calls'] = 8
        session['chatbot_client_id'] = 'a' * 32
        session['_auth_user_id'] = 'sentinel'

        with patch('recommendation.services.conversation_session.time', return_value=1000):
            state.expire_dialog()

        with patch('recommendation.services.conversation_session.time', return_value=2800):
            state.expire_dialog()

        self.assertFalse(state.load_preferences().tags)
        self.assertEqual(session['gemini_calls'], 8)
        self.assertEqual(session['chatbot_client_id'], 'a' * 32)
        self.assertEqual(session['_auth_user_id'], 'sentinel')
        state.save_preferences(Preferences(tags={'rice'}), 'RECOMMENDING')
        session[state.LAST_ACTIVE_KEY] = 1000

        with patch('recommendation.services.conversation_session.time', return_value=2800):
            state.expire_dialog(touch=False)

        self.assertFalse(state.load_preferences().tags)

    def test_usage_snapshot_and_command_are_aggregate_not_billing(self) -> None:
        from io import StringIO
        from django.core.management import call_command

        guard = UsageGuard()
        self.assertTrue(guard.consume('provider:global', 2, 86400))
        snapshot = guard.snapshot()
        self.assertEqual(snapshot['provider_budget_attempts_current_utc_day'], 1)
        self.assertIsNone(snapshot['estimated_cost'])
        output = StringIO()
        call_command('chatbot_usage', stdout=output)
        self.assertEqual(json.loads(output.getvalue()), snapshot)

    @override_settings(DEBUG=True, ALLOWED_HOSTS=['*'])
    def test_deployment_checks_report_unsafe_profile_without_secrets(self) -> None:
        findings = chatbot_deployment_checks()
        ids = {finding.id for finding in findings}
        self.assertTrue({'chatbot.E001', 'chatbot.E002', 'chatbot.E007'} <= ids)
        self.assertTrue(all('SECRET_KEY' not in str(finding) for finding in findings))


@override_settings(GEMINI_ENABLED=True, CHATBOT_REQUIRE_SHARED_CACHE=False)
class ProviderSafetyTests(SimpleTestCase):
    def setUp(self) -> None:
        cache.clear()
        self.calls = []
        self.metadata = SimpleNamespace(
            prompt_token_count=100,
            candidates_token_count=30,
            thoughts_token_count=10,
            cached_content_token_count=20,
            total_token_count=140,
        )
        self.response = SimpleNamespace(text='valid output', usage_metadata=self.metadata)
        self.client = GeminiClient()
        self.client.client = SimpleNamespace(models=SimpleNamespace(generate_content=self.generate))

    def generate(self, **kwargs: object) -> object:
        self.calls.append(kwargs)

        return self.response

    def test_builtin_and_sdk_timeouts_have_safe_failure_category(self) -> None:
        import httpx

        for exc in (TimeoutError('PRIVATE_TIMEOUT'), httpx.ReadTimeout('PRIVATE_TIMEOUT')):
            with self.subTest(kind=type(exc).__name__):
                generate = Mock(side_effect=exc)
                self.client.client.models.generate_content = generate

                with self.assertLogs('recommendation.services.gemini', level='WARNING') as logs:
                    self.assertIsNone(self.client.generate('PRIVATE_PROMPT'))

                failure = next(
                    json.loads(r.getMessage())
                    for r in logs.records
                    if json.loads(r.getMessage())['event'] == 'provider_failure'
                )
                self.assertEqual(failure['category'], 'timeout')
                self.assertIsNone(failure['http_status'])
                self.assertFalse(failure['usage_available'])
                self.assertEqual(self.client.last_event['outcome'], 'TimeoutError')
                self.assertIsNone(self.client.last_event['total_tokens'])
                self.assertNotIn('PRIVATE_', str(logs.output))
                generate.assert_called_once()

    def test_transport_failure_does_not_leak_request_url(self) -> None:
        import httpx

        generate = Mock(
            side_effect=httpx.ConnectError(
                'PRIVATE_ERROR',
                request=httpx.Request('GET', 'https://example.invalid/?key=PRIVATE_KEY'),
            )
        )
        self.client.client.models.generate_content = generate

        with self.assertLogs('recommendation.services.gemini', level='WARNING') as logs:
            self.assertIsNone(self.client.generate('PRIVATE_PROMPT'))

        failure = next(
            json.loads(r.getMessage())
            for r in logs.records
            if json.loads(r.getMessage())['event'] == 'provider_failure'
        )
        self.assertEqual(failure['category'], 'transport')
        self.assertNotIn('PRIVATE_', str(logs.output))
        self.assertNotIn('example.invalid', str(logs.output))
        generate.assert_called_once()

    def test_api_status_is_classified_without_logging_error_body(self) -> None:
        from google.genai.errors import APIError

        cases = (
            (400, 'invalid_request'),
            (401, 'authentication'),
            (403, 'authentication'),
            (429, 'rate_limited'),
            (500, 'upstream'),
            (503, 'upstream'),
            (418, 'api_error'),
        )

        for status, category in cases:
            with self.subTest(status=status):
                generate = Mock(
                    side_effect=APIError(status, {'error': {'message': 'PRIVATE_BODY'}})
                )
                self.client.client.models.generate_content = generate

                with self.assertLogs('recommendation.services.gemini', level='WARNING') as logs:
                    self.assertIsNone(self.client.generate('PRIVATE_PROMPT'))

                failure = next(
                    json.loads(r.getMessage())
                    for r in logs.records
                    if json.loads(r.getMessage())['event'] == 'provider_failure'
                )
                self.assertEqual(failure['category'], category)
                self.assertEqual(failure['http_status'], status)
                self.assertNotIn('PRIVATE_', str(logs.output))
                generate.assert_called_once()

    def test_unexpected_provider_exception_has_generic_category(self) -> None:
        self.client.client.models.generate_content = Mock(
            side_effect=RuntimeError('PRIVATE_KEY PRIVATE_PROMPT')
        )

        with self.assertLogs('recommendation.services.gemini', level='WARNING') as logs:
            self.assertIsNone(self.client.generate('PRIVATE_PROMPT'))

        failure = next(
            json.loads(r.getMessage())
            for r in logs.records
            if json.loads(r.getMessage())['event'] == 'provider_failure'
        )
        self.assertEqual(failure['category'], 'unexpected')
        self.assertIsNone(failure['http_status'])
        self.assertNotIn('PRIVATE_', str(logs.output))

    def test_failure_metadata_rejects_uncontrolled_values(self) -> None:
        from ..services.telemetry import provider_failure_event

        for category, status in (
            ('PRIVATE_BODY', None),
            ('upstream', '503 PRIVATE_BODY'),
            ('api_error', True),
            ('api_error', 999),
        ):
            with self.subTest(category=category, status=status), self.assertRaises(ValueError):
                provider_failure_event(category, status)

    def test_success_has_no_failure_diagnostic_or_extra_provider_dispatch(self) -> None:
        with self.assertLogs('recommendation.services.gemini', level='INFO') as logs:
            self.assertEqual(self.client.generate('test'), 'valid output')

        self.assertEqual(
            [json.loads(r.getMessage())['event'] for r in logs.records], ['provider_attempt']
        )
        self.assertEqual(len(self.calls), 1)

    @override_settings(GEMINI_ENABLED=False)
    def test_disabled_provider_does_not_call_sdk(self) -> None:
        self.assertIsNone(self.client.generate('PRIVATE_PROMPT'))
        self.assertFalse(self.calls)
        self.assertEqual(self.client.last_event['outcome'], 'disabled')
        self.assertFalse(self.client.last_event['provider_called'])

    def test_sdk_metadata_logged_without_prompt_response_or_identity(self) -> None:
        with self.assertLogs('recommendation.services.gemini', level='INFO') as logs:
            self.assertEqual(self.client.generate('PRIVATE_PROMPT'), 'valid output')

        event = self.client.last_event
        self.assertEqual(
            (
                event['input_tokens'],
                event['output_tokens'],
                event['thinking_tokens'],
                event['cached_tokens'],
                event['total_tokens'],
            ),
            (100, 30, 10, 20, 140),
        )
        self.assertIsNone(event['estimated_cost'])
        self.assertNotIn('PRIVATE_PROMPT', str(logs.output))
        self.assertNotIn('valid output', str(logs.output))
        self.assertEqual(self.calls[0]['config'].max_output_tokens, 512)

    def test_missing_or_invalid_metadata_is_unknown_not_zero(self) -> None:
        self.response.usage_metadata = None
        self.client.generate('test')
        self.assertIsNone(self.client.last_event['input_tokens'])
        self.assertIsNone(
            token_count(SimpleNamespace(prompt_token_count=True), 'prompt_token_count')
        )
        self.assertIsNone(token_count(SimpleNamespace(prompt_token_count=-1), 'prompt_token_count'))

    @override_settings(GEMINI_GLOBAL_CALLS_PER_DAY=1)
    def test_global_provider_budget_is_independent_of_session_reset(self) -> None:
        self.assertEqual(self.client.generate('first'), 'valid output')
        ConversationSession(SessionStore()).reset()
        self.assertIsNone(self.client.generate('second'))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.client.last_event['outcome'], 'quota_exhausted')

    @override_settings(GEMINI_CLIENT_CALLS_PER_DAY=1)
    def test_client_provider_budget_spans_sessions(self) -> None:
        first = request_context.set({'client': 'client-id', 'session': 'session-a'})

        try:
            self.assertEqual(self.client.generate('first'), 'valid output')
        finally:
            request_context.reset(first)

        second = request_context.set({'client': 'client-id', 'session': 'session-b'})

        try:
            self.assertIsNone(self.client.generate('second'))
        finally:
            request_context.reset(second)

        self.assertEqual(len(self.calls), 1)

    def test_timeout_error_empty_and_oversized_output_have_safe_fallback(self) -> None:
        self.client.client.models.generate_content = Mock(side_effect=TimeoutError('PRIVATE_ERROR'))

        with self.assertLogs('recommendation.services.gemini', level='WARNING') as logs:
            self.assertIsNone(self.client.generate('PRIVATE_PROMPT'))

        self.assertNotIn('PRIVATE_ERROR', str(logs.output))
        self.client.client.models.generate_content = self.generate
        self.response.text = 'x' * 16001
        self.assertIsNone(self.client.generate('test'))
        before = len(self.calls)
        self.assertIsNone(self.client.generate('x' * 16001))
        self.assertEqual(len(self.calls), before)

    def test_interpreter_and_classifier_exceptions_do_not_escape(self) -> None:
        fake = Mock()
        fake.generate.side_effect = RuntimeError('PRIVATE_ERROR')
        interpreter = GeminiInterpreter(fake)
        self.assertIsNone(interpreter.interpret('ingin nasi'))
        self.assertIsNone(interpreter.classify_entity('sepeda', 'ingin sepeda'))
