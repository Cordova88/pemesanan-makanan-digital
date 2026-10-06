import re
from dataclasses import dataclass, field

from .language import IndonesianPriceParser, normalize_text


@dataclass
class Preferences:
    tags: set = field(default_factory=set)
    max_price: int | None = None
    mood_tags: set = field(default_factory=set)
    excluded_tags: set = field(default_factory=set)
    soft_excluded_tags: set = field(default_factory=set)
    category: str | None = None
    prefer_affordable: bool = False
    moods: set = field(default_factory=set)

    @property
    def all_positive_tags(self):
        return self.tags | self.mood_tags

    def to_dict(self, state="COLLECTING_PREFERENCES", follow_up=None):
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
    def from_dict(cls, data):
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

    ALIASES = {
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
        "brothy": ("berkuah", "kuah", "sup", "soto"),
        "chicken": ("ayam", "daging ayam", "olahan ayam"),
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

    STRONG_NEGATION = (
        "jangan", "tidak mau", "tidak ingin", "tidak suka", "tanpa", "hindari", "tidak"
    )
    SOFT_NEGATION = ("kurang suka", "tidak terlalu suka", "tidak kuat", "kurang kuat")
    CATEGORY_RULES = {
        "Minuman": ("minuman", "pengen minum", "ingin minum"),
        "Makanan": ("makanan", "masakan", "makan aja"),
    }

    def __init__(self):
        self.price_parser = IndonesianPriceParser()
        self._aliases = {
            tag: tuple(sorted((normalize_text(alias) for alias in aliases), key=len, reverse=True))
            for tag, aliases in self.ALIASES.items()
        }

    @staticmethod
    def _contains(text, phrase):
        return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text) is not None

    def _negation_for(self, text, alias):
        for cue in self.STRONG_NEGATION:
            pattern = rf"(?<!\w){re.escape(cue)}\s+(?:(?:yang|terlalu|banget)\s+){{0,2}}{re.escape(alias)}(?!\w)"
            if re.search(pattern, text):
                return "strong"
        for cue in self.SOFT_NEGATION:
            pattern = rf"(?<!\w){re.escape(cue)}\s+(?:(?:yang|terlalu|banget)\s+){{0,2}}{re.escape(alias)}(?!\w)"
            if re.search(pattern, text):
                return "soft"
        return None

    def extract(self, text):
        normalized = normalize_text(text)
        tags = set()
        excluded = set()
        soft_excluded = set()

        # Match longer phrases first so "sangat pedas" is also treated as spicy.
        for tag, aliases in self._aliases.items():
            for alias in aliases:
                if not self._contains(normalized, alias):
                    continue
                if tag == "tofu" and self._contains(normalized, "tidak tahu"):
                    continue
                negation = (
                    None
                    if tag == "mild" and alias.startswith("tidak ")
                    else self._negation_for(normalized, alias)
                )
                if negation == "strong":
                    excluded.add(tag)
                elif negation == "soft":
                    soft_excluded.add(tag)
                else:
                    tags.add(tag)

        if "very_spicy" in tags:
            tags.add("spicy")
        if "fried_rice" in tags:
            tags.update(("rice", "savory", "filling"))
        if "fried_noodle" in tags:
            tags.update(("noodle", "savory", "filling"))
        if "heavy_meal" in tags:
            tags.update(("filling",))
        if "light_meal" in tags:
            tags.update(("light",))

        tags -= excluded
        tags -= soft_excluded
        category = next(
            (
                category
                for category, phrases in self.CATEGORY_RULES.items()
                if any(self._contains(normalized, normalize_text(phrase)) for phrase in phrases)
            ),
            None,
        )
        max_price = self.price_parser.parse_maximum(normalized)
        return Preferences(
            tags=tags,
            excluded_tags=excluded,
            soft_excluded_tags=soft_excluded,
            max_price=max_price,
            category=category,
            prefer_affordable=self.price_parser.prefers_affordable(normalized),
        )
