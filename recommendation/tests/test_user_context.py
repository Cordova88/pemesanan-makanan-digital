"""Phase 3 emotion boundaries, physical negation and temporary context."""

import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase

from menu.models import Category, MenuItem, MenuTag
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.mood_extractor import MoodExtractor, UserContext
from ..services.mood_resolver import MoodResolver
from ..services.response_types import ChatbotResponse
from ..services.text_generator import TextGenerator


class LocalContextGenerator(TextGenerator):
    def __init__(self) -> None:
        self.calls: int = 0

    def generate(self, prompt: str) -> str | None:
        self.calls += 1

        raise AssertionError("Context responses should remain local")


class UserContextExtractionTests(SimpleTestCase):
    def setUp(self) -> None:
        self.extractor = MoodExtractor()

    def test_emotion_physical_situation_and_taste_are_separate(self) -> None:
        context = self.extractor.extract_context("Aku sedih, capek habis kuliah, mau yang manis")
        self.assertEqual(context.emotions, frozenset({"sad"}))
        self.assertEqual(context.physical, frozenset({"tired"}))
        self.assertEqual(context.situations, frozenset({"studying"}))
        self.assertNotIn("sweet", context.emotions | context.physical | context.situations)

    def test_emotion_vocabulary_and_negation(self) -> None:
        for text, expected in (
            ("aku sedih", "sad"),
            ("lagi happy banget", "happy"),
            ("aku stres", "stressed"),
            ("aku marah", "frustrated"),
            ("aku kecewa", "disappointed"),
        ):
            self.assertIn(expected, self.extractor.extract_context(text).emotions)

        for text in (
            "aku tidak sedih",
            "aku tidak sedang senang",
            "aku tidak lagi merasa terlalu sedih",
        ):
            self.assertFalse(self.extractor.extract_context(text).emotions)

    def test_negated_physical_and_temporal_correction(self) -> None:
        for text, kind in (
            ("sudah tidak haus", "thirsty"),
            ("tidak capek habis kerja", "tired"),
            ("tidak terlalu lapar", "hungry"),
        ):
            context = self.extractor.extract_context(text)
            self.assertNotIn(kind, context.physical)
            self.assertIn(kind, context.cleared_physical)

        self.assertEqual(
            self.extractor.extract_context("tadi haus, sekarang capek").physical,
            frozenset({"tired"}),
        )
        self.assertIn(
            "tired",
            self.extractor.extract_context("tidak capek, sekarang ingin nasi").cleared_physical,
        )

    def test_food_effect_description_is_not_user_emotion_or_condition(self) -> None:
        self.assertFalse(self.extractor.extract_context("ingin makanan yang bikin happy").emotions)
        self.assertFalse(self.extractor.extract_context("makanan yang bikin haus").physical)

    def test_work_study_and_company_do_not_imply_emotion_or_hunger(self) -> None:
        for text, kind in (
            ("lagi kerja", "working"),
            ("lagi belajar", "studying"),
            ("bareng teman", "with_friends"),
        ):
            context = self.extractor.extract_context(text)
            self.assertIn(kind, context.situations)
            self.assertFalse(context.physical | context.emotions)

        self.assertNotIn("tired", self.extractor.extract("habis kerja"))

    def test_emotion_does_not_resolve_to_food_and_explicit_tags_override_inference(self) -> None:
        resolver = MoodResolver()
        self.assertEqual(resolver.resolve({"low_mood", "sad", "happy", "frustrated"}), set())
        self.assertNotIn("cold", resolver.resolve({"hot_thirsty"}, explicit_tags={"warm"}))
        self.assertFalse(
            {"drink", "cold", "refreshing"}
            & resolver.resolve({"hot_thirsty"}, explicit_tags={"rice"})
        )

    def test_context_collections_are_independent_and_safe_to_share(self) -> None:
        source = {"sad"}
        context = UserContext(emotions=source)
        source.clear()
        self.assertEqual(context.emotions, frozenset({"sad"}))
        self.assertFalse(UserContext().has_context)


class ContextSessionTests(SimpleTestCase):
    def setUp(self) -> None:
        self.session = SessionStore()
        self.state = ConversationSession(self.session)

    def test_context_expires_after_two_followup_turns(self) -> None:
        self.state.advance_context(UserContext(physical={"tired"}), explicit_food=False)
        self.assertFalse(self.state.advance_context(UserContext(), explicit_food=False))
        self.assertTrue(self.state.advance_context(UserContext(), explicit_food=False))
        self.assertNotIn(self.state.TEMP_CONTEXT_KEY, self.session)

    def test_time_expiry_and_emotion_data_minimization(self) -> None:
        with patch("recommendation.services.conversation_session.time", return_value=1000):
            self.state.advance_context(
                UserContext(emotions={"sad"}, physical={"thirsty"}), explicit_food=False
            )

        stored = self.session[self.state.TEMP_CONTEXT_KEY]
        self.assertEqual(set(stored), {"physical", "situations", "remaining_turns", "expires_at"})
        self.assertNotIn("sad", json.dumps(stored))

        with patch("recommendation.services.conversation_session.time", return_value=1301):
            self.assertTrue(self.state.advance_context(UserContext(), explicit_food=False))

        self.assertNotIn(self.state.TEMP_CONTEXT_KEY, self.session)

    def test_explicit_food_replaces_old_physical_and_reset_removes_only_context_namespace(
        self,
    ) -> None:
        self.state.advance_context(UserContext(physical={"thirsty"}), explicit_food=False)
        self.assertTrue(self.state.advance_context(UserContext(), explicit_food=True))
        self.assertNotIn(self.state.TEMP_CONTEXT_KEY, self.session)
        self.state.advance_context(UserContext(situations={"studying"}), explicit_food=False)
        self.session["cart"] = ["sentinel"]
        self.state.reset()
        self.assertNotIn(self.state.TEMP_CONTEXT_KEY, self.session)
        self.assertEqual(self.session["cart"], ["sentinel"])


class ContextIntegrationTests(TestCase):
    def setUp(self) -> None:
        food = Category.objects.create(name="Makanan")
        drink = Category.objects.create(name="Minuman")
        self.tags = {
            name: MenuTag.objects.create(name=name)
            for name in (
                "rice",
                "filling",
                "heavy_meal",
                "comfort_food",
                "sweet",
                "drink",
                "cold",
                "refreshing",
                "warm",
            )
        }
        self.items = {}

        for name, category, price, tags in (
            ("Nasi Hangat", food, 18000, ("rice", "filling", "heavy_meal", "comfort_food", "warm")),
            ("Kue Manis", food, 12000, ("sweet",)),
            ("Teh Dingin", drink, 7000, ("drink", "cold", "refreshing")),
            ("Teh Hangat", drink, 8000, ("drink", "warm")),
        ):
            item = MenuItem.objects.create(name=name, category=category, price=Decimal(price))
            item.tags.add(*(self.tags[tag] for tag in tags))
            self.items[name] = item

        self.session = SessionStore()
        self.generator = LocalContextGenerator()

    def reply(self, text: str, action: str | None = None) -> ChatbotResponse:
        return ChatbotService(self.session, gemini_client=self.generator).reply(text, action=action)

    def test_sad_happy_stressed_frustrated_and_disappointed_never_force_food(self) -> None:
        for text in ("Aku sedih.", "Lagi happy banget.", "Aku stres.", "Aku marah.", "Aku kecewa."):
            with self.subTest(text=text):
                result = self.reply(text)
                self.assertFalse(result["recommendations"])
                self.assertFalse(result["preferences"]["tags"])
                self.assertFalse(result["preferences"]["mood_tags"])
                self.assertNotIn("low_mood", result["preferences"]["moods"])
                self.assertNotIn("manis", result["message"].casefold())

        self.assertEqual(self.generator.calls, 0)

    def test_sadness_with_explicit_sweet_and_happiness_with_rice_respect_actual_preference(
        self,
    ) -> None:
        result = self.reply("Aku sedih, ingin yang manis")
        self.assertEqual([match.item.name for match in result["recommendations"]], ["Kue Manis"])
        self.assertIn("membaik", result["message"])
        result = self.reply("Aku lagi happy banget, ingin nasi")
        self.assertEqual([match.item.name for match in result["recommendations"]], ["Nasi Hangat"])
        self.assertNotIn("sweet", self.session["recommendation_state"]["mood_tags"])

    def test_stressed_and_hungry_or_studying_offers_choices_without_claiming_cure(self) -> None:
        hungry = self.reply("Aku stres dan lapar")
        self.assertTrue(hungry["recommendations"])
        self.assertIn("hungry", self.session[ConversationSession.TEMP_CONTEXT_KEY]["physical"])
        self.assertNotIn("sweet", self.session["recommendation_state"]["mood_tags"])
        self.assertNotRegex(
            hungry["message"].casefold(), r"menyembuhkan|terbukti|mengobati|tinggi protein"
        )

        for text in ("Aku lagi belajar", "Bareng teman"):
            self.session = SessionStore()
            result = self.reply(text)
            self.assertFalse(result["recommendations"])
            self.assertFalse(result["preferences"]["mood_tags"])
            self.assertNotRegex(
                result["message"].casefold(), r"menyembuhkan|terbukti|mengobati|tinggi protein"
            )

    def test_tired_and_explicit_filling_context_is_supported_without_provider(self) -> None:
        result = self.reply("Aku capek habis kuliah, ingin yang mengenyangkan")
        self.assertTrue(result["recommendations"])
        self.assertIn("tired", result["preferences"]["moods"])
        self.assertIn("studying", self.session[ConversationSession.TEMP_CONTEXT_KEY]["situations"])
        self.assertEqual(self.generator.calls, 0)

    def test_thirst_then_explicit_rice_clears_old_drink_inference(self) -> None:
        first = self.reply("Aku haus")
        self.assertIn("hot_thirsty", first["preferences"]["moods"])
        result = self.reply("Sekarang mau nasi")
        self.assertEqual([match.item.name for match in result["recommendations"]], ["Nasi Hangat"])
        self.assertFalse(result["preferences"]["mood_tags"])
        self.assertNotIn("hot_thirsty", result["preferences"]["moods"])

    def test_negated_thirst_and_tired_conditions_clear_previous_inference(self) -> None:
        for positive, correction in (
            ("Aku haus", "sudah tidak haus"),
            ("aku capek", "tidak capek sekarang ingin nasi"),
        ):
            self.session = SessionStore()
            self.reply(positive)
            result = self.reply(correction)
            self.assertFalse(result["preferences"]["moods"])
            self.assertFalse(result["preferences"]["mood_tags"])

    def test_explicit_warm_preference_outweighs_thirst_inference(self) -> None:
        result = self.reply("Aku haus, mau yang hangat")
        self.assertTrue(result["recommendations"])
        self.assertTrue(
            all(
                "warm" in {tag.name for tag in match.item.tags.all()}
                for match in result["recommendations"]
            )
        )
        self.assertNotIn("dingin", result["message"].casefold())
        self.assertFalse(any("Dingin" in tag for tag in result["preferences"]["mood_tags"]))

    def test_inference_expires_after_two_turns_and_after_time_limit(self) -> None:
        with patch("recommendation.services.conversation_session.time", return_value=1000):
            self.reply("Aku capek")
            self.reply("xyz")
            result = self.reply("xyz")

        self.assertFalse(result["preferences"]["moods"])

        with patch("recommendation.services.conversation_session.time", return_value=1000):
            self.reply("Aku haus")

        with patch("recommendation.services.conversation_session.time", return_value=1301):
            result = self.reply("xyz")

        self.assertFalse(result["preferences"]["moods"])

    def test_context_change_and_emotion_does_not_remove_active_budget(self) -> None:
        self.reply("nasi maksimal 20 ribu")
        result = self.reply("Aku capek habis kerja")
        self.assertEqual(result["active_search"]["max_price"], 20000)
        result = self.reply("Aku sedih")
        self.assertEqual(result["active_search"]["max_price"], 20000)
        self.assertTrue(all(match.item.price <= 20000 for match in result["recommendations"]))

    def test_emotion_with_nonfood_and_exact_menu_keeps_entity_identity(self) -> None:
        result = self.reply("Aku sedih, ingin motor")
        self.assertIn("motor", result["message"])
        self.assertFalse(result["recommendations"])
        result = self.reply("Aku senang, ingin nasi hangat")
        self.assertEqual([match.item.name for match in result["recommendations"]], ["Nasi Hangat"])

    def test_emotion_plus_more_does_not_swallow_rejection_or_replay_shown_ids(self) -> None:
        first = self.reply("nasi maksimal 20 ribu")
        ids = {match.item.pk for match in first["recommendations"]}
        result = self.reply("Aku sedih, cari yang lain")
        self.assertFalse(ids & {match.item.pk for match in result["recommendations"]})
        self.assertIn("rice", self.session["recommendation_state"]["tags"])

    def test_reset_and_sessions_do_not_leak_temporary_context_or_emotions(self) -> None:
        self.reply("Aku sedih dan capek")
        self.assertNotIn("sad", json.dumps(dict(self.session)))
        fresh = ChatbotService(SessionStore(), gemini_client=LocalContextGenerator())
        self.assertFalse(fresh.reply("")["preferences"]["moods"])
        self.reply("mulai lagi", action="reset")
        self.assertNotIn(ConversationSession.TEMP_CONTEXT_KEY, self.session)

    def test_wire_contract_keeps_context_internal_and_no_order_side_effect(self) -> None:
        with patch(
            "recommendation.services.gemini.GeminiClient.generate",
            side_effect=AssertionError("Context stays local"),
        ):
            response = self.client.post(
                "/api/recommendation/chat/",
                {"message": "Aku sedih"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(
            {"message", "state", "preferences", "recommendations", "quick_replies"}.issubset(body)
        )
        self.assertNotIn("emotions", body)
        self.assertNotIn("physical", body)
        from orders.models import Order

        self.assertEqual(Order.objects.count(), 0)
