import re


TAG_LABELS = {
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
    "chicken": "🍗 Ayam",
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


NORMALIZATION_RULES = (
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


def normalize_text(text):
    normalized = (text or "").lower().strip()
    for pattern, replacement in NORMALIZATION_RULES:
        normalized = re.sub(pattern, replacement, normalized)
    return re.sub(r"\s+", " ", normalized)


class IndonesianPriceParser:
    """Parse explicit Indonesian rupiah expressions into a maximum price."""

    AMOUNT_PATTERN = re.compile(
        r"(?:rp\.?\s*)?"
        r"(?P<amount>\d{1,3}(?:[.,]\d{3})+|\d{1,6})"
        r"\s*(?P<unit>ribu|rb|r\b|k\b)?",
        re.IGNORECASE,
    )
    BUDGET_CUES = (
        "budget",
        "maksimal",
        "maximal",
        "maks",
        "paling mahal",
        "di bawah",
        "dibawah",
        "kurang dari",
        "jangan lebih",
        "tidak lebih",
        "sekitar",
        "kisaran",
        "aja",
        "rupiah",
        "rp",
        "murah",
        "hemat",
        "mahal",
    )

    def parse_maximum(self, text):
        normalized = normalize_text(text)
        for match in self.AMOUNT_PATTERN.finditer(normalized):
            amount_text = match.group("amount")
            unit = match.group("unit")
            if not unit and not any(cue in normalized for cue in self.BUDGET_CUES):
                if not normalized.strip(" .,!") == amount_text:
                    continue
            amount = int(re.sub(r"[.,]", "", amount_text))
            if unit or amount < 1000:
                amount *= 1000
            if amount > 0:
                return amount
        return None

    @staticmethod
    def prefers_affordable(text):
        normalized = normalize_text(text)
        return any(
            phrase in normalized
            for phrase in ("murah", "hemat", "jangan mahal", "tidak mahal")
        )
