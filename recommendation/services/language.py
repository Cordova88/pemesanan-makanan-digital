import re

TAG_LABELS: dict[str, str] = {
    "spicy": "🌶️ Pedas",
    "very_spicy": "🔥 Sangat pedas",
    "savory": "🧂 Gurih",
    "sweet": "🍯 Manis",
    "sour": "🍋 Asam segar",
    "salty": "🧂 Asin",
    "umami": "😋 Kaya rasa",
    "rich": "🧈 Kaya rasa",
    "mild": "🌿 Tidak terlalu pedas",
    "crispy": "✨ Renyah",
    "crunchy": "🥨 Garing",
    "soft": "☁️ Lembut",
    "tender": "🍖 Empuk",
    "chewy": "🍡 Kenyal",
    "creamy": "🥛 Lembut dan kental",
    "juicy": "💧 Berair",
    "saucy": "🍛 Berbumbu",
    "dry": "🍽️ Tidak berkuah",
    "brothy": "🍲 Berkuah",
    "boiled": "🍲 Rebus",
    "chicken": "🍗 Ayam",
    "duck": "🦆 Bebek",
    "beef": "🥩 Sapi",
    "seafood": "🦐 Hasil laut",
    "shrimp": "🦐 Udang",
    "fish": "🐟 Ikan",
    "egg": "🥚 Telur",
    "tofu": "🟨 Tahu",
    "tempeh": "🟫 Tempe",
    "cheese": "🧀 Keju",
    "rice": "🍚 Nasi",
    "noodle": "🍜 Mie",
    "fried_rice": "🍳 Nasi goreng",
    "fried_noodle": "🍝 Mie goreng",
    "soup": "🍲 Sup",
    "bread": "🍞 Roti",
    "heavy_meal": "🍱 Makanan berat",
    "light_meal": "🥗 Makanan ringan",
    "snack": "🍟 Camilan",
    "dessert": "🍰 Hidangan manis",
    "drink": "🥤 Minuman",
    "filling": "🍚 Mengenyangkan",
    "light": "🥗 Ringan",
    "comfort_food": "😌 Makanan yang bikin nyaman",
    "refreshing": "✨ Menyegarkan",
    "warming": "🔥 Menghangatkan",
    "satisfying": "😋 Bikin puas",
    "hot": "♨️ Panas",
    "warm": "🌤️ Hangat",
    "cold": "🧊 Dingin",
    "quick_meal": "⚡ Cepat disajikan",
    "late_night": "🌙 Cocok malam hari",
    "breakfast": "🌅 Sarapan",
    "lunch": "☀️ Makan siang",
    "dinner": "🌆 Makan malam",
    "sharing": "👥 Cocok untuk berbagi",
    "solo": "🍽️ Porsi sendiri",
}


def tag_label(tag: str) -> str:
    """Return a readable label for built-in and staff-created tags."""

    return TAG_LABELS.get(tag, tag.replace("_", " ").strip().title())


NORMALIZATION_RULES: tuple[tuple[str, str], ...] = (
    (r"\b(?:gue|gua|gw)\b", "aku"),
    (r"\b(?:enggak|nggak|ngga|gak|ga|gk)\b", "tidak"),
    (r"\bgatau\b", "tidak tahu"),
    (r"\b(?:lg|lagi2)\b", "lagi"),
    (r"\b(?:bgt|bangettt+)\b", "banget"),
    (r"\b(?:yg|yng)\b", "yang"),
    (r"\b(?:pengen|pengin|pgn)\b", "ingin"),
    (r"\bpedes\b", "pedas"),
    (r"\blaper\b", "lapar"),
    (r"\bkelaperan\b", "kelaparan"),
    (r"\btau\b", "tahu"),
    (r"\bnyemil\b", "ngemil"),
    (r"\bnyari\b", "cari"),
    (r"\bcepet\b", "cepat"),
    (r"\bseger\b", "segar"),
    (r"\banget banget\b", "banget"),
)


def normalize_text(text: str) -> str:
    normalized = (text or "").lower().strip()

    for pattern, replacement in NORMALIZATION_RULES:
        normalized = re.sub(pattern, replacement, normalized)

    return re.sub(r"\s+", " ", normalized)


class IndonesianPriceParser:
    """Recognize wording that asks for the cheapest suitable option."""

    @staticmethod
    def prefers_affordable(text: str) -> bool:
        normalized = normalize_text(text)

        return any(
            phrase in normalized
            for phrase in (
                "murah",
                "hemat",
                "jangan mahal",
                "tidak mahal",
                "ramah di kantong",
                "ramah dikantong",
                "pas di kantong",
                "pas dikantong",
                "pas di dompet",
                "terjangkau",
                "ekonomis",
            )
        )
