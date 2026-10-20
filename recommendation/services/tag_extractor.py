from collections.abc import Iterable
import re
from types import NotImplementedType
from typing import TYPE_CHECKING, ClassVar, Self, TypedDict, cast

from .language import IndonesianPriceParser, normalize_text
from .mood_resolver import MoodResolver

if TYPE_CHECKING:
    from .conversation_interpreter import ConversationInterpretation


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
        "tags", "max_price", "mood_tags", "excluded_tags", "soft_excluded_tags",
        "category", "prefer_affordable", "moods",
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
        self.excluded_tags: set[str] = set() if excluded_tags is _COLLECTION_DEFAULT else excluded_tags
        self.soft_excluded_tags: set[str] = set() if soft_excluded_tags is _COLLECTION_DEFAULT else soft_excluded_tags
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

    def apply_interpretation(
        self,
        interpretation: "ConversationInterpretation",
        mood_resolver: MoodResolver,
    ) -> None:
        """Apply a preference delta, preserving operation order and mood rules.

        The orchestrator handles RESET and non-preference intents before calling
        this method. Tag conflict cleanup runs after the complete operation list.
        """
        moods = set(interpretation.moods)
        for operation in interpretation.operations:
            op = operation.action
            tags = set(operation.tags)
            if op == "ADD":
                self.tags.update(tags)
                self.excluded_tags.difference_update(tags)
                self.soft_excluded_tags.difference_update(tags)
            elif op == "REMOVE":
                self.tags.difference_update(tags)
                self.excluded_tags.update(tags)
                self.soft_excluded_tags.difference_update(tags)
            elif op == "SOFT_REMOVE":
                self.tags.difference_update(tags)
                self.soft_excluded_tags.update(tags)
                self.excluded_tags.difference_update(tags)
            elif op == "REPLACE":
                self.tags.difference_update(operation.remove_tags)
                self.tags.update(tags)
                self.excluded_tags.difference_update(tags)
                self.soft_excluded_tags.difference_update(tags)
                self.excluded_tags.difference_update(operation.remove_tags)
                self.soft_excluded_tags.difference_update(operation.remove_tags)
            elif op == "DROP":
                self.tags.difference_update(tags)
            elif op == "RELAX":
                self.excluded_tags.difference_update(tags)
                self.soft_excluded_tags.difference_update(tags)
            elif op == "CLEAR_TAGS":
                self.tags.clear()
                self.excluded_tags.clear()
                self.soft_excluded_tags.clear()
            elif op == "CLEAR":
                self.tags.clear()
                self.excluded_tags.clear()
                self.soft_excluded_tags.clear()
                self.moods.clear()
                self.max_price = None
                self.category = None
                self.prefer_affordable = False
        if interpretation.clear_moods:
            self.moods.clear()
        if moods:
            self.moods = moods
        self.tags.difference_update(self.excluded_tags | self.soft_excluded_tags)
        self.mood_tags = mood_resolver.resolve(self.moods)
        self.max_price = interpretation.max_price
        self.category = interpretation.category
        if interpretation.prefer_affordable:
            self.prefer_affordable = True
        if interpretation.clear_max_price:
            self.max_price = None
        if interpretation.clear_prefer_affordable:
            self.prefer_affordable = False

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
    """Extract direct food preferences and explicit dislikes from Indonesian text."""

    ALIASES: ClassVar[dict[str, tuple[str, ...]]] = {
        "spicy": (
            "pedas", "sambal", "sambalnya", "cabai", "cabe", "nampol", "nendang",
            "bikin melek", "rasa yang kuat", "rasa kuat",
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
            "kenyang", "mengenyangkan", "perut kosong", "belum makan",
            "lapar", "kelaparan", "butuh tenaga", "makan banyak",
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

    ALLERGY_INGREDIENT_TAGS: ClassVar[frozenset[str]] = frozenset({
        'shrimp', 'seafood', 'fish', 'egg', 'chicken', 'beef', 'duck', 'cheese', 'tofu', 'tempeh',
    })

    STRONG_NEGATION: ClassVar[tuple[str, ...]] = (
        "jangan", "tidak mau", "tidak ingin", "tidak suka", "tanpa", "hindari", "tidak"
    )
    SOFT_NEGATION: ClassVar[tuple[str, ...]] = ("kurang suka", "tidak terlalu suka", "tidak kuat", "kurang kuat")
    CATEGORY_RULES: ClassVar[dict[str, tuple[str, ...]]] = {
        "Minuman": ("minuman", "pengen minum", "ingin minum", "mau minum"),
        "Makanan": ("makanan", "masakan", "makan aja", "makan saja", "hidangan", "mau makan", "ingin makan", "pengen makan"),
    }

    def __init__(self) -> None:
        self.price_parser: IndonesianPriceParser = IndonesianPriceParser()
        self._aliases: dict[str, tuple[str, ...]] = {
            tag: tuple(sorted((normalize_text(alias) for alias in aliases), key=len, reverse=True))
            for tag, aliases in self.ALIASES.items()
        }
        self._category_rules: dict[str, tuple[str, ...]] = dict(self.CATEGORY_RULES)

    def configure_categories(self, categories: Iterable[str]) -> None:
        """Resolve categories from active catalog labels, including custom ones."""
        self._category_rules = {}
        vocabulary = dict(self.CATEGORY_RULES)
        vocabulary['Camilan'] = ('camilan', 'cemilan', 'ngemil', 'nyemil', 'snack')
        for name in categories:
            phrases = vocabulary.get(name, ()) + (normalize_text(name),)
            self._category_rules[name] = tuple(dict.fromkeys(normalize_text(phrase) for phrase in phrases))

    def category_terms(self) -> set[str]:
        return {phrase for phrases in self._category_rules.values() for phrase in phrases}

    def get_allowed_tags(self) -> set[str]:
        """Return catalog-aware tag names without exposing the alias mapping."""
        return set(self._aliases)

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
            aliases.update(
                normalize_text(alias)
                for alias in aliases_by_tag.get(name, ())
            )
            self._aliases[name] = tuple(
                sorted((alias for alias in aliases if alias), key=len, reverse=True)
            )

    @staticmethod
    def _contains(text: str, phrase: str) -> bool:
        return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text) is not None

    def _negation_for(self, text: str, alias: str) -> str | None:
        # Evaluate the current occurrence, including a shared cue in a list.
        # A later positive clause can explicitly correct a previous exclusion.
        prefix = re.split(r"[,;.!?]|\b(?:tapi|namun|sekarang)\b", text)[-1]
        if re.search(r"\b(?:jangan|tidak)\s+(?:yang\s+)?terlalu\s+$", prefix):
            return "soft"
        if re.search(r"\bterlalu\s+$", prefix):
            return "soft"
        for cue in self.SOFT_NEGATION:
            if re.search(rf"\b{re.escape(cue)}\s+(?:(?:yang|terlalu|banget)\s+){{0,2}}$", prefix):
                return "soft"
        if re.search(r"\b(?:kurang suka|tidak terlalu suka|tidak kuat|kurang kuat)\s+.+\s+(?:dan|atau)\s+$", prefix):
            return "soft"
        for cue in self.STRONG_NEGATION:
            if re.search(rf"\b{re.escape(cue)}\s+(?:(?:yang|terlalu|banget)\s+){{0,2}}$", prefix):
                return "strong"
        if re.search(r"\b(?:jangan|tanpa|hindari|tidak (?:mau|ingin|suka))\s+(?!.*\b(?:mau|ingin|boleh|pakai)\b).+\s+(?:dan|atau)\s+$", prefix):
            return "strong"
        return None

    def extract_allergy_tags(self, text: str) -> set[str]:
        """Recognize explicit ingredient lists, never tags from a menu question.

        Unknown phrases stay unresolved; callers must retain staff verification.
        Use ingredient vocabulary, not catalog aliases that may name whole dishes.
        """
        normalized = normalize_text(text)
        clauses = re.split(r'\b(?:alergi|allergy|allergic|alergen)\b', normalized)[1:]
        ingredients: set[str] = set()
        for clause in clauses:
            # A comma can introduce a question about a single-ingredient menu
            # too ("alergi telur, ayam aman?"), not another declared allergen.
            clause = re.sub(
                r',\s*[^,.;!?]*\b(?:aman|boleh|apakah|bagaimana|gimana|mau|ingin)\b.*$',
                '', clause,
            )
            declaration = re.split(
                r'[.;!?]|\b(?:tapi|tetapi|namun|apakah|bagaimana|gimana|kalau|'
                r'boleh|aman|mau|ingin|rekomendasikan|jadi|sedangkan)\b', clause, maxsplit=1,
            )[0]
            declaration = declaration.strip(' :')
            declaration = re.sub(r'^(?:terhadap|dengan|pada|to)\s+', '', declaration)
            for phrase in re.split(r'[,/&]|\b(?:dan|serta)\b', declaration):
                phrase = re.sub(r'\s+(?:ya|nih|dong|sih)$', '', phrase.strip())
                for tag in self.ALLERGY_INGREDIENT_TAGS:
                    if phrase in self.ALIASES[tag]:
                        ingredients.add(tag)
        return ingredients

    def extract(self, text: str) -> Preferences:
        normalized = normalize_text(text)
        normalized = re.sub(r"\bada tidak\b", "ada", normalized)
        tags: set[str] = set()
        excluded: set[str] = set()
        soft_excluded: set[str] = set()

        mentions: dict[str, tuple[int, str | None]] = {}
        for tag, aliases in self._aliases.items():
            for alias in aliases:
                for match in re.finditer(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", normalized):
                    prefix = normalized[:match.start()]
                    if tag == "tofu" and re.search(r"\btidak\s+$", prefix):
                        continue
                    negation = None if tag == "mild" and alias.startswith("tidak ") else self._negation_for(prefix, alias)
                    if tag not in mentions or match.start() > mentions[tag][0]:
                        mentions[tag] = (match.start(), negation)
        for tag, (_, negation) in mentions.items():
            (excluded if negation == "strong" else soft_excluded if negation == "soft" else tags).add(tag)

        # Compound expressions must not create opposite requirements.
        if "dry" in tags:
            tags.discard("brothy")
            excluded.discard("brothy")
        if "mild" in tags:
            tags.discard("spicy")
            if "spicy" in excluded | soft_excluded:
                tags.discard("mild")
        if "light" in tags and self._contains(normalized, "tidak terlalu lapar"):
            soft_excluded.discard("filling")

        if "very_spicy" in tags:
            tags.add("spicy")
        if "fried_rice" in tags:
            tags.add("rice")
        if "fried_noodle" in tags:
            tags.add("noodle")
        if "heavy_meal" in tags:
            tags.update(("filling",))
        if "light_meal" in tags:
            tags.update(("light",))

        tags -= excluded
        tags -= soft_excluded
        category_mentions = []
        for name, phrases in self._category_rules.items():
            for phrase in phrases:
                for match in re.finditer(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', normalized):
                    prefix, suffix = normalized[:match.start()], normalized[match.end():]
                    if self._negation_for(prefix, phrase) is not None:
                        continue
                    if re.search(r'\b(?:sudah|habis|baru|setelah)\s*(?:(?:makan|minum)\s*)?$', prefix):
                        continue
                    if phrase.endswith(('makan', 'minum')) and re.match(r'\s+apa\b', suffix):
                        continue
                    category_mentions.append((len(phrase), match.start(), name))
        category = max(category_mentions)[2] if category_mentions else None
        if category and category not in self.CATEGORY_RULES and category != 'Camilan':
            # A category label is structural evidence, not an extra required tag.
            # Keep separate preferences: "dessert manis" still requires sweet.
            label = normalize_text(category)
            for tag, aliases in self._aliases.items():
                if label in aliases and not any(
                    self._contains(normalized, alias) for alias in aliases if alias != label
                ):
                    tags.discard(tag)
        max_price = self.price_parser.parse_maximum(normalized)
        return Preferences(
            tags=tags,
            excluded_tags=excluded,
            soft_excluded_tags=soft_excluded,
            max_price=max_price,
            category=category,
            prefer_affordable=self.price_parser.prefers_affordable(normalized),
        )
