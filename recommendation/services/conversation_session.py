"""Chatbot-only session state and its lifecycle.

The session stores just enough context for the AI: preferences, the last search,
shown recommendations, the previous exchange, and provider-call accounting.
"""

from time import time
from typing import ClassVar

from django.conf import settings
from django.contrib.sessions.backends.base import SessionBase

from .recommendation import SearchConstraints
from .tag_extractor import Preferences, PreferencesPayload


class ConversationStatePayload(PreferencesPayload, total=False):
    last_question: str | None
    last_recommendations: list[int]
    shown_recommendation_ids: list[int]


class ConversationSession:
    STATE_KEY: ClassVar[str] = 'recommendation_state'
    SHOWN_KEY: ClassVar[str] = 'recommendation_shown'
    SEARCH_KEY: ClassVar[str] = 'recommendation_search'
    LAST_RESULT_EMPTY_KEY: ClassVar[str] = 'recommendation_last_result_empty'
    GEMINI_CALLS_KEY: ClassVar[str] = 'gemini_calls'
    LAST_ACTIVE_KEY: ClassVar[str] = 'recommendation_last_active'
    REVISION_KEY: ClassVar[str] = 'recommendation_revision'
    OWNED_KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            STATE_KEY,
            SHOWN_KEY,
            SEARCH_KEY,
            LAST_RESULT_EMPTY_KEY,
            GEMINI_CALLS_KEY,
            LAST_ACTIVE_KEY,
            REVISION_KEY,
            'last_question',
            'last_recommendations',
            'shown_recommendation_ids',
            'recommendation_required_tags',
            'recommendation_last_message',
            'recommendation_last_response',
            'recommendation_excluded_item_ids',
        }
    )

    def __init__(self, session: SessionBase) -> None:
        self._session: SessionBase = session

    @staticmethod
    def _owned_key(key: str) -> bool:
        return key in ConversationSession.OWNED_KEYS

    def load_state(self) -> ConversationStatePayload:
        stored = self._session.get(self.STATE_KEY, {})

        return stored if isinstance(stored, dict) else {}

    def load_preferences(self) -> Preferences:
        return Preferences.from_dict(self.load_state())

    def save_preferences(self, preferences: Preferences, state: str) -> None:
        payload: ConversationStatePayload = {
            **preferences.to_dict(state=state),
            'max_price': None,
            'category': None,
            'last_question': self._session.get('last_question'),
            'last_recommendations': self._session.get('last_recommendations', []),
            'shown_recommendation_ids': self._session.get(
                'shown_recommendation_ids', []
            ),
        }
        self._session[self.STATE_KEY] = payload
        self._session.modified = True

    def load_constraints(self) -> SearchConstraints:
        stored = self._session.get(self.SEARCH_KEY)

        if isinstance(stored, dict):
            try:
                return SearchConstraints.from_dict(stored)
            except (TypeError, ValueError):
                pass

        preferences = self.load_preferences()

        return SearchConstraints(
            required_tags=frozenset(
                self._session.get('recommendation_required_tags', [])
            ),
            category=preferences.category,
            max_price=preferences.max_price,
            moods=frozenset(preferences.moods),
        )

    def consume_gemini_call(self, maximum: int) -> bool:
        maximum = max(0, int(maximum))
        calls = self._session.get(self.GEMINI_CALLS_KEY, 0)
        calls = calls if type(calls) is int and calls >= 0 else 0

        if calls >= maximum:
            return False

        self._session[self.GEMINI_CALLS_KEY] = calls + 1
        self._session.modified = True

        return True

    def expire_dialog(self, *, touch: bool = True) -> None:
        now = int(time())
        previous = self._session.get(self.LAST_ACTIVE_KEY)
        lifetime = getattr(settings, 'CHATBOT_DIALOG_IDLE_SECONDS', 1800)

        if type(previous) is int and now - previous >= lifetime:
            self.reset()

        if touch:
            self._session[self.LAST_ACTIVE_KEY] = now

    def reset(self) -> None:
        for key in list(self._session.keys()):
            if isinstance(key, str) and key.startswith('recommendation_'):
                if key != self.REVISION_KEY:
                    self._session.pop(key, None)

        for key in ('last_question', 'last_recommendations', 'shown_recommendation_ids'):
            self._session.pop(key, None)

        self._session.modified = True
