"""Authoritative conversation CAS, API revisions and privacy boundaries."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import json
from threading import Barrier
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.contrib.sessions.models import Session
from django.core import signing
from django.core.cache import cache
from django.db import close_old_connections, connections, OperationalError
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from ..services.conversation_session import ConversationSession
from ..services.conversation_store import (
    ConversationStore,
    ConversationConflict,
    ConversationStoreUnavailable,
)
from ..views import chat


class FakeChatbotService:
    """Stand-in for the AI service: records only the search state it is given."""

    def __init__(self, session: SessionStore) -> None:
        self.session = session

    def reply(self, message: str, more: bool = False, action: str | None = None) -> dict:
        del more
        search = self.session.get(ConversationSession.SEARCH_KEY, {})

        if not isinstance(search, dict):
            search = {}

        search = dict(search)

        if action == 'reset' or message == 'mulai lagi':
            self.session.pop(ConversationSession.SEARCH_KEY, None)
            search = {}
        elif 'jangan pedas' in message:
            search['excluded_tags'] = ['spicy']
        elif 'maksimal' in message:
            search['max_price'] = 20000

        if search:
            self.session[ConversationSession.SEARCH_KEY] = search

        return {
            'message': 'Halo!',
            'state': 'COLLECTING_PREFERENCES',
            'preferences': {},
            'recommendations': [],
            'quick_replies': [],
            'active_search': search,
        }


class ConversationStoreTests(TestCase):
    def setUp(self) -> None:
        self.legacy = SessionStore()
        self.legacy.update(
            {
                'cart': {'private': 'CART_CANARY'},
                '_auth_user_id': 'AUTH_CANARY',
                'chatbot_client_id': 'NONCE_CANARY',
            }
        )

    def turn(self, revision: int | None = None) -> ConversationStore:
        return ConversationStore('synthetic-identity', self.legacy, revision)

    def test_only_owned_state_is_stored_separately(self) -> None:
        self.legacy[ConversationSession.SEARCH_KEY] = {'excluded_tags': ['shrimp']}
        turn = self.turn()
        raw = Session.objects.get(session_key=turn.key).session_data
        decoded = signing.loads(raw, salt=ConversationStore.SALT)
        self.assertEqual(
            decoded['state'][ConversationSession.SEARCH_KEY]['excluded_tags'], ['shrimp']
        )

        for value in ('CART_CANARY', 'AUTH_CANARY', 'NONCE_CANARY'):
            self.assertNotIn(value, json.dumps(decoded))

        self.assertLessEqual(len(turn.key), 40)

    def test_same_base_two_writers_second_cannot_erase_first_exclusion(self) -> None:
        first, second = self.turn(), self.turn()
        first.session[ConversationSession.SEARCH_KEY] = {'excluded_tags': ['shrimp']}
        second.session[ConversationSession.SEARCH_KEY] = {'max_price': 10000}
        self.assertEqual(first.commit(), 1)

        with self.assertRaises(ConversationConflict):
            second.commit()

        current = self.turn()
        self.assertEqual(
            current.session[ConversationSession.SEARCH_KEY]['excluded_tags'], ['shrimp']
        )

    def test_expected_revision_rejects_old_action_before_service_execution(self) -> None:
        self.turn().commit()

        with self.assertRaises(ConversationConflict) as error:
            self.turn(0)

        self.assertEqual(error.exception.revision, 1)

    def test_reset_is_monotonic_and_late_request_cannot_restore_dialog(self) -> None:
        initial = self.turn()
        initial.session[ConversationSession.SEARCH_KEY] = {'excluded_tags': ['shrimp']}
        initial.commit()
        reset, late = self.turn(1), self.turn(1)
        ConversationSession(reset.session).reset()
        self.assertEqual(reset.commit(), 2)
        late.session[ConversationSession.SEARCH_KEY] = {'max_price': 20000}

        with self.assertRaises(ConversationConflict):
            late.commit()

        current = self.turn()
        self.assertNotIn(ConversationSession.SEARCH_KEY, current.session)
        self.assertEqual(current.revision, 2)

    def test_losing_provider_attempt_is_charged_once_without_business_delta(self) -> None:
        first, second = self.turn(), self.turn()
        first.session['gemini_calls'] = 1
        second.session['gemini_calls'] = 1
        second.session[ConversationSession.SEARCH_KEY] = {'excluded_tags': ['wrong']}
        first.commit()

        with self.assertRaises(ConversationConflict):
            second.commit()

        second.preserve_usage()
        current = self.turn()
        self.assertEqual(current.session['gemini_calls'], 2)
        self.assertNotIn(ConversationSession.SEARCH_KEY, current.session)

    def test_failed_turn_usage_preserved_without_partial_preferences(self) -> None:
        turn = self.turn()
        turn.session['gemini_calls'] = 2
        turn.session[ConversationSession.SEARCH_KEY] = {'max_price': 99999}
        turn.preserve_usage()
        current = self.turn()
        self.assertEqual(current.session['gemini_calls'], 2)
        self.assertNotIn(ConversationSession.SEARCH_KEY, current.session)

    def test_stale_main_session_mirror_has_no_authority(self) -> None:
        turn = self.turn()
        turn.session[ConversationSession.SEARCH_KEY] = {'excluded_tags': ['shrimp']}
        turn.commit()
        self.legacy[ConversationSession.SEARCH_KEY] = {'max_price': 1}
        self.assertEqual(
            self.turn().session[ConversationSession.SEARCH_KEY]['excluded_tags'], ['shrimp']
        )

    def test_identity_isolation_and_nonchat_fields_survive_mirror(self) -> None:
        turn = self.turn()
        turn.session[ConversationSession.SEARCH_KEY] = {'max_price': 10000}
        turn.commit()
        turn.mirror(self.legacy)
        self.assertEqual(self.legacy['cart'], {'private': 'CART_CANARY'})
        other = ConversationStore('different-identity', SessionStore())
        self.assertNotIn(ConversationSession.SEARCH_KEY, other.session)
        self.assertNotEqual(turn.key, other.key)

    def test_production_mirror_removal_keeps_auth_cart_and_identity(self) -> None:
        turn = self.turn()
        self.legacy[ConversationSession.SEARCH_KEY] = {'max_price': 10000}
        turn.mirror(self.legacy, enabled=False)
        self.assertNotIn(ConversationSession.SEARCH_KEY, self.legacy)
        self.assertEqual(self.legacy['cart'], {'private': 'CART_CANARY'})
        self.assertEqual(self.legacy['chatbot_client_id'], 'NONCE_CANARY')

    def test_expired_state_is_cleared_without_revision_aba_or_quota_reset(self) -> None:
        turn = self.turn()
        turn.session.update(
            {'gemini_calls': 7, ConversationSession.SEARCH_KEY: {'max_price': 20000}}
        )
        turn.commit()
        Session.objects.filter(session_key=turn.key).update(
            expire_date=timezone.now() - timedelta(seconds=1)
        )
        current = self.turn()
        self.assertNotIn(ConversationSession.SEARCH_KEY, current.session)
        self.assertEqual(current.session['gemini_calls'], 7)
        self.assertGreater(current.revision, 1)

    def test_oversized_state_rejected_without_commit(self) -> None:
        for value in ('x' * 40000, '😀' * 8000):
            turn = self.turn()
            turn.session['recommendation_last_message'] = value

            with self.assertRaises(ConversationStoreUnavailable):
                turn.commit()

            self.assertEqual(self.turn().revision, 0)

    def test_invalid_signature_and_foreign_fields_fail_closed(self) -> None:
        turn = self.turn()

        for raw in (
            'PRIVATE_BAD_SIGNATURE',
            signing.dumps({'schema': 1, 'state': {'cart': 'PRIVATE'}}, salt=ConversationStore.SALT),
        ):
            Session.objects.filter(session_key=turn.key).update(session_data=raw)

            with self.assertRaises(ConversationStoreUnavailable):
                self.turn()

    def test_browser_cookie_cannot_decode_authoritative_chat_payload(self) -> None:
        turn = self.turn()
        self.assertEqual(Session.objects.get(session_key=turn.key).get_decoded(), {})


class RevisionApiTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def send(self, message: str = 'halo', **extra: object):
        return self.client.post(
            '/api/recommendation/chat/',
            {'message': message, **extra},
            content_type='application/json',
        )

    def test_response_revision_and_stale_request_409_without_provider(self) -> None:
        with patch('recommendation.views.ChatbotService', FakeChatbotService):
            first = self.send()

        revision = first.json()['revision']

        with patch('recommendation.views.ChatbotService') as service:
            response = self.send('jangan pedas', revision=revision - 1)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['revision'], revision)
        self.assertNotIn('recommendations', response.json())
        service.assert_not_called()
        self.assertIn('no-store', response['Cache-Control'])
        self.assertRegex(response['X-Request-ID'], r'^[a-f0-9]{32}$')

    def test_invalid_revision_types_are_400_without_processing(self) -> None:
        for value in (True, None, -1, '1', 1.5, 2**53):
            with self.subTest(value=value):
                self.assertEqual(self.send(revision=value).status_code, 400)

    def test_legacy_client_without_revision_still_uses_authoritative_state(self) -> None:
        with patch('recommendation.views.ChatbotService', FakeChatbotService):
            self.send('jangan pedas')
            session = self.client.session
            session[ConversationSession.SEARCH_KEY] = {'max_price': 1}
            session.save()
            result = self.send('maksimal 20 ribu').json()

        self.assertIn('Pedas', ' '.join(result['active_search']['excluded_tags']))
        self.assertEqual(result['active_search']['max_price'], 20000)

    def test_reset_conflict_does_not_erase_newer_choice_or_quota(self) -> None:
        with patch('recommendation.views.ChatbotService', FakeChatbotService):
            first = self.send('jangan pedas').json()
            updated = self.send('maksimal 20 ribu', revision=first['revision']).json()
            response = self.send('mulai lagi', action='reset', revision=first['revision'])

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['revision'], updated['revision'])
        main = self.client.session
        current = ConversationStore(main['chatbot_client_id'], main)
        self.assertIn('spicy', current.session[ConversationSession.SEARCH_KEY]['excluded_tags'])

    def test_storage_error_returns_generic_503_without_private_details(self) -> None:
        with patch(
            'recommendation.views.ConversationStore',
            side_effect=RuntimeError('PRIVATE_STORE_CANARY'),
        ), self.assertLogs('recommendation.views', level='WARNING') as logs:
            response = self.send()

        self.assertEqual(response.status_code, 503)
        self.assertNotIn('PRIVATE_STORE_CANARY', response.content.decode())
        self.assertNotIn('PRIVATE_STORE_CANARY', '\n'.join(logs.output))

    def test_csrf_protection_still_precedes_processing(self) -> None:
        client = Client(enforce_csrf_checks=True)

        with patch('recommendation.views.ConversationStore') as store:
            response = client.post(
                '/api/recommendation/chat/', {'message': 'halo'}, content_type='application/json'
            )

        self.assertEqual(response.status_code, 403)
        store.assert_not_called()

    def test_parallel_first_requests_with_existing_cookie_use_stable_identity(self) -> None:
        main = self.client.session
        main['cart'] = {'keep': 'cart'}
        main.save()
        factory = RequestFactory()
        from django.contrib.sessions.backends.db import SessionStore as DbSession

        requests = [
            factory.post(
                '/api/recommendation/chat/',
                json.dumps({'message': 'halo'}),
                content_type='application/json',
            )
            for _ in range(2)
        ]

        with patch('recommendation.views.ChatbotService', FakeChatbotService):
            for request in requests:
                request.session = DbSession(session_key=main.session_key)
                response = chat(request)
                self.assertEqual(response.status_code, 200)

        self.assertEqual(
            requests[0].session['chatbot_client_id'], requests[1].session['chatbot_client_id']
        )
        self.assertEqual(
            Session.objects.filter(session_key__startswith=ConversationStore.PREFIX).count(), 1
        )

    def test_commit_race_returns_409_without_saving_losing_business_delta(self) -> None:
        with patch('recommendation.views.ChatbotService', FakeChatbotService):
            first = self.send('jangan pedas').json()
        commit = ConversationStore.commit
        raced = False

        def race(turn):
            nonlocal raced

            if not raced:
                raced = True
                main = self.client.session
                winner = ConversationStore(main['chatbot_client_id'], main)
                winner.session[ConversationSession.SEARCH_KEY]['excluded_tags'].append('shrimp')
                commit(winner)

            return commit(turn)

        with patch('recommendation.views.ChatbotService', FakeChatbotService), patch.object(
            ConversationStore, 'commit', race
        ):
            response = self.send('maksimal 10 ribu', revision=first['revision'])

        self.assertEqual(response.status_code, 409)
        main = self.client.session
        state = ConversationStore(main['chatbot_client_id'], main).session[
            ConversationSession.SEARCH_KEY
        ]
        self.assertIn('shrimp', state['excluded_tags'])
        self.assertNotIn('max_price', state)

    def test_debug_compatibility_mirror_is_not_required_in_production(self) -> None:
        with patch('recommendation.views.ChatbotService', FakeChatbotService):
            with override_settings(DEBUG=True):
                self.send('jangan pedas')

            self.assertIn(ConversationSession.SEARCH_KEY, self.client.session)

            with override_settings(DEBUG=False):
                response = self.send('maksimal 20 ribu')

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(ConversationSession.SEARCH_KEY, self.client.session)
        self.assertIn('Pedas', ' '.join(response.json()['active_search']['excluded_tags']))


class ConcurrentSqlCasTests(TransactionTestCase):
    def test_two_database_connections_never_both_commit_same_base(self) -> None:
        import sqlite3
        from uuid import uuid4

        if connections['default'].vendor != 'sqlite':
            self.skipTest('This shared-memory connection test targets SQLite only')

        original = ConversationStore('threaded-synthetic', SessionStore())
        database = deepcopy(connections['default'].settings_dict)
        uri = 'file:rasakita_cas_' + uuid4().hex + '?mode=memory&cache=shared'
        database['NAME'] = uri
        shared = sqlite3.connect(uri, uri=True)
        connections['default'].connection.backup(shared)
        barrier = Barrier(2)

        def writer(value: int) -> str:
            wrapper = connections['default'].copy()
            wrapper.settings_dict = deepcopy(database)
            connections['default'] = wrapper

            try:
                turn = ConversationStore('threaded-synthetic', SessionStore())
                turn.session[ConversationSession.SEARCH_KEY] = {'max_price': value}
                barrier.wait(timeout=10)

                try:
                    turn.commit()

                    return 'committed'
                except ConversationConflict:
                    return 'conflict'
                except OperationalError:
                    return 'storage_busy'
            finally:
                if wrapper.connection is not None:
                    wrapper.connection.close()
                    wrapper.connection = None

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(writer, (1, 2)))

            self.assertEqual(outcomes.count('committed'), 1)
            row = shared.execute(
                'SELECT session_data FROM django_session WHERE session_key = ?', (original.key,)
            ).fetchone()
            state = ConversationStore._decode(row[0])
            self.assertEqual(state[ConversationSession.REVISION_KEY], 1)
            self.assertIn(state[ConversationSession.SEARCH_KEY]['max_price'], {1, 2})
        finally:
            shared.close()
