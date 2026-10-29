from collections.abc import Iterable
import re
from types import NotImplementedType
from typing import ClassVar, Self, TypedDict, cast

from .language import IndonesianPriceParser, normalize_text


# Distinguish an omitted collection from an explicitly supplied value, as before.
_COLLECTION_DEFAULT: object = object()


class PreferencesPayload(TypedDict, total=False):
    tags: list[str]
    max_price: int | None
    mood_tags: list[str]
    excluded_tags: list[str]
    soft_excluded_tags: list[str]
    category: str | None
    prefer_affordable: bool
    moods: list[str]
    state: str
    follow_up: str | None


class Preferences:
    """Mutable conversation preferences with independent default collections."""

    __match_args__: ClassVar[tuple[str, ...]] = (
        "tags",
        "max_price",
        "mood_tags",
        "excluded_tags",
        "soft_excluded_tags",
        "category",
        "prefer_affordable",
        "moods",
    )
    __hash__ = None

    def __init__(
        self,
        tags: set[str] = cast(set[str], _COLLECTION_DEFAULT),
        max_price: int | None = None,
        mood_tags: set[str] = cast(set[str], _COLLECTION_DEFAULT),
        excluded_tags: set[str] = cast(set[str], _COLLECTION_DEFAULT),
        soft_excluded_tags: set[str] = cast(set[str], _COLLECTION_DEFAULT),
        category: str | None = None,
        prefer_affordable: bool = False,
        moods: set[str] = cast(set[str], _COLLECTION_DEFAULT),
    ) -> None:
        self.tags: set[str] = set() if tags is _COLLECTION_DEFAULT else tags
        self.max_price: int | None = max_price
        self.mood_tags: set[str] = set() if mood_tags is _COLLECTION_DEFAULT else mood_tags
        self.excluded_tags: set[str] = (
            set() if excluded_tags is _COLLECTION_DEFAULT else excluded_tags
        )
        self.soft_excluded_tags: set[str] = (
            set() if soft_excluded_tags is _COLLECTION_DEFAULT else soft_excluded_tags
        )
        self.category: str | None = category
        self.prefer_affordable: bool = prefer_affordable
        self.moods: set[str] = set() if moods is _COLLECTION_DEFAULT else moods

    def __eq__(self, other: object) -> bool | NotImplementedType:
        if not isinstance(other, Preferences) or type(self) is not type(other):
            return NotImplemented

        return all(getattr(self, name) == getattr(other, name) for name in self.__match_args__)

    def __repr__(self) -> str:
        fields = ", ".join(f"{name}={getattr(self, name)!r}" for name in self.__match_args__)

        return f"{type(self).__qualname__}({fields})"

    @property
    def all_positive_tags(self) -> set[str]:
        return self.tags | self.mood_tags

    def to_dict(
        self,
        state: str = "COLLECTING_PREFERENCES",
        follow_up: str | None = None,
    ) -> PreferencesPayload:
        return {
            "tags": sorted(self.tags),
            "mood_tags": sorted(self.mood_tags),
            "excluded_tags": sorted(self.excluded_tags),
            "soft_excluded_tags": sorted(self.soft_excluded_tags),
            "max_price": self.max_price,
            "category": self.category,
            "prefer_affordable": self.prefer_affordable,
            "moods": sorted(self.moods),
            "state": state,
            "follow_up": follow_up,
        }

    @classmethod
    def from_dict(cls, data: PreferencesPayload) -> Self:
        return cls(
            tags=set(data.get("tags", [])),
            mood_tags=set(data.get("mood_tags", [])),
            excluded_tags=set(data.get("excluded_tags", [])),
            soft_excluded_tags=set(data.get("soft_excluded_tags", [])),
            max_price=data.get("max_price"),
            category=data.get("category"),
            prefer_affordable=data.get("prefer_affordable", False),
            moods=set(data.get("moods", [])),
        )


class TagExtractor:
    """Catalog tag vocabulary and aliases shared with the Gemini assistant."""

    ALIASES: ClassVar[dict[str, tuple[str, ...]]] = {
        "spicy": (
            "pedas",
            "sambal",
            "sambalnya",
            "cabai",
            "cabe",
            "nampol",
            "nendang",
            "bikin melek",
            "rasa yang kuat",
            "rasa kuat",
        ),
        "very_spicy": ("sangat pedas", "pedas banget", "pedas parah", "pedas gila", "super pedas"),
        "savory": ("gurih", "asin gurih", "savory", "berbumbu"),
        "sweet": ("manis", "yang manis", "dessert", "pencuci mulut"),
        "sour": ("asam", "kecut", "segar asam"),
        "salty": ("asin",),
        "umami": ("umami", "kaya rasa"),
        "rich": ("creamy", "kaya rasa", "berlemak", "saus kental"),
        "mild": ("tidak pedas", "nggak pedas", "ga pedas", "kurang pedas", "tidak terlalu pedas"),
        "crispy": ("renyah", "crispy", "kriuk", "krenyes"),
        "crunchy": ("garing", "crunchy", "kriuk"),
        "soft": ("lembut", "empuk", "tekstur lembut"),
        "tender": ("empuk", "daging lembut"),
        "chewy": ("kenyal",),
        "creamy": ("creamy", "lembut dan creamy"),
        "juicy": ("juicy", "berair"),
        "saucy": ("banyak saus", "bersaus", "sausnya banyak", "berkuah kental"),
        "dry": ("tidak berkuah", "tanpa kuah", "kering"),
        "brothy": ("berkuah", "kuah", "soto"),
        "boiled": ("rebus", "rebusan", "direbus", "boiled"),
        "chicken": ("ayam", "daging ayam", "olahan ayam"),
        "duck": ("bebek", "entok", "duck"),
        "beef": ("sapi", "daging sapi", "daging merah"),
        "seafood": ("seafood", "makanan laut"),
        "shrimp": ("udang",),
        "fish": ("ikan",),
        "egg": ("telur",),
        "tofu": ("tahu",),
        "tempeh": ("tempe",),
        "cheese": ("keju", "cheese", "mozzarella"),
        "rice": ("nasi",),
        "noodle": ("mie", "mi", "bakmi", "mi ayam"),
        "fried_rice": ("nasi goreng",),
        "fried_noodle": ("mie goreng", "mi goreng"),
        "soup": ("sup", "soto", "kuah kaldu"),
        "bread": ("roti",),
        "heavy_meal": ("makanan berat", "makan berat", "porsi besar", "makan besar", "berat"),
        "light_meal": ("makanan ringan", "makan ringan"),
        "snack": ("camilan", "cemilan", "snack", "ngemil", "makan dikit", "nyemil"),
        "dessert": ("dessert", "pencuci mulut", "hidangan penutup"),
        "drink": ("minuman", "minum", "haus", "tenggorokan kering"),
        "filling": (
            "kenyang",
            "mengenyangkan",
            "perut kosong",
            "belum makan",
            "lapar",
            "kelaparan",
            "butuh tenaga",
            "makan banyak",
        ),
        "light": ("ringan", "tidak terlalu lapar", "cuma sedikit"),
        "comfort_food": ("comfort food", "makanan rumahan", "makanan yang bikin happy"),
        "refreshing": ("segar", "nyegerin", "menyegarkan", "seger"),
        "warming": ("menghangatkan",),
        "satisfying": ("bikin puas", "memuaskan"),
        "hot": ("panas",),
        "warm": ("hangat", "anget"),
        "cold": ("dingin", "es", "sejuk"),
        "quick_meal": ("cepat", "buru-buru", "waktunya mepet", "jangan lama", "lagi sibuk"),
        "late_night": ("larut malam", "tengah malam", "begadang"),
        "breakfast": ("sarapan", "pagi-pagi"),
        "lunch": ("makan siang",),
        "dinner": ("makan malam",),
        "sharing": ("berbagi", "buat rame-rame", "untuk rame-rame"),
        "solo": ("sendirian", "porsi sendiri"),
    }

    def __init__(self) -> None:
        self.price_parser: IndonesianPriceParser = IndonesianPriceParser()
        self._aliases: dict[str, tuple[str, ...]] = {
            tag: tuple(sorted((normalize_text(alias) for alias in aliases), key=len, reverse=True))
            for tag, aliases in self.ALIASES.items()
        }

    def configure_catalog_tags(
        self,
        catalog_tags: Iterable[tuple[str, str]],
        catalog_aliases: Iterable[tuple[str, str]] = (),
    ) -> None:
        """Add current database tags and CMS-managed aliases."""
        aliases_by_tag: dict[str, set[str]] = {}

        for tag_name, phrase in catalog_aliases:
            aliases_by_tag.setdefault(tag_name, set()).add(phrase)

        for name, display_name in catalog_tags:
            aliases = set(self._aliases.get(name, ()))
            aliases.add(normalize_text(name.replace("_", " ")))

            if display_name:
                aliases.add(normalize_text(re.sub(r"[^\w\s]", " ", display_name)))

            aliases.update(normalize_text(alias) for alias in aliases_by_tag.get(name, ()))
            self._aliases[name] = tuple(
                sorted((alias for alias in aliases if alias), key=len, reverse=True)
            )
