"""Behavioral contracts shared by the original and plain domain objects."""

from copy import copy, deepcopy
import json
import pickle

from django.test import SimpleTestCase

from menu.models import MenuItem
from ..services.recommendation import RecommendationMatch, SearchConstraints
from ..services.tag_extractor import Preferences


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
