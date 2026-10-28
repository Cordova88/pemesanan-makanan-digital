from typing import ClassVar
import re
from decimal import Decimal

from .budget import BudgetConstraint, BudgetRequest, NumericMention

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
    """Parse explicit Indonesian rupiah expressions into a maximum price."""

    AMOUNT_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"(?<![\w.,])(?P<rp>rp\.?\s*)?"
        r"(?P<amount>\d{1,3}(?:[.,]\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
        r"\s*(?P<unit>ribuan|rupiah|ribu|juta|jt|rb|r|k)?(?!\w|[.,]\d)",
        re.IGNORECASE,
    )
    BUDGET_CUES: ClassVar[tuple[str, ...]] = (
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

    WORD_DIGITS: ClassVar[dict[str, int]] = {
        'nol': 0,
        'satu': 1,
        'dua': 2,
        'tiga': 3,
        'empat': 4,
        'lima': 5,
        'enam': 6,
        'tujuh': 7,
        'delapan': 8,
        'sembilan': 9,
        'sepuluh': 10,
        'sebelas': 11,
        'seratus': 100,
    }

    @classmethod
    def _word_integer(cls, text: str) -> int | None:
        words = text.split()

        if not words or len(words) > 6:
            return None

        total, previous = 0, 1000
        index = 0

        while index < len(words):
            value = cls.WORD_DIGITS.get(words[index])

            if value is None:
                return None

            if index + 1 < len(words) and words[index + 1] in {'belas', 'puluh', 'ratus'}:
                if not 1 <= value <= 9:
                    return None

                operator = words[index + 1]
                value = (
                    value + 10
                    if operator == 'belas'
                    else value * (10 if operator == 'puluh' else 100)
                )
                index += 1

            if value >= previous:
                return None

            total += value
            previous = 0 if 10 <= value < 20 else value
            index += 1

        return total if total <= 999 else None

    @classmethod
    def normalize_money_input(cls, text: str) -> str:
        normalized = normalize_text(text).replace('–', '-').replace('—', '-')
        normalized = re.sub(r'\bseribu\b', '1 ribu', normalized)
        normalized = re.sub(r'\bsejuta\b', '1 juta', normalized)
        vocabulary = '|'.join(cls.WORD_DIGITS) + '|belas|puluh|ratus'
        word_number = r'(?:' + vocabulary + r')(?:\s+(?:' + vocabulary + r')){0,5}'
        word_range = re.compile(
            r'\b('
            + word_number
            + r')\s+(sampai|hingga|s/d|-)\s+(?=(?:\d+(?:[.,]\d+)?|'
            + word_number
            + r')\s*(?:ribu(?:an)?|juta|rupiah|rb|k)\b)'
        )

        def replace_range(match: re.Match[str]) -> str:
            value = cls._word_integer(match[1])

            return f'{value} {match[2]} ' if value is not None else match[0]

        normalized = word_range.sub(replace_range, normalized)
        pattern = re.compile(r'\b((?:(?:' + vocabulary + r')\s+){1,6})(ribu(?:an)?|juta|rupiah)\b')

        def replace(match: re.Match[str]) -> str:
            value = cls._word_integer(match[1].strip())

            return f'{value} {match[2]}' if value is not None else match[0]

        return pattern.sub(replace, normalized)

    @staticmethod
    def _numeric_role(normalized: str, match: re.Match[str]) -> str:
        before, after = normalized[: match.start()], normalized[match.end() :]

        if (
            before.endswith(':')
            or after.startswith(':')
            or re.search(r'\b(?:jam|pukul)\s*$', before)
        ):
            return 'TIME'

        if re.match(r'\s*orang\b', after):
            return 'PERSON_COUNT'

        if re.match(r'\s*(?:porsi|item|menu)\b', after):
            return 'QUANTITY'

        if re.match(r'\s*(?:menit|jam|tahun|cm|ml|kg|gram|liter)\b', after):
            return 'MEASUREMENT'

        if re.match(r'\s*bintang\b', after) or re.search(r'\brating\s*$', before):
            return 'RATING'

        if re.search(r'\bmeja\s*(?:(?:nomor|no|aku)\s*)?$', before):
            return 'TABLE_NUMBER'

        if re.search(r'\b(?:nomor|no|menu ke)\s*(?:aku\s*)?$', before):
            return 'REFERENCE'

        if re.search(r'\bukuran\s*$', before):
            return 'MEASUREMENT'

        clause = re.split(r'[,;!?]|\b(?:tapi|namun|sedangkan)\b', before)[-1]
        explicit_budget = re.search(
            r'\b(?:budget\w*|anggaran|maks\w*|minimal|minimum|sekitar|kisaran)(?:\s+(?:makan(?:an)?|minum(?:an)?|menu|total|per|orang)){0,3}\s*$',
            clause,
        )

        if not explicit_budget and re.search(
            r'\b(?:punya|saldo\w*|uang\w*|gaji\w*|tabungan\w*|penghasilan\w*)\b', clause
        ):
            return 'PERSONAL_FINANCE'

        return 'OTHER'

    def numeric_roles(self, text: str) -> tuple[NumericMention, ...]:
        normalized = self.normalize_money_input(text)
        money = {match.span() for match in self._price_matches(normalized)}
        result = []

        for match in self.AMOUNT_PATTERN.finditer(normalized):
            role = 'MONEY' if match.span() in money else self._numeric_role(normalized, match)

            if role == 'OTHER' and re.match(
                r'\s+(?:es|jus|ayam|nasi|menu)\b', normalized[match.end() :]
            ):
                role = 'QUANTITY'

            value = (
                self._amount(match) if role == 'MONEY' else self._literal_amount(match['amount'])
            )
            result.append(NumericMention(value, role, match.start(), match.end()))

        vocabulary = '|'.join(self.WORD_DIGITS) + '|belas|puluh|ratus'

        for match in re.finditer(
            r'\b((?:'
            + vocabulary
            + r')(?:\s+(?:'
            + vocabulary
            + r')){0,5})\s+(orang|porsi|item|menu)\b',
            normalized,
        ):
            value = self._word_integer(match[1])

            if value is not None:
                result.append(
                    NumericMention(
                        Decimal(value),
                        'PERSON_COUNT' if match[2] == 'orang' else 'QUANTITY',
                        match.start(),
                        match.end(),
                    )
                )

        return tuple(sorted(result, key=lambda mention: mention.start))

    def parse_maximum(self, text: str) -> int | None:
        request = self.parse(text)

        return request.constraint.legacy_maximum if request.constraint is not None else None

    def without_prices(self, text: str) -> str:
        """Remove recognized money spans, retaining quantities and numbered names."""
        normalized = self.normalize_money_input(text)

        for match in reversed(self._price_matches(normalized)):
            normalized = normalized[: match.start()] + ' ' + normalized[match.end() :]

        return re.sub(r'\s+', ' ', normalized).strip()

    @staticmethod
    def _literal_amount(raw: str) -> Decimal:
        grouped = re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw) is not None

        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d{1,2}", raw):
            return Decimal(raw.replace(".", "").replace(",", "."))

        return Decimal(re.sub(r"[.,]", "", raw) if grouped else raw.replace(",", "."))

    @classmethod
    def _amount(cls, match: re.Match[str], inherited_unit: str | None = None) -> Decimal:
        raw = match.group('amount')
        grouped = re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw) is not None
        amount = cls._literal_amount(raw)
        unit = match.group("unit") or inherited_unit

        if (unit and unit != "rupiah") or (
            not unit and amount < 1000 and not match.group("rp") and not grouped
        ):
            amount *= 1_000_000 if unit in {"juta", "jt"} else 1000

        return amount

    def _price_matches(self, normalized: str) -> list[re.Match[str]]:
        matches: list[re.Match[str]] = []

        for match in self.AMOUNT_PATTERN.finditer(normalized):
            before, after = normalized[: match.start()], normalized[match.end() :]

            if self._numeric_role(normalized, match) != 'OTHER':
                continue

            if before.endswith(":") or after.startswith(":"):
                continue

            if re.match(r"\s*(?:orang|porsi|item|menu|menit|jam|tahun|bintang|cm|ml|kg)\b", after):
                continue

            if re.search(
                r"\b(?:meja|nomor|no|pukul|jam|rating|ukuran|menu ke)\s*(?:aku\s*)?$", before
            ):
                continue

            if re.search(r"\b(?:punya|saldo|uangku|uang)\s*$", before):
                continue

            explicit = bool(match.group("rp") or match.group("unit"))
            bare = normalized.strip(" .!?") == match.group("amount")
            nearby = re.search(
                r"\b(?:budget\w*|anggaran|maks\w*|minimal|minimum|di bawah|dibawah|di atas|diatas|kurang dari|lebih dari|sekitar|kisaran|kira[- ]kira|kurang lebih|antara|jangan lebih(?: dari)?|tidak lebih(?: dari)?|paling mahal)\s*$",
                before,
            )
            range_part = bool(
                matches
                and re.fullmatch(
                    r"\s*(?:-|sampai|hingga|s/d|dan)\s*",
                    normalized[matches[-1].end() : match.start()],
                )
            )
            range_start = bool(
                re.match(r"\s*(?:-|sampai|hingga)\s*\d+(?:[.,]\d+)?\s*(?:ribu|rb|k)\b", after)
            )
            food_price = (
                match.group('amount').isdigit()
                and len(match.group('amount').lstrip('0')) >= 4
                and re.search(
                    r'\b(?:makan(?:an)?|minum(?:an)?|menu|nasi|ayam|mie|mi|kopi|teh|jus|es|hidangan)\b',
                    before[-60:] + ' ' + after[:60],
                )
            )

            if (
                explicit
                or nearby
                or bare
                or range_part
                or range_start
                or food_price
                or re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", match.group("amount"))
            ):
                matches.append(match)

        return matches

    def parse(self, text: str) -> BudgetRequest:
        normalized = self.normalize_money_input(text)
        request = self._parse(normalized)
        request.numeric_roles = self.numeric_roles(normalized)

        return request

    def _parse(self, normalized: str) -> BudgetRequest:
        if re.search(r"\btermurah\b", normalized):
            return BudgetRequest("cheapest")

        if re.search(
            r"\b(?:hapus|hilangkan|abaikan|tanpa|bebas|tidak pakai)\s+(?:batas\s+)?(?:budget|anggaran|harga)\b",
            normalized,
        ):
            return BudgetRequest("clear")

        if re.search(r"\blebih murah\b", normalized):
            if re.search(r'\blebih murah (?:dari|daripada)\s*(?=(?:rp\.?\s*)?\d)', normalized):
                normalized = re.sub(r'\blebih murah (?:dari|daripada)\b', 'kurang dari', normalized)
            else:
                return BudgetRequest("cheaper")

        if re.search(r"\blebih mahal\b", normalized):
            if re.search(r'\blebih mahal (?:dari|daripada)\s*(?=(?:rp\.?\s*)?\d)', normalized):
                normalized = re.sub(r'\blebih mahal (?:dari|daripada)\b', 'lebih dari', normalized)
            else:
                return BudgetRequest("expensive")

        affordable = self.prefers_affordable(normalized)

        if re.search(
            r"(?:^|\b(?:budget|maksimal|minimal|rp\.?)\s*)(?:-|minus\s+)\s*\d", normalized
        ):
            return BudgetRequest(
                "invalid",
                clarification="Budget tidak boleh negatif. Berapa batas harga yang kamu inginkan?",
            )

        matches = self._price_matches(normalized)

        if not matches:
            return BudgetRequest("affordable" if affordable else "none")

        for position, match in enumerate(matches):
            prefix = normalized[: match.start()].rstrip()

            if prefix.endswith('-') or re.search(r'\bminus\s*$', prefix):
                bridge = normalized[matches[position - 1].end() : match.start()] if position else ''

                if not position or not re.fullmatch(r'\s*-\s*', bridge):
                    return BudgetRequest(
                        'invalid',
                        clarification='Budget tidak boleh negatif. Berapa harga yang dimaksud?',
                    )

        correction = len(matches) > 1 and bool(
            re.search(
                r"\b(?:tidak jadi|gajadi|maksudku|koreksi|ganti budget|ubah budget)\b", normalized
            )
        )

        if correction:
            matches = matches[-1:]

        group_scope = re.search(
            r"\b(?:berdua|bertiga|orang|per kepala)\b|\b(?:\d+|dua|tiga|empat|beberapa)\s*(?:porsi|menu|item)\b",
            normalized,
        )
        per_item = re.search(r"\bper\s+(?:menu|porsi|item)\b", normalized)
        categories = tuple(
            category
            for category, pattern in (
                ('Makanan', r'\bmakan(?:an)?\b'),
                ('Minuman', r'\bminum(?:an)?\b'),
                ('Camilan', r'\b(?:camilan|cemilan|snack)\b'),
            )
            if re.search(pattern, normalized)
        )
        overall = (
            bool(re.search(r'\b(?:total|seluruh|keseluruhan)\b', normalized)) or len(categories) > 1
        )
        approximate = bool(
            re.search(r'\b(?:sekitar|kisaran|kira[- ]kira|kurang lebih)\b', normalized)
        )

        if approximate:
            if len(matches) != 1 or (group_scope or overall) and not per_item:
                return BudgetRequest(
                    'ambiguous',
                    clarification='Perkiraan ini untuk harga per menu atau budget total? Sebutkan cakupannya; batas rencana sebelumnya tetap berlaku.',
                )

            if re.search(
                r'\b(?:maksimal|minimal|maksimum|minimum|di bawah|di atas|kurang dari|lebih dari)\b',
                normalized,
            ):
                return BudgetRequest(
                    'ambiguous',
                    clarification='Maksudnya perkiraan harga atau batas tegas? Sebutkan satu jenis batas agar tidak berubah keliru.',
                )

            try:
                return BudgetRequest('approximate', soft_target=self._amount(matches[0]))
            except ValueError as error:
                return BudgetRequest('invalid', clarification=str(error))

        if (group_scope or overall) and not per_item and len(matches) == 1:
            total = self._amount(matches[-1])

            try:
                BudgetConstraint(maximum=total)
            except ValueError as error:
                return BudgetRequest("invalid", clarification=str(error))

            people = [
                mention.value
                for mention in self.numeric_roles(normalized)
                if mention.role == 'PERSON_COUNT'
            ]

            if len(people) > 1 or any(value != value.to_integral_value() for value in people):
                return BudgetRequest(
                    'ambiguous',
                    clarification='Sebutkan satu jumlah orang yang utuh agar cakupan budget jelas.',
                )

            count = (
                int(people[0])
                if people
                else (2 if 'berdua' in normalized else 3 if 'bertiga' in normalized else None)
            )

            if count is not None and not 1 <= count <= 99:
                return BudgetRequest(
                    'invalid',
                    clarification='Jumlah orang harus antara 1 dan 99. Berapa jumlah yang dimaksud?',
                )

            scope = (
                'PER_PERSON'
                if re.search(r'\bper (?:orang|kepala)\b', normalized)
                else 'PLAN_TOTAL' if overall else 'GROUP_TOTAL'
            )

            return BudgetRequest(
                'total',
                scope=scope,
                amount=total,
                person_count=count,
                requested_categories=categories,
                clarification='Anggaran ini berlaku untuk rencana bersama, bukan otomatis batas per menu. Sebutkan menu atau jumlah porsi yang kamu inginkan.',
            )

        minimum: Decimal | None = None
        maximum: Decimal | None = None
        min_inclusive, max_inclusive = True, True
        kind = "maximum"

        if len(matches) == 2 and re.fullmatch(
            r"\s*(?:-|sampai|hingga|s/d|dan)\s*", normalized[matches[0].end() : matches[1].start()]
        ):
            minimum = self._amount(matches[0], matches[1].group("unit"))
            maximum = self._amount(matches[1], matches[0].group("unit"))
            kind = "range"
        else:
            lower_cue = re.search(r"\b(?:minimal|minimum|di atas|diatas|lebih dari)\b", normalized)
            upper_cue = re.search(
                r"\b(?:maksimal|maksimum|di bawah|dibawah|kurang dari|tidak lebih|jangan lebih)\b",
                normalized,
            )

            if len(matches) > 2 or (len(matches) > 1 and not (lower_cue and upper_cue)):
                return BudgetRequest(
                    "ambiguous",
                    clarification="Ada beberapa nominal harga. Sebutkan satu batas, atau rentang minimum sampai maksimum yang kamu inginkan.",
                )

            for match in matches:
                before = normalized[max(0, match.start() - 35) : match.start()]

                if re.search(
                    r"\b(?:minimal|minimum|di atas|diatas|lebih dari)\s*$", before
                ) and not re.search(r"\b(?:jangan|tidak)\s+lebih", before):
                    minimum = self._amount(match)
                    min_inclusive = not bool(
                        re.search(r"(?:di atas|diatas|lebih dari)\s*$", before)
                    )
                else:
                    maximum = self._amount(match)
                    max_inclusive = not bool(
                        re.search(r"(?:di bawah|dibawah|kurang dari)\s*$", before)
                    )

            kind = (
                "range"
                if minimum is not None and maximum is not None
                else "minimum" if minimum is not None else "maximum"
            )

        try:
            constraint = BudgetConstraint(
                minimum, maximum, minimum_inclusive=min_inclusive, maximum_inclusive=max_inclusive
            )
        except ValueError as error:
            return BudgetRequest("invalid", clarification=str(error))

        scope_ambiguous = bool(
            kind == 'maximum'
            and not per_item
            and not categories
            and re.fullmatch(
                r'(?:aku |saya )?(?:budget(?:ku)?|anggaran(?:ku)?)\s*'
                + re.escape(matches[0][0])
                + r'[.!?]*',
                normalized,
            )
        )

        return BudgetRequest(
            kind, constraint, correction=correction, scope_ambiguous=scope_ambiguous
        )

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
