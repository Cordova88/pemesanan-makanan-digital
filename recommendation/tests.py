from decimal import Decimal
from io import StringIO
import json
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from menu.models import (
    AddOn,
    Category,
    MenuItem,
    MenuTag,
    MenuTagAlias,
    VariantGroup,
    VariantOption,
)
from orders.models import Order

from .services.language import IndonesianPriceParser, TAG_LABELS, normalize_text
from .services.mood_extractor import MoodExtractor
from .services.recommendation import RecommendationService
from .services.tag_extractor import Preferences, TagExtractor
from .services.conversation_interpreter import (
    ConversationIntent,
    ConversationInterpreter,
)
from .services.chatbot import ChatbotService
from .services.ai.GeminiInterpreter import GeminiInterpreter, validate
from .services.ai.explanations import RecommendationExplanationService
from .services.gemini import GeminiClient


class LanguageRuleTests(SimpleTestCase):
    def setUp(self):
        self.extractor = TagExtractor()
        self.moods = MoodExtractor()
        self.price_parser = IndonesianPriceParser()

    def test_informal_spicy_and_chicken_phrases(self):
        spicy_phrases = (
            "pedas",
            "pedes dong",
            "pengen yang pedes",
            "lagi pengen pedas",
            "sambalnya banyak",
            "yang nampol",
            "yang nendang",
            "yang ada sambalnya",
            "yang bikin melek",
            "pengen rasa yang kuat",
        )
        for phrase in spicy_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn("spicy", self.extractor.extract(phrase).tags)

        for phrase in ("ayam", "mau ayam", "daging ayam", "olahan ayam"):
            with self.subTest(phrase=phrase):
                self.assertIn("chicken", self.extractor.extract(phrase).tags)

    def test_hunger_snack_and_informal_normalization(self):
        self.assertEqual(normalize_text("Gue lg laper bgt"), "aku lagi lapar banget")
        hunger = self.extractor.extract("Gue lagi laper banget, kenyangin aku")
        self.assertTrue({"filling", "heavy_meal"} & hunger.tags)
        self.assertIn("very_hungry", self.moods.extract("laper parah"))
        self.assertIn("snack", self.extractor.extract("Lagi pengen ngemil nih").tags)
        self.assertIn("snack", self.extractor.extract("cari cemilan").tags)
        self.assertIn("light", self.extractor.extract("nggak terlalu lapar").tags)

    def test_refreshing_temperature_and_speed_phrases(self):
        thirst = self.extractor.extract(
            "Lagi gerah, cariin minuman yang dingin dan seger dong"
        )
        self.assertTrue({"drink", "cold", "refreshing"} <= thirst.tags)
        self.assertIn("hot_thirsty", self.moods.extract("lagi kepanasan"))
        self.assertIn("warm", self.extractor.extract("pengen yang anget").tags)
        self.assertIn("quick_meal", self.extractor.extract("lagi buru-buru").tags)
        self.assertIn("quick", self.moods.extract("waktunya mepet, jangan lama"))

    def test_moods_and_confused_phrases(self):
        self.assertIn("tired", self.moods.extract("capek bgt habis kerja"))
        self.assertIn("low_mood", self.moods.extract("lagi bad mood, bete banget"))
        for phrase in (
            "gak tahu",
            "nggak tahu",
            "ga tau",
            "gatau",
            "bingung",
            "terserah kamu",
            "pilihin dong",
            "apa aja deh",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn("confused", self.moods.extract(phrase))
        self.assertNotIn("tofu", self.extractor.extract("gatau").tags)

    def test_explicit_and_soft_negative_preferences(self):
        for phrase in ("jangan pedas", "nggak mau pedas", "tanpa pedas"):
            with self.subTest(phrase=phrase):
                result = self.extractor.extract(phrase)
                self.assertIn("spicy", result.excluded_tags)
                self.assertNotIn("spicy", result.tags)

        no_chicken = self.extractor.extract("aku gak suka ayam")
        self.assertIn("chicken", no_chicken.excluded_tags)
        no_sweet = self.extractor.extract("nggak suka yang manis")
        self.assertIn("sweet", no_sweet.excluded_tags)
        less_heavy = self.extractor.extract("jangan yang terlalu berat")
        self.assertIn("heavy_meal", less_heavy.excluded_tags)
        soft = self.extractor.extract("aku kurang suka pedas")
        self.assertIn("spicy", soft.soft_excluded_tags)

    def test_catalog_terms_include_duck_and_boiled(self):
        result = self.extractor.extract("bebek rebus")
        self.assertEqual(result.tags, {"duck", "boiled"})

    def test_price_parser_understands_rupiah_variants(self):
        examples = {
            "15 ribu": 15000,
            "15rb": 15000,
            "15 rb": 15000,
            "15k": 15000,
            "15000": 15000,
            "maksimal 20 ribu": 20000,
            "di bawah 20k": 20000,
            "ada gak nasi di bawah 20 ribu": 20000,
            "nasi di bawah 150 ribu": 150000,
            "budgetku 20k": 20000,
            "sekitar 20 ribuan": 20000,
        }
        for phrase, expected in examples.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(self.price_parser.parse_maximum(phrase), expected)
        self.assertIsNone(self.price_parser.parse_maximum("mau yang murah dong"))
        self.assertTrue(self.price_parser.prefers_affordable("jangan mahal"))

    def test_existence_question_does_not_treat_gak_as_a_food_exclusion(self):
        preferences = self.extractor.extract("ada gak nasi yang di bawah 20 ribu")

        self.assertIn("rice", preferences.tags)
        self.assertNotIn("rice", preferences.excluded_tags)
        self.assertEqual(preferences.max_price, 20000)

    def test_hidangan_is_a_food_category_constraint(self):
        for phrase in ("makanan manis", "hidangan manis"):
            with self.subTest(phrase=phrase):
                preferences = self.extractor.extract(phrase)
                self.assertEqual(preferences.category, "Makanan")
                self.assertIn("sweet", preferences.tags)


class ConversationInterpreterTests(SimpleTestCase):
    def setUp(self):
        self.interpreter = ConversationInterpreter()

    def test_interprets_add_remove_and_replacement_as_current_message_operations(self):
        add = self.interpreter.interpret("Aku mau pedas")
        self.assertEqual(add.intent, ConversationIntent.RECOMMEND)
        self.assertEqual(add.operations[0].action, "ADD")
        self.assertIn("spicy", add.operations[0].tags)

        remove = self.interpreter.interpret("Eh jangan pedas deh")
        self.assertEqual(remove.intent, ConversationIntent.REMOVE_PREFERENCES)
        self.assertIn("spicy", remove.excluded_tags)

        replace = self.interpreter.interpret("Ganti ayam jadi sapi")
        self.assertEqual(replace.intent, ConversationIntent.REPLACE_PREFERENCES)
        self.assertEqual(replace.operations[0].remove_tags, ("chicken",))
        self.assertEqual(replace.operations[0].tags, ("beef",))
        self.assertFalse(replace.excluded_tags)

        clear = self.interpreter.interpret("Hapus pilihan sebelumnya")
        self.assertEqual(clear.intent, ConversationIntent.RESET)
        self.assertEqual(clear.operations[0].action, "CLEAR")

    def test_unknown_messages_and_bare_numbers_are_not_food_requests(self):
        for message in ("test", "asdfgh", "123123", "haha"):
            with self.subTest(message=message):
                self.assertEqual(
                    self.interpreter.interpret(message).intent,
                    ConversationIntent.UNKNOWN,
                )

    def test_catalog_question_is_distinct_from_a_rice_preference(self):
        question = self.interpreter.interpret("Pilihan nasi apa aja?")
        self.assertEqual(question.intent, ConversationIntent.CATALOG_QUESTION)
        self.assertEqual(question.catalog_tags, {"rice"})

        statement = self.interpreter.interpret("Aku mau pilihan nasi")
        self.assertNotEqual(statement.intent, ConversationIntent.CATALOG_QUESTION)
        self.assertIn("rice", statement.tags)

    def test_no_results_challenge_retries_only_with_catalogued_message_criteria(self):
        message = "Masa nggak ada ikan?"
        without_empty_result = self.interpreter.interpret(
            message,
            last_result_empty=False,
        )
        with_empty_result = self.interpreter.interpret(
            message,
            last_result_empty=True,
        )

        self.assertNotEqual(
            without_empty_result.intent,
            ConversationIntent.RETRY_SEARCH,
        )
        self.assertEqual(with_empty_result.intent, ConversationIntent.RETRY_SEARCH)
        self.assertEqual(with_empty_result.tags, {"fish"})

    def test_recommendation_references_resolve_to_context_positions(self):
        references = (
            ("Yang pertama", "first"),
            ("Yang nomor 2", "second"),
            ("Yang terakhir", "last"),
            ("Menu kedua aja", "second"),
            ("Yang tadi", "last"),
        )
        for message, reference in references:
            with self.subTest(message=message):
                result = self.interpreter.interpret(
                    message,
                    last_recommendations=[11, 22, 33],
                )
                self.assertEqual(
                    result.intent,
                    ConversationIntent.SELECT_RECOMMENDATION,
                )
                self.assertEqual(result.contextual_reference, reference)

        self.assertEqual(
            self.interpreter.interpret("Yang pertama").intent,
            ConversationIntent.UNKNOWN,
        )

    def test_last_question_replaces_only_the_answered_dimension(self):
        result = self.interpreter.interpret("Camilan", last_question="meal_type")
        self.assertEqual(result.intent, ConversationIntent.REPLACE_PREFERENCES)
        self.assertIn("heavy_meal", result.operations[0].remove_tags)
        self.assertIn("snack", result.operations[0].tags)

        no_context = self.interpreter.interpret("Sapi")
        self.assertEqual(no_context.intent, ConversationIntent.RECOMMEND)
        self.assertIn("beef", no_context.tags)

        protein_answer = self.interpreter.interpret(
            "Sapi",
            last_question="protein",
        )
        self.assertEqual(protein_answer.intent, ConversationIntent.REPLACE_PREFERENCES)
        self.assertIn("chicken", protein_answer.operations[0].remove_tags)
        self.assertIn("beef", protein_answer.operations[0].tags)

    def test_mood_cancellation_is_distinct_from_new_mood_and_tags(self):
        result = self.interpreter.interpret(
            "Udah nggak capek, sekarang pengen yang seger"
        )
        self.assertTrue(result.clear_moods)
        self.assertNotIn("tired", result.moods)
        self.assertIn("refreshing", result.tags)


class GeminiInterpreterTests(SimpleTestCase):
    def setUp(self):
        self.client = type(
            "FakeGeminiClient",
            (),
            {"generate": lambda _self, _prompt: None},
        )()
        self.interpreter = GeminiInterpreter(self.client)
        self.valid_response = {
            "intent": ConversationIntent.REPLACE_PREFERENCES,
            "add_tags": ["light_meal"],
            "remove_tags": ["heavy_meal"],
            "excluded_tags": [],
            "soft_excluded_tags": [],
            "moods": [],
            "clear_moods": False,
            "max_price": None,
            "prefer_affordable": None,
            "clear_max_price": False,
            "clear_prefer_affordable": False,
            "message_is_meaningful": True,
        }

    def test_validated_replacement_delta_maps_to_existing_replace_operation(self):
        raw = json.dumps(self.valid_response)
        self.client.generate = lambda _prompt: raw
        result = self.interpreter.interpret(
            "yang tadi terlalu berat, cari yang lebih ringan",
            context={"tags": ["heavy_meal"]},
        )
        self.assertEqual(result.intent, ConversationIntent.REPLACE_PREFERENCES)
        self.assertEqual(result.operations[0].action, "REPLACE")
        self.assertEqual(result.operations[0].remove_tags, ("heavy_meal",))
        self.assertEqual(result.operations[0].tags, ("light_meal",))

    def test_invalid_fields_tags_and_contextual_removal_are_rejected(self):
        allowed_tags = set(self.interpreter.allowed_tags)
        allowed_moods = set(self.interpreter.allowed_moods)
        self.assertTrue(
            validate(self.valid_response, allowed_tags, allowed_moods, {"heavy_meal"})
        )

        invalid_responses = []
        extra = dict(self.valid_response, extra=True)
        invalid_responses.append(extra)
        unknown_tag = dict(self.valid_response, add_tags=["fictional_tag"])
        invalid_responses.append(unknown_tag)
        unknown_removal = dict(self.valid_response, remove_tags=["chicken"])
        invalid_responses.append(unknown_removal)
        malformed_list = dict(self.valid_response, add_tags=[["nested"]])
        invalid_responses.append(malformed_list)
        for response in invalid_responses:
            with self.subTest(response=response):
                self.assertFalse(
                    validate(response, allowed_tags, allowed_moods, {"heavy_meal"})
                )

    def test_malformed_provider_output_returns_none(self):
        self.client.generate = lambda _prompt: "not-json"
        self.assertIsNone(self.interpreter.interpret("yang bikin nagih"))

    def test_gemini_client_returns_none_for_provider_timeout_without_leaking_details(self):
        class FailingModels:
            @staticmethod
            def generate_content(**_kwargs):
                raise TimeoutError("provider timeout")

        client = GeminiClient()
        client.client = type(
            "FakeProvider",
            (),
            {"models": FailingModels()},
        )()
        with self.assertLogs("recommendation.services.gemini", level="WARNING") as logs:
            self.assertIsNone(client.generate("test prompt"))
        self.assertIn("TimeoutError", logs.output[0])
        self.assertNotIn("provider timeout", logs.output[0])

    @override_settings(GEMINI_MODEL="test-gemini-model")
    def test_gemini_client_uses_configured_model_and_logs_success_without_prompt(self):
        calls = []

        class SuccessfulModels:
            @staticmethod
            def generate_content(**kwargs):
                calls.append(kwargs)
                return type("Response", (), {"text": "ok"})()

        client = GeminiClient()
        client.client = type(
            "FakeProvider",
            (),
            {"models": SuccessfulModels()},
        )()

        with self.assertLogs("recommendation.services.gemini", level="INFO") as logs:
            self.assertEqual(client.generate("private prompt"), "ok")

        self.assertEqual(calls[0]["model"], "test-gemini-model")
        self.assertNotIn("private prompt", logs.output[0])
        self.assertIn("response received", logs.output[0])

    def test_gemini_routing_accepts_food_revisions_and_common_typo(self):
        local = ConversationInterpreter()
        examples = (
            "Aku pengen yang bikin nagih tapi nggak bikin eneg",
            "Pedas boleh, tapi jangan terlalu berminya",
        )

        for message in examples:
            with self.subTest(message=message):
                interpretation = local.interpret(message)
                self.assertTrue(
                    ChatbotService._eligible_for_gemini(message, interpretation)
                )

        for message in ("adfgadda", "Siapa presiden?", "Pengen pedas"):
            with self.subTest(message=message):
                interpretation = local.interpret(message)
                self.assertFalse(
                    ChatbotService._eligible_for_gemini(message, interpretation)
                )


class RecommendationExplanationServiceTests(TestCase):
    def test_intro_and_explanations_share_one_grounded_gemini_call(self):
        food = Category.objects.create(name="Makanan")
        rice = MenuTag.objects.create(name="rice", display_name=TAG_LABELS["rice"])
        item = MenuItem.objects.create(
            category=food,
            name="Nasi Goreng",
            price=Decimal("18000"),
        )
        item.tags.add(rice)
        preferences = Preferences(tags={"rice"})
        matches = RecommendationService().rank(preferences)
        calls = []

        class FakeGeminiClient:
            def generate(self, prompt):
                calls.append(prompt)
                return json.dumps(
                    {
                        "intro": "Oke, kita cari yang sesuai pilihanmu ya! 🍚",
                        "explanations": [
                            {
                                "id": item.pk,
                                "text": "Nasi Goreng sesuai dengan Nasi.",
                            }
                        ],
                    }
                )

        intro, explanations = RecommendationExplanationService(
            FakeGeminiClient()
        ).explain_with_intro(
            matches,
            preferences,
            "Aku mau nasi",
            response_kind="recommendation",
        )

        self.assertEqual(len(calls), 1)
        self.assertIn("Aku mau nasi", calls[0])
        self.assertEqual(intro, "Oke, kita cari yang sesuai pilihanmu ya! 🍚")
        self.assertEqual(
            explanations,
            {item.pk: "Nasi Goreng sesuai dengan Nasi."},
        )

    def test_unsupported_intro_is_rejected_without_losing_valid_explanations(self):
        food = Category.objects.create(name="Makanan")
        rice = MenuTag.objects.create(name="rice", display_name=TAG_LABELS["rice"])
        item = MenuItem.objects.create(
            category=food,
            name="Nasi Goreng",
            price=Decimal("18000"),
        )
        item.tags.add(rice)
        matches = RecommendationService().rank(Preferences(tags={"rice"}))

        class FakeGeminiClient:
            @staticmethod
            def generate(_prompt):
                return json.dumps(
                    {
                        "intro": "<script>Diskon sehat 50%!</script>",
                        "explanations": [
                            {
                                "id": item.pk,
                                "text": "Nasi Goreng sesuai dengan Nasi.",
                            }
                        ],
                    }
                )

        intro, explanations = RecommendationExplanationService(
            FakeGeminiClient()
        ).explain_with_intro(
            matches,
            Preferences(tags={"rice"}),
            "Aku mau nasi",
        )

        self.assertIsNone(intro)
        self.assertEqual(
            explanations,
            {item.pk: "Nasi Goreng sesuai dengan Nasi."},
        )

    def test_grounded_explanation_is_accepted_and_does_not_change_ranked_items(self):
        food = Category.objects.create(name="Makanan")
        spicy = MenuTag.objects.create(name="spicy", display_name=TAG_LABELS["spicy"])
        item = MenuItem.objects.create(
            category=food,
            name="Ayam Geprek",
            price=Decimal("15000"),
        )
        item.tags.add(spicy)
        preferences = Preferences(tags={"spicy"})
        matches = RecommendationService().rank(preferences)
        before = [match.item.pk for match in matches]
        fake = type(
            "FakeGeminiClient",
            (),
            {
                "generate": lambda _self, _prompt: json.dumps(
                    {
                        "explanations": [
                            {
                                "id": item.pk,
                                "text": "Ayam Geprek sesuai dengan Pedas.",
                            }
                        ]
                    }
                )
            },
        )()
        result = RecommendationExplanationService(fake).explain(matches, preferences)
        after = [match.item.pk for match in RecommendationService().rank(preferences)]
        self.assertEqual(result, {item.pk: "Ayam Geprek sesuai dengan Pedas."})
        self.assertEqual(before, after)

    def test_explanations_are_batched_and_bound_to_the_correct_ranked_items(self):
        food = Category.objects.create(name="Makanan")
        spicy = MenuTag.objects.create(name="spicy", display_name=TAG_LABELS["spicy"])
        first = MenuItem.objects.create(
            category=food,
            name="Ayam Geprek",
            price=Decimal("15000"),
        )
        first.tags.add(spicy)
        second = MenuItem.objects.create(
            category=food,
            name="Mie Pedas",
            price=Decimal("14000"),
        )
        second.tags.add(spicy)
        preferences = Preferences(tags={"spicy"})
        matches = RecommendationService().rank(preferences)
        generated = {
            "explanations": [
                {"id": match.item.pk, "text": f"{match.item.name} sesuai dengan Pedas."}
                for match in matches
            ]
        }
        calls = []

        class FakeGeminiClient:
            def generate(self, prompt):
                calls.append(prompt)
                return json.dumps(generated)

        result = RecommendationExplanationService(FakeGeminiClient()).explain(
            matches,
            preferences,
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            result,
            {
                first.pk: "Ayam Geprek sesuai dengan Pedas.",
                second.pk: "Mie Pedas sesuai dengan Pedas.",
            },
        )
        self.assertEqual(
            [match.item.pk for match in RecommendationService().rank(preferences)],
            [match.item.pk for match in matches],
        )

    def test_unsupported_or_malformed_explanations_are_rejected(self):
        food = Category.objects.create(name="Makanan")
        spicy = MenuTag.objects.create(name="spicy", display_name=TAG_LABELS["spicy"])
        item = MenuItem.objects.create(
            category=food,
            name="Ayam Geprek",
            price=Decimal("15000"),
        )
        item.tags.add(spicy)
        preferences = Preferences(tags={"spicy"})
        matches = RecommendationService().rank(preferences)
        unsafe = {
            "explanations": [
                {
                    "id": item.pk,
                    "text": "Ayam Geprek mengandung protein tinggi dan Pedas.",
                }
            ]
        }
        fake = type(
            "FakeGeminiClient",
            (),
            {"generate": lambda _self, _prompt: json.dumps(unsafe)},
        )()
        service = RecommendationExplanationService(fake)
        self.assertEqual(service.explain(matches, preferences), {})
        fake.generate = lambda _prompt: "{"
        self.assertEqual(service.explain(matches, preferences), {})
        self.assertIn("Pedas", service.fallback(matches[0]))


class RecommendationTests(TestCase):
    def setUp(self):
        self.food = Category.objects.create(name="Makanan")
        self.drinks = Category.objects.create(name="Minuman")
        self.spicy = MenuTag.objects.create(name="spicy", display_name=TAG_LABELS["spicy"])
        self.chicken = MenuTag.objects.create(
            name="chicken", display_name=TAG_LABELS["chicken"]
        )
        self.rice = MenuTag.objects.create(name="rice", display_name=TAG_LABELS["rice"])
        self.noodle = MenuTag.objects.create(
            name="noodle", display_name=TAG_LABELS["noodle"]
        )
        self.cold = MenuTag.objects.create(name="cold", display_name=TAG_LABELS["cold"])
        self.refreshing = MenuTag.objects.create(
            name="refreshing", display_name=TAG_LABELS["refreshing"]
        )
        self.drink = MenuTag.objects.create(
            name="drink", display_name=TAG_LABELS["drink"]
        )
        self.savory = MenuTag.objects.create(
            name="savory", display_name=TAG_LABELS["savory"]
        )
        self.filling = MenuTag.objects.create(
            name="filling", display_name=TAG_LABELS["filling"]
        )
        self.best = MenuItem.objects.create(
            category=self.food, name="Ayam Geprek", price=Decimal("15000")
        )
        self.best.tags.add(
            self.spicy, self.chicken, self.rice, self.filling, self.savory
        )
        self.noodles = MenuItem.objects.create(
            category=self.food, name="Mie Pedas", price=Decimal("14000")
        )
        self.noodles.tags.add(self.spicy, self.noodle, self.filling)
        self.tea = MenuItem.objects.create(
            category=self.drinks, name="Es Teh", price=Decimal("5000")
        )
        self.tea.tags.add(self.cold, self.refreshing, self.drink)
        self.unavailable = MenuItem.objects.create(
            category=self.food,
            name="Menu Habis",
            price=Decimal("9000"),
            is_available=False,
        )
        self.unavailable.tags.add(self.spicy)
        self.inactive = MenuItem.objects.create(
            category=self.food,
            name="Menu Nonaktif",
            price=Decimal("9000"),
            is_active=False,
        )
        self.inactive.tags.add(self.spicy)
        self.inactive_category = Category.objects.create(
            name="Arsip", is_active=False
        )
        self.archived = MenuItem.objects.create(
            category=self.inactive_category,
            name="Menu Arsip",
            price=Decimal("9000"),
        )
        self.archived.tags.add(self.spicy)
        self.recommender = RecommendationService()

    def test_tag_relationship_and_extraction(self):
        self.assertIn(self.spicy, self.best.tags.all())
        preferences = TagExtractor().extract("Aku mau ayam pedas dan nasi")
        self.assertEqual(preferences.tags & {"chicken", "spicy", "rice"},
                         {"chicken", "spicy", "rice"})
        legacy_preferences = Preferences({"spicy", "chicken", "rice"}, 20000)
        self.assertEqual(legacy_preferences.max_price, 20000)
        self.assertEqual(
            self.recommender.recommend(legacy_preferences)[0],
            self.best,
        )

    def test_direct_and_mood_preferences_have_different_weights(self):
        direct = self.recommender.rank(Preferences(tags={"spicy", "chicken"}))
        mood = self.recommender.rank(Preferences(mood_tags={"spicy", "chicken"}))
        direct_match = next(match for match in direct if match.item == self.best)
        mood_match = next(match for match in mood if match.item == self.best)
        self.assertEqual(direct_match.score, 8)
        self.assertEqual(mood_match.score, 4)
        self.assertIn(TAG_LABELS["spicy"], direct_match.match_reasons)

    def test_explicit_protein_preference_excludes_unrelated_ranked_matches(self):
        fish = MenuTag.objects.create(name="fish", display_name=TAG_LABELS["fish"])
        sweet = MenuTag.objects.create(name="sweet", display_name=TAG_LABELS["sweet"])
        fish_item = MenuItem.objects.create(
            category=self.food,
            name="Ikan Bakar",
            price=Decimal("26000"),
        )
        fish_item.tags.add(fish)
        sweet_item = MenuItem.objects.create(
            category=self.food,
            name="Pisang Goreng",
            price=Decimal("10000"),
        )
        sweet_item.tags.add(sweet)

        preferences = Preferences(tags={"fish", "sweet"}, category="Makanan")
        fish_matches = self.recommender.rank(
            preferences,
            required_tags={"fish"},
        )
        fish_and_sweet_matches = self.recommender.rank(
            preferences,
            required_tags={"fish", "sweet"},
        )

        self.assertEqual([match.item for match in fish_matches], [fish_item])
        self.assertEqual(fish_and_sweet_matches, [])

    def test_budget_category_moods_and_affordable_preference(self):
        within_budget = self.recommender.rank(
            Preferences(max_price=10000, category="Minuman")
        )
        self.assertEqual([match.item for match in within_budget], [self.tea])
        mood_matches = self.recommender.rank(
            Preferences(mood_tags={"cold", "refreshing", "drink"})
        )
        self.assertEqual(mood_matches[0].item, self.tea)
        affordable = self.recommender.rank(
            Preferences(prefer_affordable=True, tags={"spicy"})
        )
        self.assertEqual(affordable[0].item, self.noodles)
        self.assertIn("💰 Ramah di kantong", affordable[0].match_reasons)

    def test_negative_preferences_exclude_or_penalize_items(self):
        without_spicy = self.recommender.rank(
            Preferences(tags={"chicken"}, excluded_tags={"spicy"})
        )
        self.assertNotIn(self.best, [match.item for match in without_spicy])
        only_dislike = self.recommender.rank(Preferences(excluded_tags={"spicy"}))
        self.assertTrue(only_dislike)
        self.assertNotIn(self.noodles, [match.item for match in only_dislike])

        soft_dislike = self.recommender.rank(
            Preferences(tags={"spicy"}, soft_excluded_tags={"spicy"})
        )
        spicy_match = next(match for match in soft_dislike if match.item == self.best)
        self.assertLess(spicy_match.score, 4)

    def test_availability_exclusions_limit_and_deterministic_order(self):
        first = self.recommender.rank(Preferences(tags={"spicy"}), limit=2)
        second = self.recommender.rank(Preferences(tags={"spicy"}), limit=2)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        returned = [match.item for match in first]
        self.assertNotIn(self.unavailable, returned)
        self.assertNotIn(self.inactive, returned)
        self.assertNotIn(self.archived, returned)

        excluding = self.recommender.rank(
            Preferences(tags={"spicy"}), exclude_ids=[self.noodles.id]
        )
        self.assertNotIn(self.noodles, [match.item for match in excluding])

    def test_catalog_lookup_requires_all_requested_tags_and_only_returns_available_items(self):
        matches = self.recommender.find_catalog_matches({"spicy", "rice"})

        self.assertEqual([match.item for match in matches], [self.best])
        self.assertEqual(
            matches[0].match_reasons,
            (TAG_LABELS["rice"], TAG_LABELS["spicy"]),
        )


class DemoSeedTests(TestCase):
    def test_seed_demo_assigns_distinct_believable_tag_combinations(self):
        call_command("seed_demo", stdout=StringIO())

        ayam_geprek = MenuItem.objects.get(name="Ayam Geprek")
        es_jeruk = MenuItem.objects.get(name="Es Jeruk")
        tahu_crispy = MenuItem.objects.get(name="Tahu Crispy")
        mie_goreng = MenuItem.objects.get(name="Mie Goreng")

        self.assertTrue(
            {"spicy", "savory", "crispy", "chicken", "rice", "filling"}
            <= set(ayam_geprek.tags.values_list("name", flat=True))
        )
        self.assertTrue(
            {"sweet", "sour", "cold", "refreshing", "drink"}
            <= set(es_jeruk.tags.values_list("name", flat=True))
        )
        self.assertTrue(
            {"crispy", "savory", "snack", "light", "tofu"}
            <= set(tahu_crispy.tags.values_list("name", flat=True))
        )
        self.assertNotEqual(
            set(ayam_geprek.tags.values_list("name", flat=True)),
            set(mie_goreng.tags.values_list("name", flat=True)),
        )

    def test_seed_demo_adds_many_items_per_category_without_duplicates(self):
        call_command("seed_demo", stdout=StringIO())
        call_command("seed_demo", stdout=StringIO())

        self.assertEqual(
            MenuItem.objects.filter(category__name="Makanan").count(),
            21,
        )
        self.assertEqual(
            MenuItem.objects.filter(category__name="Minuman").count(),
            17,
        )
        self.assertTrue(MenuItem.objects.filter(name="Rendang Sapi").exists())
        self.assertTrue(MenuItem.objects.filter(name="Jus Mangga").exists())


class ChatbotIntegrationTests(TestCase):
    def setUp(self):
        self.gemini_patch = patch(
            "recommendation.services.gemini.GeminiClient.generate",
            return_value=None,
        )
        self.gemini_generate = self.gemini_patch.start()
        self.addCleanup(self.gemini_patch.stop)
        food = Category.objects.create(name="Makanan")
        self.spicy = MenuTag.objects.create(name="spicy", display_name=TAG_LABELS["spicy"])
        self.chicken = MenuTag.objects.create(
            name="chicken", display_name=TAG_LABELS["chicken"]
        )
        self.rice = MenuTag.objects.create(name="rice", display_name=TAG_LABELS["rice"])
        self.filling = MenuTag.objects.create(
            name="filling", display_name=TAG_LABELS["filling"]
        )
        self.best = MenuItem.objects.create(
            category=food,
            name="Ayam Geprek",
            price=Decimal("15000"),
        )
        self.best.tags.add(self.spicy, self.chicken, self.rice, self.filling)
        self.other = MenuItem.objects.create(
            category=food, name="Mie Pedas", price=Decimal("14000")
        )
        self.other.tags.add(self.spicy, self.filling)
        group = VariantGroup.objects.create(
            menu_item=self.best,
            name="Ukuran",
            is_required=True,
        )
        self.variant = VariantOption.objects.create(
            group=group,
            name="Regular",
            price_adjustment=Decimal("0"),
        )
        self.addon = AddOn.objects.create(name="Extra Sambal", price=Decimal("3000"))
        self.addon.menu_items.add(self.best)

    def post_chat(self, message, action=None):
        import json

        payload = {"message": message}
        if action:
            payload["action"] = action
        return self.client.post(
            "/api/recommendation/chat/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_chatbot_follow_up_retains_preferences_then_recommends(self):
        spicy = self.post_chat("Pengen pedas")
        self.assertEqual(spicy.status_code, 200)
        self.assertEqual(spicy.json()["state"], "ASKING_FOLLOWUP")
        self.assertIn("makanan berat", spicy.json()["message"])
        self.assertEqual(self.client.session["recommendation_state"]["tags"], ["spicy"])
        meal = self.post_chat("Makanan berat")
        self.assertEqual(meal.json()["state"], "ASKING_FOLLOWUP")
        self.assertIn("nasi atau mie", meal.json()["message"])

        rice = self.post_chat("Pengen nasi")
        self.assertEqual(rice.json()["state"], "RECOMMENDING")
        self.assertEqual(
            set(self.client.session["recommendation_state"]["tags"]),
            {"spicy", "filling", "heavy_meal", "rice"},
        )
        self.assertTrue(rice.json()["recommendations"])

    def test_cms_tag_alias_is_used_by_chatbot(self):
        smoky = MenuTag.objects.create(name="smoky", display_name="Berasap")
        MenuTagAlias.objects.create(tag=smoky, phrase="panggang asap")
        item = MenuItem.objects.create(
            category=self.best.category,
            name="Sate Asap",
            price=Decimal("16000"),
        )
        item.tags.add(smoky)

        response = self.post_chat("Saya mau yang panggang asap")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.session["recommendation_state"]["tags"],
            ["smoky"],
        )
        self.assertIn(
            "Sate Asap",
            {item["name"] for item in response.json()["recommendations"]},
        )

    def test_deterministic_followups_do_not_call_gemini_to_rephrase_questions(self):
        first = self.post_chat("Pengen pedas")
        self.assertEqual(first.json()["state"], "ASKING_FOLLOWUP")
        second = self.post_chat("Makanan berat")
        self.assertEqual(second.json()["state"], "ASKING_FOLLOWUP")
        self.assertIn("nasi atau mie", second.json()["message"])
        self.gemini_generate.assert_not_called()

    def test_sufficient_food_context_recommends_without_extra_followup(self):
        response = self.post_chat("Aku mau ayam pedas pakai nasi")

        self.assertEqual(response.json()["state"], "RECOMMENDING")
        self.assertTrue(response.json()["recommendations"])
        self.assertIsNone(response.json()["preferences"]["follow_up"])

    def test_new_protein_request_does_not_return_stale_flavor_only_matches(self):
        sweet = MenuTag.objects.create(name="sweet", display_name=TAG_LABELS["sweet"])
        fish = MenuTag.objects.create(name="fish", display_name=TAG_LABELS["fish"])
        fish_item = MenuItem.objects.create(
            category=self.best.category,
            name="Ikan Bakar",
            price=Decimal("26000"),
        )
        fish_item.tags.add(fish)
        sweet_item = MenuItem.objects.create(
            category=self.best.category,
            name="Pisang Goreng",
            price=Decimal("10000"),
        )
        sweet_item.tags.add(sweet)

        self.post_chat("Aku mau yang manis aja")
        self.post_chat("Kalau makanan manis ada gak?")
        response = self.post_chat("ikan")

        recommendations = response.json()["recommendations"]
        self.assertEqual([item["name"] for item in recommendations], ["Ikan Bakar"])
        self.assertIn(TAG_LABELS["fish"], response.json()["preferences"]["tags"])

    def test_current_food_tags_and_budget_are_required_despite_stale_preferences(self):
        fish = MenuTag.objects.create(name="fish", display_name=TAG_LABELS["fish"])
        sweet = MenuTag.objects.create(name="sweet", display_name=TAG_LABELS["sweet"])
        rice = self.rice
        fish_item = MenuItem.objects.create(
            category=self.best.category,
            name="Ikan Bakar",
            price=Decimal("26000"),
        )
        fish_item.tags.add(fish)
        sweet_item = MenuItem.objects.create(
            category=self.best.category,
            name="Pisang Goreng",
            price=Decimal("10000"),
        )
        sweet_item.tags.add(sweet)
        rice_item = MenuItem.objects.create(
            category=self.best.category,
            name="Nasi Uduk",
            price=Decimal("14000"),
        )
        rice_item.tags.add(rice)

        self.post_chat("ikan")
        no_exact_match = self.post_chat("ikan manis")
        self.assertEqual(no_exact_match.json()["recommendations"], [])
        self.assertIn("belum menemukan", no_exact_match.json()["message"])

        budgeted_rice = self.post_chat("ada gak nasi di bawah 20 ribu")
        self.assertEqual(
            [item["name"] for item in budgeted_rice.json()["recommendations"]],
            ["Nasi Uduk", "Ayam Geprek"],
        )
        self.assertTrue(
            all(
                item["price"] <= "20000.00"
                for item in budgeted_rice.json()["recommendations"]
            )
        )
        self.assertEqual(
            budgeted_rice.json()["active_search"]["max_price"],
            20000,
        )

    def test_conversation_sequence_scopes_search_filters_and_retries_empty_results(self):
        sweet = MenuTag.objects.create(name="sweet", display_name=TAG_LABELS["sweet"])
        fish = MenuTag.objects.create(name="fish", display_name=TAG_LABELS["fish"])
        sweet_food = MenuItem.objects.create(
            category=self.best.category,
            name="Pisang Manis",
            price=Decimal("14000"),
        )
        sweet_food.tags.add(sweet)
        sweet_food_over_budget = MenuItem.objects.create(
            category=self.best.category,
            name="Kue Manis",
            price=Decimal("20000"),
        )
        sweet_food_over_budget.tags.add(sweet)
        drink_category = Category.objects.create(name="Minuman")
        sweet_drink = MenuItem.objects.create(
            category=drink_category,
            name="Es Teh Manis",
            price=Decimal("5000"),
        )
        sweet_drink.tags.add(sweet)
        fish_item = MenuItem.objects.create(
            category=self.best.category,
            name="Ikan Bakar",
            price=Decimal("26000"),
        )
        fish_item.tags.add(fish)

        sweet_results = self.post_chat("hidangan manis di bawah 15rb").json()
        self.assertEqual(
            [item["id"] for item in sweet_results["recommendations"]],
            [sweet_food.id],
        )
        self.assertEqual(sweet_results["active_search"]["category"], "Makanan")
        self.assertEqual(sweet_results["active_search"]["max_price"], 15000)

        fish_results = self.post_chat("ikan").json()
        self.assertEqual(
            [item["id"] for item in fish_results["recommendations"]],
            [fish_item.id],
        )
        self.assertEqual(
            fish_results["active_search"]["required_tags"],
            [TAG_LABELS["fish"]],
        )
        self.assertIsNone(fish_results["active_search"]["max_price"])
        self.assertIsNone(fish_results["preferences"]["max_price"])
        self.assertNotIn("manis", fish_results["message"].casefold())
        self.assertNotIn("15.000", fish_results["message"])

        no_exact_match = self.post_chat("ikan manis").json()
        self.assertEqual(no_exact_match["recommendations"], [])
        challenged = self.post_chat("masa nggak ada ikan?").json()
        self.assertEqual(
            [item["id"] for item in challenged["recommendations"]],
            [fish_item.id],
        )
        self.assertNotIn("manis", challenged["message"].casefold())

        chicken_results = self.post_chat("kalau ayam ada apa?").json()
        self.assertIn(
            self.best.id,
            [item["id"] for item in chicken_results["recommendations"]],
        )
        self.assertNotIn(TAG_LABELS["fish"].casefold(), chicken_results["message"].casefold())
        self.assertNotIn("manis", chicken_results["message"].casefold())

    def test_budget_update_keeps_the_active_food_filter_but_replaces_the_cap(self):
        rice_item = MenuItem.objects.create(
            category=self.best.category,
            name="Nasi Uduk",
            price=Decimal("14000"),
        )
        rice_item.tags.add(self.rice)
        high_price_rice = MenuItem.objects.create(
            category=self.best.category,
            name="Nasi Spesial",
            price=Decimal("18000"),
        )
        high_price_rice.tags.add(self.rice)

        first = self.post_chat("nasi di bawah 20 ribu").json()
        self.assertEqual(first["active_search"]["required_tags"], [TAG_LABELS["rice"]])
        self.assertEqual(first["active_search"]["max_price"], 20000)

        updated = self.post_chat("di bawah 15 ribu").json()
        self.assertEqual(updated["active_search"]["required_tags"], [TAG_LABELS["rice"]])
        self.assertEqual(updated["active_search"]["max_price"], 15000)
        self.assertNotIn(
            high_price_rice.id,
            [item["id"] for item in updated["recommendations"]],
        )

    def test_catalog_question_applies_food_category_and_budget_as_hard_filters(self):
        sweet = MenuTag.objects.create(name="sweet", display_name=TAG_LABELS["sweet"])
        sweet_food = MenuItem.objects.create(
            category=self.best.category,
            name="Pisang Manis",
            price=Decimal("14000"),
        )
        sweet_food.tags.add(sweet)
        sweet_food_over_budget = MenuItem.objects.create(
            category=self.best.category,
            name="Kue Manis",
            price=Decimal("20000"),
        )
        sweet_food_over_budget.tags.add(sweet)
        drink_category = Category.objects.create(name="Minuman")
        sweet_drink = MenuItem.objects.create(
            category=drink_category,
            name="Es Teh Manis",
            price=Decimal("5000"),
        )
        sweet_drink.tags.add(sweet)

        result = self.post_chat(
            "Kalau hidangan manis di bawah 15rb ada gak?"
        ).json()

        self.assertTrue(result["catalog_question"])
        self.assertEqual(
            [item["id"] for item in result["recommendations"]],
            [sweet_food.id],
        )
        self.assertEqual(result["active_search"]["category"], "Makanan")
        self.assertEqual(result["active_search"]["max_price"], 15000)

    def test_ambiguous_food_message_reaches_gemini_before_unknown_fallback(self):
        response = self.post_chat(
            "Aku pengen yang bikin nagih tapi nggak bikin eneg"
        )

        self.assertEqual(response.json()["state"], "COLLECTING_PREFERENCES")
        self.assertEqual(response.json()["recommendations"], [])
        self.gemini_generate.assert_called_once()

    def test_catalog_question_returns_matching_available_items_without_changing_preferences(self):
        first = self.post_chat("Aku mau pedas")
        self.assertEqual(first.json()["state"], "ASKING_FOLLOWUP")
        self.post_chat("Makanan berat")
        before = self.post_chat("Aku mau nasi")
        previous_preferences = before.json()["preferences"]
        self.gemini_generate.reset_mock()
        self.gemini_generate.return_value = None

        result = self.post_chat("Pilihan nasi apa aja?")
        body = result.json()

        self.assertEqual(body["state"], "RECOMMENDING")
        self.assertEqual(
            [item["id"] for item in body["recommendations"]],
            [self.best.id],
        )
        self.assertEqual(body["preferences"], previous_preferences)
        self.assertIn("pilihan menu", body["message"])
        self.gemini_generate.assert_called_once()

    def test_catalog_question_with_no_matches_returns_safe_empty_result(self):
        response = self.post_chat("Pilihan seafood apa aja?")

        self.assertEqual(response.json()["recommendations"], [])
        self.assertIn("belum menemukan menu", response.json()["message"])
        self.gemini_generate.assert_not_called()

    def test_catalog_question_uses_batched_natural_intro_and_catalog_card_label(self):
        self.gemini_generate.return_value = json.dumps(
            {
                "intro": "Bisa, ini pilihan yang cocok dari katalog ya!",
                "explanations": [
                    {
                        "id": self.best.id,
                        "text": "Ayam Geprek sesuai dengan Nasi.",
                    }
                ],
            }
        )

        result = self.post_chat("Pilihan nasi apa aja?").json()

        self.assertEqual(
            result["message"],
            "Bisa, ini pilihan yang cocok dari katalog ya!",
        )
        self.assertTrue(result["catalog_question"])
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(
            result["recommendations"][0]["explanation"],
            "Ayam Geprek sesuai dengan Nasi.",
        )
        self.gemini_generate.assert_called_once()


    def test_open_answer_to_followup_keeps_existing_preferences_and_recommends(self):
        first_question = self.post_chat("Pengen pedas")
        self.assertEqual(first_question.json()["state"], "ASKING_FOLLOWUP")

        second_question = self.post_chat("Makanan berat")
        self.assertEqual(second_question.json()["state"], "ASKING_FOLLOWUP")
        self.assertIn("nasi atau mie", second_question.json()["message"])

        answer = self.post_chat("Terserah")
        preferences = answer.json()["preferences"]
        self.assertEqual(answer.json()["state"], "RECOMMENDING")
        self.assertTrue(answer.json()["recommendations"])
        self.assertIn(TAG_LABELS["spicy"], preferences["tags"])
        self.assertIn(TAG_LABELS["heavy_meal"], preferences["tags"])
        self.assertIsNone(preferences["follow_up"])
        self.assertIsNone(self.client.session["recommendation_state"]["last_question"])

    def test_provider_or_invalid_explanation_output_uses_deterministic_fallback(self):
        for provider_result in (None, "not-json"):
            with self.subTest(provider_result=provider_result):
                self.client.session.flush()
                self.gemini_generate.return_value = provider_result
                response = self.post_chat("Aku mau ayam pedas pakai nasi")

                self.assertEqual(response.json()["state"], "RECOMMENDING")
                card = next(
                    item
                    for item in response.json()["recommendations"]
                    if item["id"] == self.best.id
                )
                self.assertTrue(card["explanation"].startswith("Dipilih karena cocok dengan:"))
                self.assertIn(TAG_LABELS["chicken"], card["explanation"])
                self.assertIn(TAG_LABELS["spicy"], card["explanation"])

    def test_all_manual_conversation_examples_are_handled_without_internal_tag_labels(self):
        examples = (
            ("Aku mau makanan pedas", {"tags": ("spicy",)}),
            (
                "Aku lagi capek banget, pengen makanan yang bikin kenyang",
                {"tags": ("filling",), "moods": ("tired",)},
            ),
            (
                "Aduh laper parah, cariin ayam pedas yang murah dong",
                {
                    "tags": ("chicken", "spicy", "filling"),
                    "prefer_affordable": True,
                },
            ),
            (
                "Lagi gerah banget, pengen minuman yang seger",
                {
                    "tags": ("drink", "refreshing"),
                    "mood_tags": ("cold",),
                    "moods": ("hot_thirsty",),
                },
            ),
            (
                "Aku bingung mau makan apa",
                {"state": "COLLECTING_PREFERENCES"},
            ),
            ("Aku cuma mau ngemil", {"tags": ("snack",)}),
            ("Jangan pedas ya, aku nggak kuat", {"excluded_tags": ("spicy",)}),
            ("Budgetku 15 ribu aja", {"max_price": 15000}),
            (
                "Aku habis kerja, capek banget, terserah yang penting enak dan kenyang",
                {"tags": ("filling",), "moods": ("tired",)},
            ),
            (
                "Pengen yang pedes, ayam, nasi, tapi jangan lebih dari 20 ribu",
                {
                    "tags": ("spicy", "chicken", "rice"),
                    "max_price": 20000,
                },
            ),
        )
        for message, expected in examples:
            with self.subTest(message=message):
                self.client.session.flush()
                response = self.post_chat(message)
                self.assertEqual(response.status_code, 200)
                self.assertIsInstance(response.json()["message"], str)
                self.assertNotIn('"spicy"', response.content.decode("utf-8"))
                self.assertNotIn('"chicken"', response.content.decode("utf-8"))
                preferences = response.json()["preferences"]
                for field, values in expected.items():
                    if field in {"tags", "mood_tags", "excluded_tags"}:
                        values = tuple(TAG_LABELS[value] for value in values)
                        self.assertTrue(set(values) <= set(preferences[field]))
                    elif field == "moods":
                        self.assertTrue(set(values) <= set(preferences[field]))
                    elif field == "max_price":
                        self.assertEqual(response.json()["active_search"][field], values)
                    else:
                        self.assertEqual(preferences[field], values)

    def test_confusion_returns_friendly_quick_replies(self):
        for phrase in ("Aku bingung mau makan apa", "terserah deh", "gatau"):
            with self.subTest(phrase=phrase):
                response = self.post_chat(phrase)
                self.assertEqual(response.json()["state"], "COLLECTING_PREFERENCES")
                self.assertIn("nggak perlu mikir", response.json()["message"])
                self.assertTrue(response.json()["quick_replies"])

    def test_empty_initial_message_shows_the_start_prompt(self):
        response = self.post_chat("")
        self.assertEqual(response.status_code, 200)
        self.assertIn("bantu kamu memilih menu", response.json()["message"])
        self.assertTrue(response.json()["quick_replies"])

    def test_meaningful_terserah_message_keeps_its_food_and_mood_preferences(self):
        response = self.post_chat(
            "Aku habis kerja, capek banget, terserah yang penting enak dan kenyang"
        )
        preferences = response.json()["preferences"]
        self.assertEqual(response.json()["state"], "RECOMMENDING")
        self.assertIn(TAG_LABELS["filling"], preferences["tags"])
        self.assertIn("tired", preferences["moods"])
        self.assertNotIn("nggak perlu mikir", response.json()["message"])

    def test_remove_replace_and_budget_updates_preserve_unrelated_preferences(self):
        first = self.post_chat("Aku mau pedas, ayam, dan nasi")
        self.assertEqual(first.json()["state"], "RECOMMENDING")

        removed = self.post_chat("Eh jangan pedas deh")
        prefs = removed.json()["preferences"]
        self.assertNotIn(TAG_LABELS["spicy"], prefs["tags"])
        self.assertIn(TAG_LABELS["spicy"], prefs["excluded_tags"])
        self.assertIn(TAG_LABELS["chicken"], prefs["tags"])
        self.assertIn(TAG_LABELS["rice"], prefs["tags"])

        changed = self.post_chat("Ganti ayam jadi sapi")
        prefs = changed.json()["preferences"]
        self.assertNotIn(TAG_LABELS["chicken"], prefs["tags"])
        self.assertIn(TAG_LABELS["beef"], prefs["tags"])
        self.assertIn(TAG_LABELS["rice"], prefs["tags"])
        self.assertIn(TAG_LABELS["spicy"], prefs["excluded_tags"])

        cheaper = self.post_chat("Yang murah aja")
        prefs = cheaper.json()["preferences"]
        self.assertIn(TAG_LABELS["beef"], prefs["tags"])
        self.assertIn(TAG_LABELS["rice"], prefs["tags"])
        self.assertTrue(prefs["prefer_affordable"])

    def test_explicit_correction_replaces_stale_preferences(self):
        self.post_chat("Pengen pedas")
        self.post_chat("Mau ngemil aja")

        changed = self.post_chat("Eh gajadi, aku mau yang pedas")
        self.assertEqual(changed.json()["preferences"]["tags"], [TAG_LABELS["spicy"]])

        corrected = self.post_chat("Eh salah, maksudku manis aja")
        self.assertEqual(corrected.json()["preferences"]["tags"], [TAG_LABELS["sweet"]])
        self.assertEqual(corrected.json()["preferences"]["excluded_tags"], [])
        self.assertEqual(corrected.json()["preferences"]["soft_excluded_tags"], [])

    def test_contextual_revision_uses_validated_gemini_delta(self):
        self.post_chat("Aku mau makanan berat")
        response = {
            "intent": ConversationIntent.REPLACE_PREFERENCES,
            "add_tags": ["light_meal"],
            "remove_tags": ["heavy_meal"],
            "excluded_tags": [],
            "soft_excluded_tags": [],
            "moods": [],
            "clear_moods": False,
            "max_price": None,
            "prefer_affordable": None,
            "clear_max_price": False,
            "clear_prefer_affordable": False,
            "message_is_meaningful": True,
        }
        self.gemini_generate.return_value = json.dumps(response)
        result = self.post_chat("Yang tadi terlalu berat, cari yang lebih ringan")
        preferences = result.json()["preferences"]
        self.assertNotIn(TAG_LABELS["heavy_meal"], preferences["tags"])
        self.assertIn(TAG_LABELS["light_meal"], preferences["tags"])

    def test_provider_failure_does_not_change_saved_preferences(self):
        first = self.post_chat("Aku mau pedas dan ayam")
        saved = first.json()["preferences"]
        self.gemini_generate.return_value = None
        response = self.post_chat("Yang tadi terlalu berat")
        self.assertEqual(response.json()["preferences"]["tags"], saved["tags"])
        self.assertEqual(
            response.json()["preferences"]["excluded_tags"],
            saved["excluded_tags"],
        )

    def test_unknown_and_gibberish_do_not_mutate_or_replay_preferences(self):
        first = self.post_chat("Aku mau pedas dan ayam")
        stored = first.json()["preferences"]
        for message in ("test", "asdfgh", "123123", "haha"):
            with self.subTest(message=message):
                response = self.post_chat(message)
                self.assertEqual(response.json()["state"], "RECOMMENDING")
                self.assertEqual(response.json()["recommendations"], [])
                self.assertEqual(response.json()["preferences"]["tags"], stored["tags"])
                self.assertEqual(
                    response.json()["preferences"]["excluded_tags"],
                    stored["excluded_tags"],
                )

    def test_rejection_excludes_shown_items_without_changing_preferences(self):
        for number in range(5):
            item = MenuItem.objects.create(
                category=self.best.category,
                name=f"Menu Pedas Tambahan {number}",
                price=Decimal("12000") + number,
            )
            item.tags.add(self.spicy, self.filling)

        first = self.post_chat("Aku mau pedas dan kenyang")
        self.assertEqual(len(first.json()["recommendations"]), 3)
        first_ids = {item["id"] for item in first.json()["recommendations"]}
        preferences = first.json()["preferences"]

        second = self.post_chat("Cari yang lain")
        second_ids = {item["id"] for item in second.json()["recommendations"]}
        self.assertTrue(second_ids)
        self.assertTrue(first_ids.isdisjoint(second_ids))
        self.assertEqual(second.json()["preferences"]["tags"], preferences["tags"])
        self.assertEqual(second.json()["preferences"]["moods"], preferences["moods"])

        third = self.post_chat("Jangan yang tadi")
        self.assertEqual(third.json()["preferences"]["tags"], preferences["tags"])
        self.assertTrue(second_ids.isdisjoint(
            {item["id"] for item in third.json()["recommendations"]}
        ))

    def test_previous_recommendation_references_return_real_available_items(self):
        result = self.post_chat("Aku mau ayam pedas dan nasi")
        recommendations = result.json()["recommendations"]
        self.assertGreaterEqual(len(recommendations), 1)

        first = self.post_chat("Yang pertama")
        self.assertEqual(
            [item["id"] for item in first.json()["recommendations"]],
            [recommendations[0]["id"]],
        )
        if len(recommendations) > 1:
            second = self.post_chat("Menu kedua aja")
            self.assertEqual(
                [item["id"] for item in second.json()["recommendations"]],
                [recommendations[1]["id"]],
            )

    def test_reference_without_previous_recommendations_is_handled_gracefully(self):
        response = self.post_chat("Yang pertama")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendations"], [])
        self.assertIsInstance(response.json()["message"], str)

    def test_contextual_answer_to_meal_question_replaces_only_meal_type(self):
        asked = self.post_chat("Pengen pedas")
        self.assertEqual(asked.json()["state"], "ASKING_FOLLOWUP")
        response = self.post_chat("Camilan")
        prefs = response.json()["preferences"]
        self.assertIn(TAG_LABELS["snack"], prefs["tags"])
        self.assertNotIn(TAG_LABELS["heavy_meal"], prefs["tags"])
        self.assertNotIn(TAG_LABELS["filling"], prefs["tags"])
        self.assertIn(TAG_LABELS["spicy"], prefs["tags"])

    def test_mood_can_be_cleared_without_losing_new_food_preferences(self):
        first = self.post_chat("Aku capek banget habis kerja dan mau yang mengenyangkan")
        self.assertIn("tired", first.json()["preferences"]["moods"])

        changed = self.post_chat("Udah nggak capek, sekarang pengen yang seger")
        preferences = changed.json()["preferences"]
        self.assertNotIn("tired", preferences["moods"])
        self.assertIn(TAG_LABELS["refreshing"], preferences["tags"])
        self.assertNotIn(TAG_LABELS["comfort_food"], preferences["mood_tags"])

    def test_clearing_the_only_mood_persists_the_empty_mood_context(self):
        self.post_chat("Aku capek banget")
        response = self.post_chat("Udah nggak capek")
        self.assertEqual(response.json()["state"], "COLLECTING_PREFERENCES")
        self.assertEqual(response.json()["preferences"]["moods"], [])
        self.assertEqual(
            self.client.session["recommendation_state"]["moods"],
            [],
        )

    def test_more_results_keep_preferences_and_exclude_shown_items(self):
        first = self.post_chat("mau ayam pedas nasi")
        self.assertEqual(first.json()["state"], "RECOMMENDING")
        shown_ids = {
            item["id"] for item in first.json()["recommendations"]
        }
        more = self.post_chat("Cari menu lain", action="more")
        self.assertEqual(more.status_code, 200)
        self.assertEqual(more.json()["state"], "RECOMMENDING")
        self.assertEqual(
            more.json()["preferences"]["tags"],
            first.json()["preferences"]["tags"],
        )
        self.assertTrue(
            shown_ids.isdisjoint(
                {item["id"] for item in more.json()["recommendations"]}
            )
        )

    def test_reset_clears_structured_preferences_and_recommendation_history(self):
        response = self.post_chat("Aku mau makanan pedas")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client.session["recommendation_state"]["tags"])

        response = self.post_chat("mulai lagi")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "COLLECTING_PREFERENCES")
        self.assertEqual(response.json()["recommendations"], [])
        self.assertNotIn("recommendation_state", self.client.session)
        self.assertNotIn("recommendation_shown", self.client.session)
        self.assertNotIn("recommendation_search", self.client.session)
        self.assertNotIn("recommendation_last_result_empty", self.client.session)

    def test_chat_to_required_variant_addon_cart_and_order(self):
        recommendations = self.post_chat("Aku mau ayam pedas pakai nasi")
        self.assertEqual(recommendations.status_code, 200)
        card = next(
            item
            for item in recommendations.json()["recommendations"]
            if item["id"] == self.best.id
        )
        self.assertIn(TAG_LABELS["spicy"], card["labels"])
        self.assertIn(TAG_LABELS["chicken"], card["match_reasons"])
        self.assertIsInstance(card["explanation"], str)
        self.assertTrue(card["explanation"])
        self.assertTrue(card["variants"][0]["required"])
        self.assertNotIn('"spicy"', str(recommendations.json()))

        import json

        added = self.client.post(
            "/api/recommendation/add/",
            data=json.dumps(
                {
                    "menu_item_id": self.best.id,
                    "quantity": 1,
                    "variant_ids": [self.variant.id],
                    "addon_ids": [self.addon.id],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(added.status_code, 200)
        cart_response = self.client.get("/api/cart/")
        self.assertEqual(len(cart_response.json()["items"]), 1)

        checkout = self.client.post(
            "/api/orders/checkout/",
            data=json.dumps(
                {
                    "customer_name": "Pelanggan Chat",
                    "phone": "",
                    "order_type": "TAKEAWAY",
                    "note": "",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(checkout.status_code, 201)
        order = Order.objects.get(public_id=checkout.json()["public_id"])
        order_item = order.items.get()
        self.assertEqual(order_item.item_name, "Ayam Geprek")
        self.assertEqual(order_item.variants.get().variant_option_id, self.variant.id)
        self.assertEqual(order_item.addons.get().addon_id, self.addon.id)
        self.assertEqual(self.client.get("/api/cart/").json()["items"], [])
        confirmation = self.client.get(f"/orders/{order.public_id}/")
        self.assertEqual(confirmation.status_code, 200)
