"""Check lazy Python 3.14 annotations and the internal/wire response boundary."""

import importlib
import inspect
from decimal import Decimal
from typing import get_type_hints
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from menu.models import Category, MenuItem, MenuTag
from ..services.conversation_interpreter import ConversationInterpretation
from ..services.response_types import ChatbotResponse, QuickReply


class AnnotationResolutionTests(SimpleTestCase):
    def test_all_service_and_view_callable_annotations_resolve(self) -> None:
        names = (
            "chatbot",
            "conversation_interpreter",
            "conversation_session",
            "gemini",
            "language",
            "mood_extractor",
            "mood_resolver",
            "recommendation",
            "tag_extractor",
            "text_generator",
            "ai.GeminiInterpreter",
            "ai.explanations",
        )
        modules = [importlib.import_module(f"recommendation.services.{name}") for name in names]
        modules.append(importlib.import_module("recommendation.views"))
        checked = 0

        for module in modules:
            namespace = {**vars(module), "ConversationInterpretation": ConversationInterpretation}
            functions = []

            for value in vars(module).values():
                if getattr(value, "__module__", None) != module.__name__:
                    continue

                if inspect.isfunction(value):
                    functions.append(value)
                elif inspect.isclass(value):
                    get_type_hints(value, globalns=namespace)

                    for member in vars(value).values():
                        if isinstance(member, (staticmethod, classmethod)):
                            functions.append(member.__func__)
                        elif isinstance(member, property) and member.fget is not None:
                            functions.append(member.fget)
                        elif inspect.isfunction(member):
                            functions.append(member)

            for function in functions:
                function = inspect.unwrap(function)

                # Python 3.14 generates this hook; it is not a source callable.
                if function.__name__ == "__annotate__":
                    continue

                with self.subTest(function=f"{module.__name__}.{function.__qualname__}"):
                    signature = inspect.signature(function)
                    hints = get_type_hints(function, globalns=namespace)
                    self.assertIn("return", hints)

                    for name in signature.parameters:
                        if name not in ("self", "cls"):
                            self.assertIn(name, hints)

                checked += 1

        self.assertGreater(checked, 80)

    def test_response_schemas_preserve_required_and_optional_keys(self) -> None:
        self.assertEqual(
            ChatbotResponse.__required_keys__,
            {
                "message",
                "state",
                "preferences",
                "recommendations",
                "quick_replies",
            },
        )
        self.assertEqual(
            ChatbotResponse.__optional_keys__,
            {
                "active_search",
                "explanations",
                "catalog_question",
                "combination",
            },
        )
        self.assertEqual(QuickReply.__required_keys__, {"label", "value"})
        self.assertEqual(QuickReply.__optional_keys__, {"action"})


class TypedResponseBoundaryTests(TestCase):
    def test_wire_response_preserves_decimal_prices_and_hides_internal_explanations(self) -> None:
        category = Category.objects.create(name="Makanan")
        tag = MenuTag.objects.create(name="rice", display_name="Nasi")
        item = MenuItem.objects.create(name="Nasi", category=category, price=Decimal("10000.50"))
        item.tags.add(tag)

        with patch("recommendation.services.gemini.GeminiClient.generate", return_value=None):
            response = self.client.post(
                "/api/recommendation/chat/",
                {"message": "mau nasi"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("explanations", payload)
        self.assertEqual(payload["recommendations"][0]["price"], "10000.50")
        self.assertEqual(payload["recommendations"][0]["id"], item.pk)
        self.assertIsInstance(payload["recommendations"][0]["explanation"], str)
        self.assertEqual(payload["active_search"]["required_tags"], ["🍚 Nasi"])
