"""Preference delta and session persistence regression contracts."""

import json

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase

from ..services.conversation_interpreter import ConversationInterpretation, PreferenceOperation
from ..services.conversation_session import ConversationSession
from ..services.mood_resolver import MoodResolver
from ..services.recommendation import SearchConstraints
from ..services.tag_extractor import Preferences


class PreferenceDeltaTests(SimpleTestCase):
    def test_add_remove_soft_remove_and_replace_preserve_unrelated_preferences(self) -> None:
        preferences = Preferences(
            tags={"rice"}, excluded_tags={"chicken"}, soft_excluded_tags={"spicy"}
        )
        preferences.apply_interpretation(
            ConversationInterpretation(
                "RECOMMEND",
                operations=[
                    PreferenceOperation("ADD", ("chicken", "spicy")),
                    PreferenceOperation("REMOVE", ("spicy",)),
                    PreferenceOperation("SOFT_REMOVE", ("chicken",)),
                    PreferenceOperation("REPLACE", ("fish",), ("chicken",)),
                ],
            ),
            MoodResolver(),
        )
        self.assertEqual(preferences.tags, {"rice", "fish"})
        self.assertEqual(preferences.excluded_tags, {"spicy"})
        self.assertEqual(preferences.soft_excluded_tags, set())

    def test_clear_then_add_and_unknown_operation_keep_original_order(self) -> None:
        preferences = Preferences(
            tags={"rice"}, max_price=10000, moods={"tired"}, prefer_affordable=True
        )
        preferences.apply_interpretation(
            ConversationInterpretation(
                "RECOMMEND",
                operations=[
                    PreferenceOperation("CLEAR"),
                    PreferenceOperation("ADD", ("fish",)),
                    PreferenceOperation("UNRECOGNIZED", ("spicy",)),
                ],
            ),
            MoodResolver(),
        )
        self.assertEqual(preferences.tags, {"fish"})
        self.assertEqual(preferences.moods, set())
        self.assertEqual(preferences.mood_tags, set())
        self.assertIsNone(preferences.max_price)
        self.assertFalse(preferences.prefer_affordable)

    def test_mood_clear_new_mood_and_budget_flags_keep_existing_precedence(self) -> None:
        preferences = Preferences(
            tags={"rice"}, max_price=20000, moods={"tired"}, prefer_affordable=True
        )
        preferences.apply_interpretation(
            ConversationInterpretation(
                "UPDATE_PREFERENCES",
                moods={"hot_thirsty"},
                clear_moods=True,
                max_price=15000,
                clear_max_price=True,
                prefer_affordable=True,
                clear_prefer_affordable=True,
                category="Minuman",
            ),
            MoodResolver(),
        )
        self.assertEqual(preferences.moods, {"hot_thirsty"})
        self.assertEqual(preferences.mood_tags, {"cold", "refreshing", "drink"})
        self.assertEqual(preferences.tags, {"rice"})
        self.assertIsNone(preferences.max_price)
        self.assertFalse(preferences.prefer_affordable)
        self.assertEqual(preferences.category, "Minuman")

    def test_omitted_context_keeps_mood_and_affordable_but_clears_transient_filters(self) -> None:
        preferences = Preferences(
            tags={"rice"},
            excluded_tags={"rice"},
            max_price=20000,
            category="Makanan",
            moods={"tired"},
            prefer_affordable=True,
        )
        preferences.apply_interpretation(ConversationInterpretation("RECOMMEND"), MoodResolver())
        self.assertEqual(preferences.tags, set())
        self.assertEqual(preferences.moods, {"tired"})
        self.assertEqual(preferences.mood_tags, {"filling", "heavy_meal", "comfort_food"})
        self.assertTrue(preferences.prefer_affordable)
        self.assertIsNone(preferences.max_price)
        self.assertIsNone(preferences.category)


class ConversationSessionTests(SimpleTestCase):
    def setUp(self) -> None:
        self.session: SessionStore = SessionStore()
        self.state: ConversationSession = ConversationSession(self.session)

    def test_preferences_and_active_search_stay_separate_and_json_serializable(self) -> None:
        preferences = Preferences(tags={"chicken"}, max_price=20000, category="Makanan")
        constraints = SearchConstraints(frozenset({"fish"}), max_price=15000, category="Makanan")
        self.state.set_last_question("base")
        self.state.record_recommendations([10], shown_ids=[9, 10])
        self.state.save_search(constraints, update_required_tags=True)
        self.state.save_preferences(preferences, "ASKING_FOLLOWUP", "base")
        payload = self.state.load_state()
        self.assertIsNone(payload["max_price"])
        self.assertIsNone(payload["category"])
        self.assertEqual(payload["tags"], ["chicken"])
        self.assertEqual(payload["last_question"], "base")
        self.assertEqual(payload["last_recommendations"], [10])
        self.assertEqual(payload["shown_recommendation_ids"], [9, 10])
        self.assertEqual(payload["follow_up"], "base")
        self.assertEqual(self.state.load_constraints(), constraints)
        self.assertEqual(self.session["recommendation_required_tags"], ["fish"])
        restored = SessionStore()
        restored.update(json.loads(json.dumps(dict(self.session))))
        self.assertEqual(ConversationSession(restored).load_constraints(), constraints)
        self.assertEqual(ConversationSession(restored).load_preferences().tags, {"chicken"})
        self.assertTrue(self.session.modified)

    def test_legacy_constraints_fallback_and_new_filter_precedence(self) -> None:
        self.session["recommendation_state"] = Preferences(
            max_price=20000, category="Makanan", moods={"tired"}
        ).to_dict()
        self.session["recommendation_required_tags"] = ["rice"]
        self.assertEqual(
            self.state.load_constraints(),
            SearchConstraints(
                frozenset({"rice"}),
                category="Makanan",
                max_price=20000,
                moods=frozenset({"tired"}),
            ),
        )
        constraints = SearchConstraints(frozenset({"fish"}), max_price=12000)
        self.state.save_search(constraints)
        self.assertEqual(self.state.load_constraints(), constraints)
        self.assertEqual(self.session["recommendation_required_tags"], ["rice"])

    def test_empty_catalog_result_keeps_shown_history_and_clears_last_result(self) -> None:
        self.state.record_recommendations([2], shown_ids=[1, 2])
        self.state.record_recommendations([])
        self.assertEqual(self.state.get_last_recommendation_ids(), [])
        self.assertEqual(self.state.get_shown_ids(), [1, 2])
        self.assertEqual(self.state.get_rejected_ids(), [])
        self.assertTrue(self.state.last_result_empty())
        self.state.record_recommendations([], shown_ids=[])
        self.assertEqual(self.state.get_shown_ids(), [])
        self.assertEqual(self.state.get_rejected_ids(), [])

    def test_rejection_falls_back_to_last_ids_when_shown_history_is_empty(self) -> None:
        ids = [1, 2]
        self.state.record_recommendations(ids, shown_ids=ids)
        ids.clear()
        self.assertEqual(self.state.get_last_recommendation_ids(), [1, 2])
        self.assertIsNot(self.state.get_last_recommendation_ids(), self.state.get_shown_ids())
        self.state.record_recommendations([], shown_ids=[])
        self.state.record_recommendations([3])
        self.assertEqual(self.state.get_rejected_ids(), [3])
        self.assertFalse(self.state.last_result_empty())

    def test_call_limit_counts_only_accepted_calls_and_reset_preserves_other_session_data(
        self,
    ) -> None:
        self.session["cart"] = [{"menu_item_id": 4}]
        self.session["recommendation_context"] = {"legacy": True}
        self.state.set_last_question("base")
        self.state.save_search(SearchConstraints(frozenset({"rice"})), update_required_tags=True)
        self.state.save_preferences(Preferences(tags={"rice"}), "RECOMMENDING")
        self.state.record_recommendations([4], shown_ids=[4])
        self.assertFalse(self.state.consume_gemini_call(-1))
        self.assertTrue(self.state.consume_gemini_call(1))
        self.assertFalse(self.state.consume_gemini_call(1))
        self.assertEqual(self.session["gemini_calls"], 1)
        self.state.reset()
        self.assertEqual(dict(self.session), {"cart": [{"menu_item_id": 4}], "gemini_calls": 1})
        self.assertTrue(self.session.modified)
        self.assertFalse(self.state.consume_gemini_call(1))
