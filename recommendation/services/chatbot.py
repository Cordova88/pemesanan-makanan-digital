"""AI-only chatbot orchestration.

Gemini is the only source of conversational replies. When it is unavailable or
returns something that fails validation, the API reports an error instead of
falling back to a local response pipeline.
"""

from typing import ClassVar, cast

from django.conf import settings
from django.contrib.sessions.backends.base import SessionBase

from menu.models import MenuTag

from .ai.assistant import GeminiAssistant
from .conversation_session import ConversationSession
from .gemini import GeminiClient
from .language import normalize_text
from .recommendation import (
    RecommendationMatch,
    RecommendationService,
    SearchConstraints,
    SearchConstraintsPayload,
)
from .response_types import ChatbotResponse
from .tag_extractor import Preferences, PreferencesPayload, TagExtractor
from .text_generator import TextGenerator


class ChatbotUnavailable(Exception):
    """The assistant could not produce a valid reply for this turn."""


class ChatbotService:
    SESSION_KEY: ClassVar[str] = ConversationSession.STATE_KEY
    SHOWN_KEY: ClassVar[str] = ConversationSession.SHOWN_KEY
    SEARCH_KEY: ClassVar[str] = ConversationSession.SEARCH_KEY
    LAST_RESULT_EMPTY_KEY: ClassVar[str] = ConversationSession.LAST_RESULT_EMPTY_KEY
    GEMINI_CALLS_KEY: ClassVar[str] = ConversationSession.GEMINI_CALLS_KEY
    UNAVAILABLE_MESSAGE: ClassVar[str] = (
        'Maaf, Chatbot belum tersedia sekarang ini. Silakan coba lagi nanti.'
    )
    RESET_PHRASES: ClassVar[set[str]] = {'reset', 'mulai lagi', 'mulai dari awal'}

    def __init__(
        self,
        session: SessionBase,
        *,
        gemini_client: TextGenerator | None = None,
    ) -> None:
        self.session: SessionBase = session
        self._state: ConversationSession = ConversationSession(session)
        self.tag_extractor: TagExtractor = TagExtractor()
        catalog_tags = (
            MenuTag.objects.filter(
                menu_items__is_active=True,
                menu_items__category__is_active=True,
            )
            .values_list('name', 'display_name')
            .distinct()
        )
        catalog_aliases = (
            MenuTag.objects.filter(
                aliases__is_active=True,
                menu_items__is_active=True,
                menu_items__category__is_active=True,
            )
            .values_list('name', 'aliases__phrase')
            .distinct()
        )
        self.tag_extractor.configure_catalog_tags(catalog_tags, catalog_aliases)
        self.recommender: RecommendationService = RecommendationService()
        self.gemini_client: TextGenerator = (
            GeminiClient() if gemini_client is None else gemini_client
        )
        self.assistant: GeminiAssistant = GeminiAssistant(
            self.gemini_client,
            self.recommender,
            self.tag_extractor,
            session=self.session,
        )

    def reset(self) -> None:
        self._state.reset()

    def _consume_gemini_budget(self) -> bool:
        return self._state.consume_gemini_call(settings.GEMINI_MAX_CALLS_PER_SESSION)

    def _preferences(self) -> Preferences:
        return self._state.load_preferences()

    def _save_preferences(self, preferences: Preferences, state: str) -> None:
        self._state.save_preferences(preferences, state)

    def _search_constraints(self) -> SearchConstraints:
        return self._state.load_constraints()

    def _response_preferences(
        self,
        preferences: Preferences,
        state: str,
    ) -> PreferencesPayload:
        response = preferences.to_dict(state=state)
        response['max_price'] = None
        response['category'] = None

        return response

    def _dialog_state(self) -> dict[str, object]:
        state = self.session.get(self.SESSION_KEY, {})

        return state if isinstance(state, dict) else {}

    def _gemini_context(self) -> dict[str, object]:
        state = self._dialog_state()

        return {
            'preferences': {
                'tags': sorted(state.get('tags', [])),
                'mood_tags': sorted(state.get('mood_tags', [])),
                'excluded_tags': sorted(state.get('excluded_tags', [])),
                'soft_excluded_tags': sorted(state.get('soft_excluded_tags', [])),
                'moods': sorted(state.get('moods', [])),
                'prefer_affordable': state.get('prefer_affordable', False),
            },
            'active_search': self._search_constraints().to_dict(),
            'shown_ids': list(self.session.get(self.SHOWN_KEY, [])),
            'last_recommendation_ids': list(state.get('last_recommendations', [])),
            'last_question': state.get(
                'last_question',
                self.session.get('last_question'),
            ),
            'recent_turn': {
                'customer': self.session.get('recommendation_last_message', ''),
                'assistant': self.session.get('recommendation_last_response', ''),
            },
        }

    def _gemini_reply(self, message: str) -> ChatbotResponse | None:
        context = self._gemini_context()
        response, _tool_results = self.assistant.respond(
            message or 'Mulai percakapan dan bantu pelanggan memilih menu.',
            context,
            self._consume_gemini_budget,
        )

        if response is None:
            return None

        matches = cast(list[RecommendationMatch], context.get('last_tool_matches', []))
        constraints_data = context.get('last_tool_constraints')
        state = self._dialog_state().get(
            'state',
            'COLLECTING_PREFERENCES',
        )
        self.session['recommendation_last_message'] = message[:500]
        self.session['recommendation_last_response'] = response[:1200]

        if constraints_data:
            constraints = SearchConstraints.from_dict(
                cast(SearchConstraintsPayload, constraints_data)
            )
            preferences = self._preferences()
            preferences.tags.update(constraints.required_tags)
            preferences.tags.difference_update(constraints.excluded_tags)
            preferences.excluded_tags.update(constraints.excluded_tags)
            preferences.max_price = constraints.max_price
            preferences.category = constraints.category
            if context.get('prefer_affordable') or self.tag_extractor.price_parser.prefers_affordable(
                message
            ):
                preferences.prefer_affordable = True
            self.session[self.SEARCH_KEY] = constraints.to_dict()
            self.session['recommendation_required_tags'] = sorted(
                constraints.required_tags
            )
            ids = [match.item.id for match in matches]
            self.session[self.SHOWN_KEY] = ids
            self.session['last_recommendations'] = ids
            self.session['shown_recommendation_ids'] = ids
            self.session[self.LAST_RESULT_EMPTY_KEY] = False
            state = 'RECOMMENDING'
            self._save_preferences(preferences, state)
            self.session.modified = True

            return {
                'message': response,
                'state': state,
                'preferences': self._response_preferences(preferences, state),
                'active_search': constraints.to_dict(),
                'recommendations': matches,
                'quick_replies': [
                    {
                        'label': '🔄 Cari Menu Lain',
                        'value': 'Cari menu lain',
                        'action': 'more',
                    },
                    {
                        'label': '🔄 Mulai Lagi',
                        'value': 'mulai lagi',
                        'action': 'reset',
                    },
                ],
            }

        self.session.modified = True

        return {
            'message': response,
            'state': state,
            'preferences': self._response_preferences(self._preferences(), state),
            'recommendations': [],
            'quick_replies': [],
        }

    def reply(
        self,
        message: str,
        more: bool = False,
        action: str | None = None,
    ) -> ChatbotResponse:
        """Return one AI reply or raise ChatbotUnavailable.

        ``more`` is retained for the existing HTTP contract; the AI now decides
        what "more" means from the message text.
        """

        del more  # The AI sees the message; there is no local "more" path anymore.
        self._state.expire_dialog()
        normalized = normalize_text(message)

        if action == 'reset' or normalized in self.RESET_PHRASES:
            self.reset()
            message = ''

        result = self._gemini_reply(message)

        if result is None:
            raise ChatbotUnavailable(self.UNAVAILABLE_MESSAGE)

        return result
