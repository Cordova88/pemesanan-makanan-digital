"""AI-only chatbot contracts: no local fallback, explicit unavailability error."""

from decimal import Decimal

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import TestCase, override_settings

from menu.models import Category, MenuItem, MenuTag
from ..services.chatbot import ChatbotService, ChatbotUnavailable
from ..services.conversation_session import ConversationSession
from ..services.text_generator import TextGenerator


class FakeProvider(TextGenerator):
    def __init__(
        self,
        response: str | None = 'Halo! Mau makan apa hari ini?',
        *,
        available: bool = True,
        tool_calls: list[tuple[str, dict]] | None = None,
    ) -> None:
        self.response = response
        self._available = available
        self.tool_calls = tool_calls or []
        self.converse_calls = 0

    @property
    def available(self) -> bool:
        return self._available

    def generate(self, prompt: str) -> str | None:
        return self.response

    def converse(
        self,
        message: str,
        system_instruction: str,
        tool_declarations: list,
        tool_handler,
        before_request,
        max_iterations: int = 4,
    ):
        del system_instruction, tool_declarations, max_iterations
        self.converse_calls += 1

        if not self._available:
            return None, []

        if before_request is not None and not before_request():
            return None, []

        results = []

        for name, arguments in self.tool_calls:
            result = tool_handler(name, arguments)
            results.append({'name': name, 'arguments': arguments, 'result': result})

        return self.response, results


class ChatbotAiOnlyTests(TestCase):
    def setUp(self) -> None:
        self.session = SessionStore()
        self.category = Category.objects.create(name='Makanan')

    def service(self, provider: FakeProvider) -> ChatbotService:
        return ChatbotService(self.session, gemini_client=provider)

    def test_unavailable_provider_raises_explicit_error(self) -> None:
        with self.assertRaises(ChatbotUnavailable) as error:
            self.service(FakeProvider(available=False)).reply('halo')

        self.assertEqual(str(error.exception), ChatbotService.UNAVAILABLE_MESSAGE)

    def test_ai_reply_is_returned_without_local_recommendations(self) -> None:
        result = self.service(FakeProvider('Halo juga!')).reply('halo')

        self.assertEqual(result['message'], 'Halo juga!')
        self.assertEqual(result['recommendations'], [])
        self.assertEqual(result['quick_replies'], [])

    def test_ai_search_tool_supplies_recommendation_cards(self) -> None:
        tag = MenuTag.objects.create(name='spicy', display_name='Pedas')
        item = MenuItem.objects.create(
            name='Ayam Geprek', category=self.category, price=Decimal('15000.00')
        )
        item.tags.add(tag)
        provider = FakeProvider(
            'Coba Ayam Geprek, pedasnya pas.',
            tool_calls=[
                (
                    'search_menu',
                    {
                        'required_tags': ['spicy'],
                        'excluded_tags': [],
                        'excluded_item_ids': [],
                        'excluded_item_names': [],
                        'category': 'Makanan',
                        'max_price': None,
                        'exclude_shown': False,
                    },
                )
            ],
        )

        result = self.service(provider).reply('yang pedas dong')

        self.assertEqual(result['state'], 'RECOMMENDING')
        self.assertEqual([match.item.pk for match in result['recommendations']], [item.pk])
        self.assertEqual(result['active_search']['required_tags'], ['spicy'])
        self.assertIn(ConversationSession.SEARCH_KEY, self.session)
        self.assertIn(ConversationSession.SHOWN_KEY, self.session)

    def test_empty_message_still_uses_ai_greeting(self) -> None:
        provider = FakeProvider('Selamat datang!')

        result = self.service(provider).reply('')

        self.assertEqual(result['message'], 'Selamat datang!')
        self.assertEqual(provider.converse_calls, 1)

    def test_reset_clears_dialog_but_keeps_provider_quota(self) -> None:
        self.session[ConversationSession.SEARCH_KEY] = {'required_tags': ['spicy']}
        self.session[ConversationSession.STATE_KEY] = {'tags': ['spicy']}
        self.session[ConversationSession.GEMINI_CALLS_KEY] = 3

        result = self.service(FakeProvider('Halo lagi!')).reply('mulai lagi', action='reset')

        self.assertEqual(result['message'], 'Halo lagi!')
        self.assertNotIn(ConversationSession.SEARCH_KEY, self.session)
        self.assertNotIn(ConversationSession.STATE_KEY, self.session)
        self.assertEqual(
            self.session[ConversationSession.GEMINI_CALLS_KEY],
            4,  # Three carried over plus the one attempt made by this turn.
        )

    @override_settings(GEMINI_ENABLED=False, GEMINI_API_KEY='')
    def test_endpoint_returns_unavailable_error_when_provider_is_off(self) -> None:
        response = self.client.post(
            '/api/recommendation/chat/',
            {'message': 'halo'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error'], ChatbotService.UNAVAILABLE_MESSAGE)
