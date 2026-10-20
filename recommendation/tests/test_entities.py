"""Phase 1 entity identities, domain boundaries and provider trust contracts."""
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase

from menu.models import Category, MenuItem, MenuTag, MenuTagAlias
from ..services.chatbot import ChatbotService
from ..services.entity_resolver import EntityResolver
from ..services.text_generator import TextGenerator


class FakeGenerator(TextGenerator):
    def __init__(self, response: str | None = None) -> None:
        self.response: str | None = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str | None:
        self.prompts.append(prompt)
        return self.response


class EntityResolverTests(SimpleTestCase):
    def setUp(self) -> None:
        self.resolver = EntityResolver(((1, "Ayam Geprek"), (2, "Ayam Bakar"), (3, "Sushi")), ("ayam", "pedas", "nasi"))

    def test_requested_nonfood_differs_from_incidental_context(self) -> None:
        for text in ("Aku mau motor.", "Ada laptop?", "Jual helm?"):
            with self.subTest(text=text):
                self.assertEqual(self.resolver.resolve(text).domain_status, "NON_FOOD_OUT_OF_SCOPE")
        self.assertEqual(self.resolver.resolve("Aku habis naik motor dan sekarang lapar.").domain_status, "GENERAL_CONVERSATION")
        for text in ("Kalau parkir motor di mana?", "Motor pengantarnya sudah datang?"):
            self.assertEqual(self.resolver.resolve(text).domain_status, "RESTAURANT_INFORMATION")

    def test_database_identity_precedes_offline_food_examples(self) -> None:
        self.assertEqual(self.resolver.resolve("Ada sushi?").menu_ids, (3,))
        self.assertEqual(self.resolver.resolve("Mau ayam geprek.").menu_ids, (1,))
        self.assertEqual(self.resolver.resolve("Ada ayam geprek?").domain_status, "IN_CATALOG")

    def test_conservative_typo_matching_and_unknown_specific_food(self) -> None:
        self.assertEqual(self.resolver.resolve("Ada ayam geprekh?").menu_ids, (1,))
        self.assertEqual(self.resolver.resolve("Ada ayam quantum?").domain_status, "AMBIGUOUS_REQUEST")
        self.assertEqual(self.resolver.resolve("Ada glorp?").domain_status, "AMBIGUOUS_REQUEST")

    def test_polite_questions_and_consumption_verbs_preserve_entity_identity(self) -> None:
        self.assertEqual(self.resolver.resolve("Halo, apakah ada ayam geprek?").menu_ids, (1,))
        self.assertEqual(self.resolver.resolve("Aku ingin makan sushi").menu_ids, (3,))
        self.assertEqual(self.resolver.resolve("Saya ingin membeli laptop di sini").domain_status, "NON_FOOD_OUT_OF_SCOPE")

    def test_close_competing_names_are_clarified_instead_of_guessing(self) -> None:
        resolver = EntityResolver(((1, "Ayam Geprek"), (2, "Ayam Gepreks")))
        self.assertEqual(resolver.resolve("Ada ayam geprekt?").domain_status, "AMBIGUOUS_REQUEST")

    def test_general_preferences_and_negations_keep_existing_interpreter(self) -> None:
        for text in ("Aku mau ayam pedas pakai nasi", "Aku mau ayam tapi jangan pedas", "Yang tadi", "Aku mau nasi"):
            with self.subTest(text=text):
                self.assertIsNone(self.resolver.resolve(text))
        rejected = self.resolver.resolve('Aku tidak mau ayam geprek')
        self.assertEqual(rejected.domain_status, 'REJECTED_CATALOG')
        self.assertEqual(rejected.rejected_menu_ids, (1,))
        self.assertFalse(rejected.menu_ids)

    def test_ai_schema_rejects_invented_identity_price_and_wrong_types(self) -> None:
        valid = {"requested_entity": "sepeda", "domain_status": "NON_FOOD_OUT_OF_SCOPE", "entity_type": "product"}
        self.assertIsNotNone(EntityResolver.validate_ai(valid, "sepeda"))
        for invalid in ([], {**valid, "price": 1}, {**valid, "requested_entity": "ayam"},
                        {**valid, "domain_status": "IN_CATALOG"}, {**valid, "entity_type": []},
                        {**valid, "domain_status": "FOOD_BUT_NOT_AVAILABLE"}):
            with self.subTest(invalid=invalid):
                self.assertIsNone(EntityResolver.validate_ai(invalid, "sepeda"))


class EntityIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.food = Category.objects.create(name="Makanan")
        self.chicken = MenuTag.objects.create(name="chicken")
        self.spicy = MenuTag.objects.create(name="spicy")
        self.geprek = MenuItem.objects.create(name="Ayam Geprek", category=self.food, price=Decimal("18000"))
        self.bakar = MenuItem.objects.create(name="Ayam Bakar", category=self.food, price=Decimal("24000"))
        self.geprek.tags.add(self.chicken, self.spicy)
        self.bakar.tags.add(self.chicken)
        self.session = SessionStore()
        self.generator = FakeGenerator()

    def service(self) -> ChatbotService:
        return ChatbotService(self.session, gemini_client=self.generator)

    def test_exact_name_returns_only_that_menu_and_reference_uses_real_item(self) -> None:
        result = self.service().reply("Ada ayam geprek?")
        self.assertEqual([m.item.pk for m in result["recommendations"]], [self.geprek.pk])
        reference = self.service().reply("yang pertama")
        self.assertEqual([m.item.pk for m in reference["recommendations"]], [self.geprek.pk])
        self.assertEqual(self.generator.prompts, [])

    def test_unavailable_inactive_item_and_category_are_never_claimed_available(self) -> None:
        for target, field in ((self.geprek, "is_available"), (self.geprek, "is_active"), (self.food, "is_active")):
            with self.subTest(field=field, target=type(target).__name__):
                setattr(target, field, False)
                target.save(update_fields=[field])
                self.assertFalse(self.service().reply("Ada ayam geprek?")["recommendations"])
                setattr(target, field, True)
                target.save(update_fields=[field])

    def test_missing_food_nonfood_and_restaurant_information_do_not_mutate_preferences(self) -> None:
        self.service().reply("Aku mau ayam")
        old = dict(self.session.get("recommendation_state", {}))
        for text, term in (("Ada sushi?", "sushi"), ("Aku mau motor.", "motor"),
                           ("Ada laptop?", "laptop"), ("Kalau parkir motor di mana?", "staf")):
            with self.subTest(text=text):
                result = self.service().reply(text)
                self.assertIn(term, result["message"].casefold())
                self.assertFalse(result["recommendations"])
                self.assertEqual(self.session.get("recommendation_state", {}), old)

    def test_fake_menu_does_not_fall_back_to_general_chicken_matches(self) -> None:
        result = self.service().reply("Ada ayam quantum?")
        self.assertFalse(result["recommendations"])
        self.assertIn("jelaskan", result["message"])
        self.assertEqual(len(self.generator.prompts), 1)

    def test_unknown_object_structured_ai_and_invalid_output_fallback(self) -> None:
        self.generator.response = json.dumps({"requested_entity": "sepeda", "domain_status": "NON_FOOD_OUT_OF_SCOPE", "entity_type": "product"})
        result = self.service().reply("Aku mau sepeda")
        self.assertIn("pembelian barang", result["message"])
        self.assertEqual(len(self.generator.prompts), 1)
        for response in (None, "invalid-json", "[]", '{"requested_entity":"sepeda","domain_status":"IN_CATALOG","entity_type":"menu_item"}'):
            self.generator.response = response
            result = self.service().reply("Aku mau sepeda")
            self.assertFalse(result["recommendations"])
            self.assertIn("jelaskan", result["message"])

    def test_exact_item_respects_explicit_and_active_price_cap_and_exclusion(self) -> None:
        self.assertFalse(self.service().reply("Ada ayam geprek di bawah 10 ribu?")["recommendations"])
        self.service().reply("ayam di bawah 20 ribu")
        self.assertFalse(self.service().reply("Ada ayam bakar?")["recommendations"])
        self.service().reply("Jangan pedas")
        self.assertFalse(self.service().reply("Ada ayam geprek?")["recommendations"])
        self.session = SessionStore()
        self.service().reply("Ada ayam tanpa pedas?")
        self.assertIn("spicy", self.session["recommendation_search"]["excluded_tags"])
        self.assertFalse(self.service().reply("Ada ayam geprek?")["recommendations"])

    def test_database_alias_and_new_catalog_item_work_without_hardcoded_names(self) -> None:
        custom = MenuTag.objects.create(name="custom_food", display_name="Menu khusus")
        MenuTagAlias.objects.create(tag=custom, phrase="hidangan pelangi")
        item = MenuItem.objects.create(name="Hidangan Andalan Baru", category=self.food, price=Decimal("9000"))
        item.tags.add(custom)
        result = self.service().reply("Ada hidangan andalan baru?")
        self.assertEqual([m.item.pk for m in result["recommendations"]], [item.pk])
        alias_result = self.service().reply("Aku mau hidangan pelangi")
        self.assertEqual([m.item.pk for m in alias_result["recommendations"]], [item.pk])

    def test_quota_exhaustion_clarifies_unknown_without_provider_and_sessions_are_isolated(self) -> None:
        self.session["gemini_calls"] = 100
        result = self.service().reply("Aku mau glorp")
        self.assertIn("jelaskan", result["message"])
        self.assertFalse(self.generator.prompts)
        fresh = ChatbotService(SessionStore(), gemini_client=FakeGenerator())
        self.assertFalse(fresh.reply("yang pertama")["recommendations"])

    def test_wire_contract_decimal_and_no_order_side_effect(self) -> None:
        with patch("recommendation.services.gemini.GeminiClient.generate", return_value=None):
            response = self.client.post("/api/recommendation/chat/", {"message": "Ada ayam geprek?"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue({"message", "state", "preferences", "recommendations", "quick_replies"}.issubset(result))
        self.assertEqual(result["recommendations"][0]["price"], "18000.00")
        self.assertNotIn("menu_ids", result)
        from orders.models import Order
        self.assertEqual(Order.objects.count(), 0)
