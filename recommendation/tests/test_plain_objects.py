"""Behavioral contracts shared by the original and plain domain objects."""

from copy import copy, deepcopy
import json
import pickle

from django.test import SimpleTestCase

from menu.models import MenuItem
from ..services.conversation_interpreter import (
    ConversationInterpretation,
    PreferenceOperation,
)
from ..services.recommendation import RecommendationMatch, SearchConstraints
from ..services.tag_extractor import Preferences


class PreferenceOperationContractTests(SimpleTestCase):
    def test_constructor_equality_hash_and_repr(self) -> None:
        operation = PreferenceOperation("REPLACE", ("rice",), ("noodle",))
        equivalent = PreferenceOperation(action="REPLACE", tags=("rice",), remove_tags=("noodle",))
        self.assertEqual(operation, equivalent)
        self.assertEqual(hash(operation), hash(equivalent))
        self.assertEqual(len({operation, equivalent}), 1)
        self.assertNotEqual(operation, PreferenceOperation("ADD", ("rice",)))
        self.assertEqual(
            repr(operation),
            "PreferenceOperation(action='REPLACE', tags=('rice',), remove_tags=('noodle',))",
        )
        self.assertEqual(PreferenceOperation("KEEP").tags, ())
        self.assertEqual(PreferenceOperation("KEEP").remove_tags, ())

    def test_fields_cannot_be_assigned_deleted_or_extended(self) -> None:
        operation = PreferenceOperation("ADD", ("rice",))

        for name in ("action", "tags", "remove_tags", "unexpected"):
            with self.subTest(name=name), self.assertRaises(AttributeError):
                setattr(operation, name, "changed")

        for name in ("action", "tags", "remove_tags"):
            with self.subTest(name=name), self.assertRaises(AttributeError):
                delattr(operation, name)

    def test_copy_pickle_pattern_matching_and_exact_class_equality(self) -> None:
        operation = PreferenceOperation("ADD", ("rice",))

        for duplicate in (
            copy(operation),
            deepcopy(operation),
            pickle.loads(pickle.dumps(operation)),
        ):
            self.assertEqual(duplicate, operation)

        match operation:
            case PreferenceOperation(action, tags, removed):
                self.assertEqual((action, tags, removed), ("ADD", ("rice",), ()))
            case _:
                self.fail("Positional pattern matching changed")

        class SpecializedOperation(PreferenceOperation):
            pass

        self.assertNotEqual(operation, SpecializedOperation("ADD", ("rice",)))
        self.assertIs(operation.__eq__(object()), NotImplemented)


class ConversationInterpretationContractTests(SimpleTestCase):
    def test_default_collections_are_independent_and_result_stays_mutable(self) -> None:
        first = ConversationInterpretation("UNKNOWN")
        second = ConversationInterpretation("UNKNOWN")

        for name in ("tags", "excluded_tags", "soft_excluded_tags", "moods", "catalog_tags"):
            getattr(first, name).add("sample")
            self.assertEqual(getattr(second, name), set())

        first.operations.append(PreferenceOperation("KEEP"))
        self.assertEqual(second.operations, [])
        first.intent = "RECOMMEND"
        self.assertEqual(first.intent, "RECOMMEND")

    def test_full_positional_constructor_and_value_equality(self) -> None:
        values = (
            "RECOMMEND",
            [PreferenceOperation("ADD", ("rice",))],
            {"rice"},
            {"fish"},
            {"spicy"},
            {"tired"},
            20000,
            "Makanan",
            True,
            "base",
            "first",
            True,
            "meal_type",
            True,
            True,
            True,
            True,
            {"rice"},
        )
        result = ConversationInterpretation(*values)
        self.assertEqual(tuple(getattr(result, name) for name in result.__match_args__), values)
        self.assertEqual(result, deepcopy(result))
        self.assertIs(result.tags, values[2])

        with self.assertRaises(TypeError):
            hash(result)

    def test_defaults_remain_unchanged(self) -> None:
        result = ConversationInterpretation("UNKNOWN")

        for name in ("max_price", "category", "last_question", "contextual_reference", "follow_up"):
            self.assertIsNone(getattr(result, name))

        for name in (
            "prefer_affordable",
            "message_is_meaningful",
            "clear_moods",
            "clear_max_price",
            "clear_prefer_affordable",
            "contextual_revision",
        ):
            self.assertIs(getattr(result, name), False)

    def test_explicit_none_keeps_legacy_constructor_behavior(self) -> None:
        result = ConversationInterpretation("UNKNOWN", operations=None, tags=None)  # type: ignore[arg-type]
        self.assertIsNone(result.operations)
        self.assertIsNone(result.tags)
        self.assertEqual(result, ConversationInterpretation("UNKNOWN", operations=None, tags=None))  # type: ignore[arg-type]


class SearchConstraintsContractTests(SimpleTestCase):
    def test_json_round_trip_sorted_output_and_hash(self) -> None:
        constraints = SearchConstraints(
            frozenset({"rice", "chicken"}),
            frozenset({"fish"}),
            "Makanan",
            20000,
            frozenset({"tired"}),
        )
        expected = {
            "required_tags": ["chicken", "rice"],
            "excluded_tags": ["fish"],
            "category": "Makanan",
            "max_price": 20000,
            "moods": ["tired"],
        }
        self.assertEqual(constraints.to_dict(), expected)
        restored = SearchConstraints.from_dict(json.loads(json.dumps(expected)))
        self.assertEqual(restored, constraints)
        self.assertEqual(hash(restored), hash(constraints))
        payload = constraints.to_dict()
        payload["required_tags"].append("spicy")
        self.assertNotIn("spicy", constraints.required_tags)

    def test_read_only_defaults_copy_and_repr(self) -> None:
        constraints = SearchConstraints()
        self.assertEqual(
            constraints.to_dict(),
            {
                "required_tags": [],
                "excluded_tags": [],
                "category": None,
                "max_price": None,
                "moods": [],
            },
        )
        self.assertEqual(
            repr(constraints),
            "SearchConstraints(required_tags=frozenset(), excluded_tags=frozenset(), category=None, max_price=None, moods=frozenset())",
        )

        for name in (*constraints.__match_args__, "unexpected"):
            with self.subTest(name=name), self.assertRaises(AttributeError):
                setattr(constraints, name, None)

        for name in constraints.__match_args__:
            with self.subTest(name=name), self.assertRaises(AttributeError):
                delattr(constraints, name)

        self.assertEqual(deepcopy(constraints), constraints)
        self.assertEqual(pickle.loads(pickle.dumps(constraints)), constraints)


class RecommendationMatchContractTests(SimpleTestCase):
    def test_value_equality_hash_and_model_reference(self) -> None:
        item = MenuItem(pk=42, name="Nasi")
        match = RecommendationMatch(item, 4, ("Nasi",), ("Nasi",))
        equivalent = RecommendationMatch(
            item=item, score=4, match_reasons=("Nasi",), labels=("Nasi",)
        )
        self.assertEqual(match, equivalent)
        self.assertEqual(hash(match), hash(equivalent))
        self.assertEqual(
            repr(match),
            "RecommendationMatch(item=<MenuItem: Nasi>, score=4, match_reasons=('Nasi',), labels=('Nasi',))",
        )
        self.assertIs(copy(match).item, item)
        item.name = "Nasi Baru"
        self.assertEqual(match.item.name, "Nasi Baru")

    def test_read_only_and_unsaved_model_hash_behavior(self) -> None:
        match = RecommendationMatch(MenuItem(name="Nasi"), 4, (), ())

        for name in (*match.__match_args__, "unexpected"):
            with self.subTest(name=name), self.assertRaises(AttributeError):
                setattr(match, name, None)

        for name in match.__match_args__:
            with self.subTest(name=name), self.assertRaises(AttributeError):
                delattr(match, name)

        with self.assertRaises(TypeError):
            hash(match)


class PreferencesContractTests(SimpleTestCase):
    def test_explicit_none_keeps_legacy_constructor_behavior(self) -> None:
        preferences = Preferences(tags=None)  # type: ignore[arg-type]
        self.assertIsNone(preferences.tags)
        self.assertEqual(preferences, Preferences(tags=None))  # type: ignore[arg-type]

    def test_collections_are_independent_and_supplied_set_keeps_identity(self) -> None:
        first, second = Preferences(), Preferences()

        for name in ("tags", "mood_tags", "excluded_tags", "soft_excluded_tags", "moods"):
            getattr(first, name).add("sample")
            self.assertEqual(getattr(second, name), set())

        tags = {"rice"}
        self.assertIs(Preferences(tags=tags).tags, tags)
        self.assertIsNone(second.max_price)
        self.assertIsNone(second.category)
        self.assertIs(second.prefer_affordable, False)

    def test_full_positional_constructor_serialization_and_session_round_trip(self) -> None:
        preferences = Preferences(
            {"rice", "chicken"}, 20000, {"warm"}, {"fish"}, {"spicy"}, "Makanan", True, {"tired"}
        )
        expected = {
            "tags": ["chicken", "rice"],
            "mood_tags": ["warm"],
            "excluded_tags": ["fish"],
            "soft_excluded_tags": ["spicy"],
            "max_price": 20000,
            "category": "Makanan",
            "prefer_affordable": True,
            "moods": ["tired"],
            "state": "RECOMMENDING",
            "follow_up": "base",
        }
        self.assertEqual(preferences.to_dict("RECOMMENDING", "base"), expected)
        restored = Preferences.from_dict(json.loads(json.dumps(expected)))
        self.assertEqual(restored, preferences)
        restored.tags.add("noodle")
        self.assertNotIn("noodle", preferences.tags)

    def test_positive_tags_are_a_copy_and_value_stays_mutable_unhashable(self) -> None:
        preferences = Preferences(tags={"rice"}, mood_tags={"warm"})
        positive = preferences.all_positive_tags
        self.assertEqual(positive, {"rice", "warm"})
        positive.clear()
        self.assertEqual(preferences.tags, {"rice"})
        preferences.max_price = 15000
        self.assertEqual(preferences.max_price, 15000)
        self.assertEqual(preferences, deepcopy(preferences))

        with self.assertRaises(TypeError):
            hash(preferences)
