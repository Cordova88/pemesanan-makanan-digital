"""Typing schemas for existing internal chatbot dictionaries (no new wire fields)."""

from typing import NotRequired, TypedDict

from .recommendation import RecommendationMatch, SearchConstraintsPayload
from .tag_extractor import PreferencesPayload


class QuickReply(TypedDict):
    label: str
    value: str
    action: NotRequired[str]


class ChatbotResponse(TypedDict):
    message: str
    state: str
    preferences: PreferencesPayload
    recommendations: list[RecommendationMatch]
    quick_replies: list[QuickReply]
    active_search: NotRequired[SearchConstraintsPayload]
