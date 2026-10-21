"""Contract and consumer tests for interchangeable text generators."""

from decimal import Decimal
import json
from typing import override
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase, override_settings

from menu.models import Category, MenuItem, MenuTag
from ..services.ai.GeminiInterpreter import GeminiInterpreter
from ..services.ai.explanations import RecommendationExplanationService
from ..services.chatbot import ChatbotService
from ..services.gemini import GeminiClient
from ..services.recommendation import RecommendationMatch
from ..services.tag_extractor import Preferences, TagExtractor
from ..services.text_generator import TextGenerator


class RecordingGenerator(TextGenerator):
    def __init__(self, response: str | None) -> None:
        self.response: str | None = response
        self.prompts: list[str] = []

    @override
    def generate(self, prompt: str) -> str | None:
        self.prompts.append(prompt)

        return self.response

    def __bool__(self) -> bool:
        # A valid dependency must be selected by presence, not truthiness.
        return False


class TextGeneratorContractTests(SimpleTestCase):
    def test_abstract_contract_and_incomplete_subclass_cannot_be_instantiated(self) -> None:
        class IncompleteGenerator(TextGenerator):
            pass

        for generator_class in (TextGenerator, IncompleteGenerator):
            with self.subTest(generator_class=generator_class), self.assertRaises(TypeError):
                generator_class()

    @override_settings(GEMINI_ENABLED=True, DEBUG=True)
    def test_fake_and_gemini_are_substitutable_for_text_and_unavailable_results(self) -> None:
        class FakeModels:
            def generate_content(self, **kwargs: object) -> object:
                return type("Response", (), {"text": "response"})()

        with patch("recommendation.services.gemini.os.getenv", return_value=None):
            gemini = GeminiClient()

        self.assertIsInstance(gemini, TextGenerator)
        self.assertIsNone(gemini.generate("prompt"))
        gemini.client = type("Provider", (), {"models": FakeModels()})()
        generators: list[TextGenerator] = [gemini, RecordingGenerator("response")]

        for generator in generators:
            self.assertEqual(generator.generate("prompt"), "response")

        self.assertIsNone(RecordingGenerator(None).generate("prompt"))

    def test_interpreter_uses_falsey_generator_and_maps_valid_response(self) -> None:
        generator = RecordingGenerator(
            json.dumps(
                {
                    "intent": "RECOMMEND",
                    "add_tags": ["rice"],
                    "remove_tags": [],
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
            )
        )

        with patch(
            "recommendation.services.ai.GeminiInterpreter.GeminiClient",
            side_effect=AssertionError("Unexpected default provider"),
        ):
            interpreter = GeminiInterpreter(generator)
            result = interpreter.interpret("mau nasi")

        self.assertIs(interpreter.gemini_client, generator)
        self.assertEqual(result.tags, {"rice"})
        self.assertEqual(result.operations[0].tags, ("rice",))
        self.assertEqual(len(generator.prompts), 1)

    def test_missing_and_invalid_generator_output_keep_interpreter_fallback(self) -> None:
        for response in (None, "not-json", "{}"):
            with self.subTest(response=response):
                generator = RecordingGenerator(response)
                self.assertIsNone(GeminiInterpreter(generator).interpret("mau nasi"))
                self.assertEqual(len(generator.prompts), 1)

    def test_allowed_tags_accessor_returns_an_independent_catalog_aware_set(self) -> None:
        extractor = TagExtractor()
        extractor.configure_catalog_tags([("custom_tag", "Tag Khusus")])
        names = extractor.get_allowed_tags()
        self.assertIn("custom_tag", names)
        names.clear()
        self.assertIn("custom_tag", extractor.get_allowed_tags())


class TextGeneratorConsumerTests(TestCase):
    def setUp(self) -> None:
        category = Category.objects.create(name="Makanan")
        tag = MenuTag.objects.create(name="rice", display_name="Nasi")
        self.item: MenuItem = MenuItem.objects.create(
            name="Nasi",
            category=category,
            price=Decimal("10000"),
        )
        self.item.tags.add(tag)

    def test_explanation_service_delegates_and_validates_using_falsey_generator(self) -> None:
        generator = RecordingGenerator(
            json.dumps(
                {
                    "explanations": [{"id": self.item.pk, "text": "Nasi sesuai nasi."}],
                }
            )
        )

        with patch(
            "recommendation.services.ai.explanations.GeminiClient",
            side_effect=AssertionError("Unexpected default provider"),
        ):
            service = RecommendationExplanationService(generator)
            matches = [RecommendationMatch(self.item, 4, ("Nasi",), ("Nasi",))]
            explanations = service.explain(matches, Preferences(tags={"rice"}))

        self.assertIs(service.gemini_client, generator)
        self.assertEqual(explanations, {self.item.pk: "Nasi sesuai nasi."})
        self.assertEqual(len(generator.prompts), 1)
        self.assertIs(matches[0].item, self.item)

    def test_chatbot_shares_injected_generator_and_preserves_local_recommendation(self) -> None:
        for response in (None, "invalid-json"):
            with self.subTest(response=response):
                generator = RecordingGenerator(response)

                with patch(
                    "recommendation.services.chatbot.GeminiClient",
                    side_effect=AssertionError("Unexpected default provider"),
                ):
                    chatbot = ChatbotService(SessionStore(), gemini_client=generator)
                    result = chatbot.reply("mau nasi")

                self.assertIs(chatbot.gemini_client, generator)
                boundary = chatbot.gemini_interpreter.gemini_client
                self.assertIs(boundary.provider, generator)
                self.assertIs(chatbot.explanation_service.gemini_client, boundary)
                self.assertIs(chatbot.semantic_reranker.generator, boundary)
                self.assertEqual(
                    [match.item.pk for match in result["recommendations"]], [self.item.pk]
                )
                self.assertEqual(
                    result["explanations"][self.item.pk], "Dipilih karena cocok dengan: 🍚 Nasi."
                )
                self.assertEqual(len(generator.prompts), 0)

    def test_default_chatbot_constructs_only_one_shared_provider(self) -> None:
        generator = RecordingGenerator(None)

        with patch(
            "recommendation.services.chatbot.GeminiClient", return_value=generator
        ) as constructor:
            chatbot = ChatbotService(SessionStore())

        constructor.assert_called_once_with()
        boundary = chatbot.gemini_interpreter.gemini_client
        self.assertIs(boundary.provider, generator)
        self.assertIs(chatbot.explanation_service.gemini_client, boundary)
        self.assertIs(chatbot.semantic_reranker.generator, boundary)
