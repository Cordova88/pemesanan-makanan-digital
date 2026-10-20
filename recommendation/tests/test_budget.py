"""Money-role parsing and end-to-end bounds with a synthetic catalog."""
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase

from menu.models import Category, MenuItem, MenuTag
from ..services.budget import BudgetConstraint
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.language import IndonesianPriceParser
from ..services.recommendation import RecommendationService, SearchConstraints
from ..services.response_types import ChatbotResponse
from ..services.tag_extractor import Preferences
from ..services.text_generator import TextGenerator


class NoBudgetProvider(TextGenerator):
    def __init__(self) -> None:
        self.calls: int = 0

    def generate(self, prompt: str) -> str | None:
        self.calls += 1
        raise AssertionError("Deterministic budget handling must not call Gemini")


class BudgetParserTests(SimpleTestCase):
    def setUp(self) -> None:
        self.parser = IndonesianPriceParser()

    def test_nominal_formats_and_decimal_rupiah(self) -> None:
        for text, expected in (("maksimal 20k", "20000"), ("20rb", "20000"), ("20 ribu", "20000"),
                               ("Rp20.000", "20000"), ("20.000", "20000"),
                               ("maksimal Rp20.000,50", "20000.50"), ("maksimal 20,5k", "20500.0"),
                               ("Rp20", "20"), ("20 rupiah", "20"), ("budget 1 juta", "1000000")):
            with self.subTest(text=text):
                self.assertEqual(self.parser.parse(text).constraint.maximum, Decimal(expected))
        # V3.2 Phase 2: approved approximate-price contract replaces the old cap.
        approximate = self.parser.parse('sekitar 20 ribuan')
        self.assertIsNone(approximate.constraint)
        self.assertEqual(approximate.soft_target, Decimal(20000))

    def test_ranges_inherit_units_and_minimum_is_not_maximum(self) -> None:
        for text in ("Budget 20-30 ribu.", "di antara 20 sampai 30 ribu", "20-30rb", "minimal 20rb maksimal 30rb"):
            with self.subTest(text=text):
                constraint = self.parser.parse(text).constraint
                self.assertEqual((constraint.minimum, constraint.maximum), (Decimal(20000), Decimal(30000)))
        self.assertEqual(self.parser.parse("minimal 15rb").constraint.minimum, Decimal(15000))
        self.assertIsNone(self.parser.parse_maximum("minimal 15rb"))

    def test_numeric_correction_uses_latest_nominal(self) -> None:
        self.assertEqual(self.parser.parse_maximum("Gak jadi 20 ribu, maksimal 35 ribu."), 35000)
        self.assertTrue(self.parser.parse("Gak jadi 20 ribu, maksimal 35 ribu.").correction)

    def test_nonmoney_roles_do_not_become_price(self) -> None:
        for text in ("Angka meja aku 20.", "2 orang", "3 porsi", "menu ke 2", "jam 20:30", "rating 4.5", "ukuran 20 cm"):
            with self.subTest(text=text):
                self.assertIsNone(self.parser.parse(text).constraint)
        for text in ("meja aku 2 budget 20k", "jam 20:30 budget 20k", "budget 20k tambah 2 ayam"):
            self.assertEqual(self.parser.parse_maximum(text), 20000)

    def test_total_budget_and_available_funds_are_not_per_item_caps(self) -> None:
        for text in ("50 ribu buat berdua.", "budget 50rb untuk 2 orang", "50rb untuk dua porsi", "2 porsi budget 20k", "budget 20rb per orang"):
            with self.subTest(text=text):
                request = self.parser.parse(text)
                self.assertEqual(request.kind, "total")
                self.assertIsNone(request.constraint)
                self.assertIn("per menu", request.clarification)
        request = self.parser.parse("Aku punya 100 ribu tapi pengen hemat.")
        self.assertEqual(request.kind, "affordable")
        self.assertIsNone(request.constraint)

    def test_invalid_ambiguous_and_removal_are_explicit(self) -> None:
        for text in ("budget -20k", "maksimal Rp-20k", "budget 30-20rb", "maksimal 2000001", "budget 20 juta"):
            with self.subTest(text=text):
                self.assertEqual(self.parser.parse(text).kind, "invalid")
        self.assertEqual(self.parser.parse("budget 20rb atau 30rb").kind, "ambiguous")
        self.assertEqual(self.parser.parse("hapus batas budget").kind, "clear")


class BudgetConstraintTests(SimpleTestCase):
    def test_inclusive_exclusive_decimal_boundaries_and_intersection(self) -> None:
        constraint = BudgetConstraint(Decimal("15000.01"), Decimal("20000.50"), maximum_inclusive=False)
        for value, allowed in (("15000", False), ("15000.01", True), ("20000.49", True), ("20000.50", False)):
            self.assertEqual(constraint.allows(Decimal(value)), allowed)
        combined = constraint.intersect(BudgetConstraint(maximum=Decimal("18000")))
        self.assertEqual(combined.maximum, Decimal("18000"))
        self.assertEqual(combined.minimum, Decimal("15000.01"))

    def test_state_roundtrip_old_constructor_and_budget_hash(self) -> None:
        bounds = BudgetConstraint(Decimal("15000"), Decimal("20000.50"))
        constraints = SearchConstraints(frozenset({"rice"}), max_price=1, budget=bounds)
        payload = constraints.to_dict()
        self.assertIsNone(payload["max_price"])
        self.assertEqual(payload["budget"]["maximum"], "20000.50")
        self.assertEqual(SearchConstraints.from_dict(json.loads(json.dumps(payload))), constraints)
        self.assertEqual(hash(SearchConstraints.from_dict(payload)), hash(constraints))
        self.assertNotIn("budget", SearchConstraints(max_price=20000).to_dict())
        self.assertEqual(BudgetConstraint(maximum=Decimal("20.0")), BudgetConstraint(maximum=Decimal("20")))

    def test_invalid_stored_budget_fails_closed(self) -> None:
        valid = BudgetConstraint(maximum=Decimal(20000)).to_dict()
        for data in ({**valid, "maximum": "NaN"}, {**valid, "maximum": "Infinity"},
                     {**valid, "maximum_inclusive": 1}, {**valid, "minimum": "30000"},
                     {**valid, "maximum": 20000}, {**valid, "extra": "injection"}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                BudgetConstraint.from_dict(data)


class BudgetIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.category = Category.objects.create(name="Makanan")
        self.rice = MenuTag.objects.create(name="rice")
        self.spicy = MenuTag.objects.create(name="spicy")
        self.items: list[MenuItem] = []
        for name, price in (("Porsi Hemat", "12000"), ("Porsi Tengah", "20000.50"),
                            ("Porsi Mahal", "30000"), ("Porsi Batas", "20000.49")):
            item = MenuItem.objects.create(name=name, category=self.category, price=Decimal(price))
            item.tags.add(self.rice)
            self.items.append(item)
        self.session = SessionStore()
        self.generator = NoBudgetProvider()

    def reply(self, text: str) -> ChatbotResponse:
        return ChatbotService(self.session, gemini_client=self.generator).reply(text)

    def assert_clarification_preserves_state(self, text: str) -> ChatbotResponse:
        expected = dict(self.session)
        # An active message refreshes idle expiry, even when budget needs clarification.
        # Cross a second deliberately so the assertion never depends on test speed.
        next_activity = expected[ConversationSession.LAST_ACTIVE_KEY] + 1
        expected[ConversationSession.LAST_ACTIVE_KEY] = next_activity
        expected[ConversationSession.REVISION_KEY] += 1  # committed activity metadata, not a budget mutation
        before = ConversationSession(self.session).projection()
        before_context = json.loads(json.dumps(self.session[ConversationSession.CONTEXTS_KEY]))
        with patch('recommendation.services.conversation_session.time', return_value=next_activity):
            result = self.reply(text)
        self.assertEqual(ConversationSession(self.session).projection(), before)
        after_context = self.session[ConversationSession.CONTEXTS_KEY]
        for key in ('previous', 'overall', 'safety', 'plan'):
            self.assertEqual(after_context[key], before_context[key])
        self.assertEqual(after_context['transition']['action'], 'CLARIFY')
        self.assertEqual(self.session[ConversationSession.REVISION_KEY], expected[ConversationSession.REVISION_KEY])
        self.assertEqual(self.session[ConversationSession.LAST_ACTIVE_KEY], next_activity)
        return result

    def test_range_and_minimum_filter_real_prices_and_score_without_food_tags(self) -> None:
        result = self.reply("budget 20-25 ribu")
        self.assertTrue(result["recommendations"])
        self.assertTrue(all(Decimal(20000) <= match.item.price <= Decimal(25000) for match in result["recommendations"]))
        self.session = SessionStore()
        result = self.reply("minimal 25 ribu")
        self.assertEqual([match.item.pk for match in result["recommendations"]], [self.items[2].pk])
        self.assertEqual(self.generator.calls, 0)

    def test_strict_under_and_inclusive_maximum_have_distinct_boundaries(self) -> None:
        item = MenuItem.objects.create(name="Tepat Batas", category=self.category, price=Decimal(20000))
        result = self.reply("maksimal 20 ribu")
        self.assertIn(item.pk, [match.item.pk for match in result["recommendations"]])
        result = self.reply("di bawah 20 ribu")
        self.assertNotIn(item.pk, [match.item.pk for match in result["recommendations"]])
        self.assertEqual(result["active_search"]["max_price"], 20000)

    def test_correction_changes_only_budget_and_preserves_food_preferences(self) -> None:
        self.reply("nasi maksimal 20 ribu")
        result = self.reply("Gak jadi 20 ribu, maksimal 35 ribu.")
        self.assertEqual(result["active_search"]["max_price"], 35000)
        self.assertEqual(self.session["recommendation_search"]["required_tags"], ["rice"])
        self.assertIn("rice", self.session["recommendation_state"]["tags"])

    def test_new_minimum_replaces_previous_maximum_as_selected_by_user(self) -> None:
        self.reply("maksimal 25 ribu")
        minimum = self.reply("minimal 15 ribu")
        self.assertIsNone(minimum['active_search']['budget']['maximum'])
        result = self.reply("minimal 30 ribu")
        self.assertEqual(result['active_search']['budget']['minimum'], '30000')
        self.assertIsNone(result['active_search']['budget']['maximum'])
        self.assertEqual([match.item.pk for match in result['recommendations']], [self.items[2].pk])

    def test_group_budget_is_stored_without_dividing_into_per_menu_cap(self) -> None:
        self.reply("nasi maksimal 20 ribu")
        result = self.reply("50 ribu buat berdua")
        self.assertFalse(result["recommendations"])
        contexts = self.session[ConversationSession.CONTEXTS_KEY]
        self.assertEqual(contexts['overall']['total_budget'], '50000')
        self.assertEqual(contexts['overall']['person_count'], 2)
        self.assertIsNone(result['active_search']['max_price'])
        self.assertEqual(contexts['previous'][-1]['constraints']['budget']['maximum'], '20000')
        self.assertIn('berbagi', result['message'])
        self.assertEqual(self.generator.calls, 0)

    def test_relative_cheaper_uses_decimal_anchor_and_never_calls_ai(self) -> None:
        self.reply("Ada porsi tengah?")
        result = self.reply("Yang lebih murah")
        self.assertTrue(result["recommendations"])
        self.assertTrue(all(match.item.price < Decimal("20000.50") for match in result["recommendations"]))
        self.assertIn(self.items[3].pk, [match.item.pk for match in result["recommendations"]])
        self.assertEqual(result["active_search"]["budget"]["maximum"], "20000.50")
        self.assertFalse(result["active_search"]["budget"]["maximum_inclusive"])
        self.assertEqual(self.generator.calls, 0)

    def test_relative_more_expensive_preserves_previous_hard_cap(self) -> None:
        self.reply("maksimal 25 ribu")
        self.reply("Ada porsi hemat?")
        result = self.reply("Yang lebih mahal")
        self.assertTrue(result["recommendations"])
        self.assertTrue(all(Decimal(12000) < match.item.price <= Decimal(25000) for match in result["recommendations"]))
        self.assertNotIn(self.items[2].pk, [match.item.pk for match in result["recommendations"]])

    def test_relative_ambiguous_or_missing_anchor_asks_before_changing_bounds(self) -> None:
        self.assertFalse(self.reply("Yang lebih murah")["recommendations"])
        self.reply("nasi maksimal 35 ribu")
        result = self.assert_clarification_preserves_state("Yang lebih murah")
        self.assertIn("menu yang mana", result["message"])
        result = self.reply("lebih murah dari yang kedua")
        self.assertTrue(all(match.item.price < self.items[3].price for match in result["recommendations"]))

    def test_affordable_does_not_clear_cap_and_cheapest_keeps_bounds(self) -> None:
        self.reply("nasi maksimal 25 ribu")
        result = self.reply("Aku punya 100 ribu tapi pengen hemat")
        self.assertEqual(result["active_search"]["max_price"], 25000)
        self.assertTrue(result["preferences"]["prefer_affordable"])
        result = self.reply("lihat menu termurah")
        prices = [match.item.price for match in result["recommendations"]]
        self.assertEqual(prices, sorted(prices))
        self.assertTrue(all(price <= 25000 for price in prices))

    def test_clear_budget_retains_food_and_more_keeps_range(self) -> None:
        self.reply("nasi budget 12-25 ribu")
        more = self.reply("cari menu lain")
        self.assertEqual(more["active_search"]["budget"]["minimum"], "12000")
        cleared = self.reply("hapus batas budget")
        self.assertIsNone(cleared["active_search"]["max_price"])
        self.assertNotIn("budget", cleared["active_search"])
        self.assertIn("rice", self.session["recommendation_state"]["tags"])

    def test_catalog_and_exact_lookup_use_minimum_range_and_fractional_cap(self) -> None:
        catalog = self.reply("Ada nasi budget 20-25 ribu?")
        self.assertTrue(catalog["catalog_question"])
        self.assertTrue(all(20000 <= match.item.price <= 25000 for match in catalog["recommendations"]))
        exact = self.reply("Ada porsi tengah budget 20-25 ribu?")
        self.assertEqual([match.item.pk for match in exact["recommendations"]], [self.items[1].pk])
        result = self.reply("Ada porsi tengah Rp20.000,49?")
        self.assertFalse(result["recommendations"])

    def test_nonmoney_messages_do_not_apply_budget_and_invalid_budget_is_safe(self) -> None:
        for text in ("Angka meja aku 20.", "123123", "budget 30-20rb"):
            with self.subTest(text=text):
                result = self.reply(text)
                self.assertFalse(result["recommendations"])
                self.assertNotIn("recommendation_search", self.session)

    def test_wire_extension_is_optional_and_legacy_price_contract_is_unchanged(self) -> None:
        with patch("recommendation.services.gemini.GeminiClient.generate", side_effect=AssertionError("No AI for budget")):
            response = self.client.post("/api/recommendation/chat/", {"message": "nasi budget 20-25 ribu"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["active_search"]["max_price"], 25000)
        self.assertEqual(body["active_search"]["budget"]["minimum"], "20000")
        self.assertTrue(all(isinstance(item["price"], str) for item in body["recommendations"]))

    def test_empty_result_category_quick_reply_keeps_explicit_budget(self) -> None:
        drinks = Category.objects.create(name="Minuman")
        tag = MenuTag.objects.create(name="drink")
        item = MenuItem.objects.create(name="Teh Hemat", category=drinks, price=Decimal(4000))
        item.tags.add(tag)
        empty = self.reply("makanan maksimal 5 ribu")
        self.assertFalse(empty["recommendations"])
        choice = next(reply for reply in empty["quick_replies"] if reply["label"] == "Minuman sesuai batas")
        result = self.reply(choice["value"])
        self.assertEqual(result["active_search"]["max_price"], 5000)
        self.assertEqual([match.item.pk for match in result["recommendations"]], [item.pk])

    def test_affordable_is_soft_even_when_all_available_items_exceed_legacy_ceiling(self) -> None:
        MenuItem.objects.update(price=Decimal(30000))
        result = self.reply("yang murah")
        self.assertTrue(result["recommendations"])
        self.assertIsNone(result["active_search"]["max_price"])
        self.assertTrue(result["preferences"]["prefer_affordable"])

    def test_ranking_weights_and_candidate_prices_remain_grounded(self) -> None:
        recommender = RecommendationService()
        preferences = Preferences(tags={"rice"})
        legacy = recommender.rank(preferences, constraints=SearchConstraints(max_price=25000))
        bounded = recommender.rank(preferences, constraints=SearchConstraints(budget=BudgetConstraint(maximum=Decimal(25000))))
        self.assertEqual([(m.item.pk, m.score) for m in legacy], [(m.item.pk, m.score) for m in bounded])

    def test_ai_preference_delta_cannot_invent_or_remove_local_price_bounds(self) -> None:
        self.reply("nasi budget 20-25 ribu")
        for invented, clear in ((999999, False), (None, True)):
            data = {
                "intent": "RECOMMEND", "add_tags": ["rice"], "remove_tags": [],
                "excluded_tags": [], "soft_excluded_tags": [], "moods": [],
                "clear_moods": False, "max_price": invented, "prefer_affordable": None,
                "clear_max_price": clear, "clear_prefer_affordable": False,
                "message_is_meaningful": True,
            }
            with self.subTest(clear=clear), patch.object(self.generator, "generate", return_value=json.dumps(data)) as generated:
                result = self.reply("yang tadi terlalu berminyak")
            self.assertEqual(generated.call_count, 1)
            self.assertEqual(result["active_search"]["budget"]["minimum"], "20000")
            self.assertEqual(result["active_search"]["budget"]["maximum"], "25000")
            self.assertTrue(all(20000 <= match.item.price <= 25000 for match in result["recommendations"]))
