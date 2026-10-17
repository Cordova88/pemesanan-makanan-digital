from django.conf import settings

from recommendation.services.recommendation import SearchConstraints
from recommendation.services.tag_extractor import Preferences


class ConversationContext:
    """Owns session-backed conversation state and bounded Gemini context."""

    SESSION_KEY = "recommendation_state"
    SHOWN_KEY = "recommendation_shown"
    SEARCH_KEY = "recommendation_search"
    LAST_RESULT_EMPTY_KEY = "recommendation_last_result_empty"
    GEMINI_CALLS_KEY = "gemini_calls"

    def __init__(self, session):
        self.session = session

    def reset(self):
        for key in (
            self.SESSION_KEY,
            self.SHOWN_KEY,
            "recommendation_context",
            "shown_recommendation_ids",
            "last_recommendations",
            "last_question",
            self.GEMINI_CALLS_KEY,
            "recommendation_required_tags",
            self.SEARCH_KEY,
            self.LAST_RESULT_EMPTY_KEY,
            "recommendation_last_message",
            "recommendation_last_response",
        ):
            self.session.pop(key, None)
        self.session.modified = True

    def consume_provider_request(self):
        maximum = max(0, int(settings.GEMINI_MAX_CALLS_PER_SESSION))
        calls = int(self.session.get(self.GEMINI_CALLS_KEY, 0))
        if calls >= maximum:
            return False
        self.session[self.GEMINI_CALLS_KEY] = calls + 1
        self.session.modified = True
        return True

    def preferences(self):
        return Preferences.from_dict(self.session.get(self.SESSION_KEY, {}))

    def search_constraints(self):
        stored = self.session.get(self.SEARCH_KEY)
        if isinstance(stored, dict):
            return SearchConstraints.from_dict(stored)
        preferences = self.preferences()
        return SearchConstraints(
            required_tags=frozenset(
                self.session.get("recommendation_required_tags", [])
            ),
            category=preferences.category,
            max_price=preferences.max_price,
            moods=frozenset(preferences.moods),
        )

    def save_preferences(self, preferences, state, follow_up=None):
        payload = preferences.to_dict(state=state, follow_up=follow_up)
        payload["max_price"] = None
        payload["category"] = None
        payload["last_question"] = self.session.get("last_question")
        payload["last_recommendations"] = self.session.get("last_recommendations", [])
        payload["shown_recommendation_ids"] = self.session.get(
            "shown_recommendation_ids",
            [],
        )
        self.session[self.SESSION_KEY] = payload
        self.session.modified = True

    def has_active_search(self):
        constraints = self.search_constraints()
        return bool(
            constraints.required_tags
            or constraints.excluded_tags
            or constraints.category
            or constraints.max_price is not None
            or constraints.moods
        )

    def gemini_context(self):
        state = self.session.get(self.SESSION_KEY, {})
        return {
            "preferences": {
                "tags": sorted(state.get("tags", [])),
                "mood_tags": sorted(state.get("mood_tags", [])),
                "excluded_tags": sorted(state.get("excluded_tags", [])),
                "soft_excluded_tags": sorted(state.get("soft_excluded_tags", [])),
                "moods": sorted(state.get("moods", [])),
                "prefer_affordable": state.get("prefer_affordable", False),
            },
            "active_search": self.search_constraints().to_dict(),
            "shown_ids": list(self.session.get(self.SHOWN_KEY, [])),
            "last_recommendation_ids": list(
                state.get("last_recommendations", [])
            ),
            "last_question": state.get(
                "last_question",
                self.session.get("last_question"),
            ),
            "recent_turn": {
                "customer": self.session.get("recommendation_last_message", ""),
                "assistant": self.session.get("recommendation_last_response", ""),
            },
        }

    @staticmethod
    def response_preferences(preferences, state, follow_up=None):
        response = preferences.to_dict(state=state, follow_up=follow_up)
        response["max_price"] = None
        response["category"] = None
        return response
