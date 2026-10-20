"""Catalog identity and bounded domain interpretation; never trusts AI stock/prices."""

from collections.abc import Collection, Iterable
from difflib import SequenceMatcher
import re
from typing import ClassVar

from .language import IndonesianPriceParser, normalize_text


class EntityResolution:
    def __init__(
        self,
        requested_entity: str,
        domain_status: str,
        entity_type: str,
        menu_ids: tuple[int, ...] = (),
        rejected_menu_ids: tuple[int, ...] = (),
        modifiers: str | None = None,
    ) -> None:
        self.requested_entity: str = requested_entity
        self.domain_status: str = domain_status
        self.entity_type: str = entity_type
        self.menu_ids: tuple[int, ...] = menu_ids
        self.rejected_menu_ids: tuple[int, ...] = rejected_menu_ids
        self.modifiers: str | None = modifiers


class EntityResolver:
    # Small offline examples, not an attempt to enumerate all products/foods.
    NON_FOOD: ClassVar[set[str]] = {"motor", "mobil", "bantal", "guling", "laptop", "helm"}
    FOOD: ClassVar[set[str]] = {"sushi", "pizza", "ramen", "tepung"}
    DOMAIN_TYPES: ClassVar[dict[str, set[str]]] = {
        "NON_FOOD_OUT_OF_SCOPE": {"product"},
        "FOOD_BUT_NOT_AVAILABLE": {"food", "beverage"},
        "RESTAURANT_INFORMATION": {"information"},
        "AMBIGUOUS_REQUEST": {"unknown"},
    }

    def __init__(
        self,
        catalog: Iterable[tuple[int, str]],
        known_terms: Collection[str] = (),
        *,
        aliases: Iterable[tuple[int, str]] = (),
    ) -> None:
        self._catalog: tuple[tuple[int, str], ...] = tuple(
            (identifier, normalize_text(name)) for identifier, name in catalog
        )
        self._known_terms: set[str] = {normalize_text(term) for term in known_terms}
        self._price_parser: IndonesianPriceParser = IndonesianPriceParser()
        self._aliases: tuple[tuple[int, str], ...] = tuple(
            (identifier, normalize_text(phrase))
            for identifier, phrase in aliases
            if phrase and len(phrase) <= 100
        )
        self._partials: tuple[tuple[int, str], ...] = self._partial_names()

    def _partial_names(self) -> tuple[tuple[int, str], ...]:
        generic = {
            'es',
            'jus',
            'paket',
            'menu',
            'porsi',
            'makanan',
            'minuman',
            'murah',
            'mahal',
            'hemat',
        }
        result: set[tuple[int, str]] = set()

        for identifier, name in self._catalog:
            words = name.split()

            for size in range(1, min(len(words), 4) + 1):
                for start in range(len(words) - size + 1):
                    phrase = ' '.join(words[start : start + size])

                    if (
                        phrase != name
                        and len(phrase) >= 3
                        and not phrase.isdecimal()
                        and phrase not in self._known_terms
                        and phrase not in generic
                        and not all(
                            word in generic or word in self._known_terms for word in phrase.split()
                        )
                    ):
                        result.add((identifier, phrase))

        return tuple(sorted(result))

    def _partial_request_supported(self, text: str) -> bool:
        """Don't turn an unknown compound (kelapa quantum) into a real item."""
        remainder = text
        phrases = self._known_terms | {
            name for _, name in self._catalog + self._aliases + self._partials
        }

        for phrase in sorted(phrases, key=len, reverse=True):
            remainder = re.sub(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', ' ', remainder)

        remainder = self._price_parser.without_prices(remainder)
        remainder = re.sub(
            r'\b(?:aku|saya|kami|apakah|ingin|mau|minta|pesan|beli|jual|ada|punya|tersedia|yang|'
            r'ganti|maksudku|maksudnya|bukan|jangan|tanpa|tidak|suka|jadi|sekalian|tambahkan|'
            r'sekarang|balik|kembali|ke|dengan|bagaimana|gimana|kalau|untuk|aja|saja|deh|dong|ya|nih|'
            r'eh|oh|oke|baiklah|tadi|sebelumnya|dan|atau|tapi|makan|minum|habis|baru|setelah|sudah|'
            r'budget|anggaran|maksimal|minimal|di|bawah|atas|antara|sampai|sekitar|kisaran|kira|kurang|lebih)\b',
            ' ',
            remainder,
        )

        return not re.sub(r'[\s,;.!?–-]', '', remainder)

    def _catalog_request(self, text: str) -> EntityResolution | None:
        """Resolve mentioned identities before descriptive tags, respecting clause roles."""
        mentions: list[tuple[int, int, str, tuple[int, ...]]] = []
        sources = (
            self._catalog,
            self._aliases,
            self._partials if self._partial_request_supported(text) else (),
        )
        known_spans = [
            (match.start(), match.end())
            for term in self._known_terms
            for match in re.finditer(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text)
        ]

        for level, source in enumerate(sources):
            for name in sorted(
                {name for _, name in source}, key=lambda value: (-len(value), value)
            ):
                if name in self._known_terms and ' ' not in name:
                    continue

                for match in re.finditer(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text):
                    if level == 2 and any(
                        match.start() < end and match.end() > start for start, end in known_spans
                    ):
                        continue

                    if any(
                        match.start() < end and match.end() > start for start, end, _, _ in mentions
                    ):
                        continue

                    ids = tuple(
                        dict.fromkeys(
                            identifier for identifier, item_name in source if item_name == name
                        )
                    )
                    mentions.append((match.start(), match.end(), name, ids))

        if not mentions:
            return None

        positive: list[tuple[str, tuple[int, ...]]] = []
        rejected: list[int] = []

        for start, end, name, ids in sorted(mentions):
            prefix = text[:start]
            clause = re.split(r'[,;.!?]', prefix)[-1]

            if re.search(
                r'\b(?:bukan|jangan|tanpa|tidak(?: jadi| mau| ingin)|tidak suka)\s*(?:yang\s+)?$',
                clause,
            ):
                rejected.extend(ids)
                continue

            if re.search(r'\b(?:habis|baru|setelah|sudah)\s+(?:makan|minum|pesan)\s*$', clause):
                continue

            if re.search(r'\bganti\s*$', clause) and re.match(
                r'\s+(?:ke|dengan|jadi)\b', text[end:]
            ):
                continue

            selection = re.search(
                r'\b(?:(?:bagaimana|gimana)\s+(?:dengan|kalau)|ingin|mau|minta|pesan|beli|jual|ada|punya|pilih|ambil|yang|ganti|maksudku|maksudnya|bukan|sekalian|tambahkan|sekarang|kalau|balik|kembali)\b',
                prefix,
            )
            bare_name = not text[:start].strip() and not text[end:].strip(' ?!.,')
            corrected = bool(rejected) and (
                not clause.strip()
                or bool(re.search(r'\b(?:aja|saja|deh|pilih|mau|ingin)\b', text[end:]))
            )
            filler_prefix = re.sub(r'^(?:(?:eh|oh|oke|baiklah)[\s,!]*)+', '', prefix).strip()
            filler_selection = not filler_prefix and bool(
                re.fullmatch(r'\s*(?:(?:aja|saja|deh|dong|ya|nih)\s*)*[.!?]*', text[end:])
            )
            suffix = text[end:]
            # Recognize a bounded catalog question, not an arbitrary trailing clause.
            availability_question = (
                re.fullmatch(r'\s*(?:apakah\s+)?', prefix) is not None
                and re.fullmatch(r'\s+(?:ada|tersedia)\s*[.!?]*', suffix) is not None
            )
            budget_words = re.sub(
                r'\b(?:budget|anggaran|dengan|maksimal|minimal|di bawah|di atas|antara|sampai|dan|sekitar|kisaran|kira kira|kurang lebih)\b|[-–]',
                ' ',
                self._price_parser.without_prices(suffix),
            ).strip(' ?!.,')
            price_request = self._price_parser.parse('menu ' + suffix)
            priced_selection = (
                not filler_prefix
                and not budget_words
                and (price_request.constraint is not None or price_request.soft_target is not None)
            )

            if (
                selection
                or bare_name
                or corrected
                or filler_selection
                or priced_selection
                or availability_question
            ):
                positive.append((name, ids))

        unique_ids = tuple(dict.fromkeys(identifier for _, ids in positive for identifier in ids))
        rejected_ids = tuple(dict.fromkeys(rejected))
        modifiers = text

        for start, end, _, _ in sorted(mentions, reverse=True):
            modifiers = modifiers[:start] + ' ' + modifiers[end:]

        if len(unique_ids) == 1:
            name = next(name for name, ids in positive if unique_ids[0] in ids)

            return EntityResolution(
                name,
                'IN_CATALOG',
                'menu_item',
                unique_ids,
                tuple(identifier for identifier in rejected_ids if identifier not in unique_ids),
                modifiers,
            )

        if unique_ids:
            return EntityResolution(
                ' / '.join(dict.fromkeys(name for name, _ in positive)),
                'AMBIGUOUS_CATALOG',
                'unknown',
                unique_ids[:8],
            )

        if rejected_ids:
            return EntityResolution(
                'menu yang disebutkan',
                'REJECTED_CATALOG',
                'menu_item',
                rejected_menu_ids=rejected_ids,
                modifiers=modifiers,
            )

        return None

    @staticmethod
    def is_past_consumption(text: str) -> bool:
        normalized = normalize_text(text)
        consumed = re.search(
            r'\b(?:sudah|habis|baru|setelah)\s+(?:makan|minum|pesan)\b', normalized
        )

        return bool(
            consumed
            and not re.search(
                r'\b(?:mau|ingin|minta|pilih|ambil|cari|pesan|ada)\b', normalized[consumed.end() :]
            )
        )

    def resolve(self, text: str) -> EntityResolution | None:
        normalized = normalize_text(text)
        normalized = re.sub(r"^(?:halo|hai|permisi)[,!\s]+", "", normalized)
        normalized = re.sub(r'^kalau\s+(?:gitu|begitu)\s+', '', normalized)

        if re.search(
            r"\b(?:parkir|pengantar(?:nya)?|pengantaran|pesanan|pengiriman)\b", normalized
        ):
            if re.search(r"\b(?:di mana|dimana|sudah|kapan|bagaimana|gimana)\b", normalized):
                return EntityResolution("layanan restoran", "RESTAURANT_INFORMATION", "information")

        catalog_request = self._catalog_request(normalized)

        if catalog_request is not None:
            return catalog_request

        if self.is_past_consumption(normalized):
            return None

        match = re.search(
            r"^(?:apakah\s+)?(?:(?:aku|saya|kami)\s+)?(?:ingin|mau|minta|pesan|beli|jual|ada|punya|yang|kalau)\s+(?:tidak\s+)?(.+)",
            normalized,
        )

        if not match:
            if re.search(r"\b(?:habis|setelah|baru)\b", normalized) and re.search(
                r"\blapar\b", normalized
            ):
                return EntityResolution("makanan", "GENERAL_CONVERSATION", "context")

            return None

        candidate = match.group(1).strip(" ?!.,")
        candidate = re.sub(r"^(?:(?:beli|membeli|pesan|memesan|makan|minum)\s+)+", "", candidate)
        candidate = re.sub(r"\s+di sini$", "", candidate)
        candidate = re.split(r"\s+rp\.?\s*(?=\d)", candidate)[0]
        candidate = re.sub(r"\s+(?:dong|ya|nih|kah)$", "", candidate)
        candidate = re.split(
            r"\s+(?:di bawah|dibawah|di atas|diatas|maksimal|minimal|antara|kisaran|anggaran|budget|(?:tapi\s+)?(?:tanpa|jangan))\b",
            candidate,
        )[0]

        if not candidate or len(candidate) > 100:
            return None

        # Negations/corrections remain the responsibility of preference interpretation.
        if re.search(r"\b(?:tidak|ganti|jadi|tapi|atau|dan)\b", candidate):
            return None

        # Preserve real numbered catalog names, but don't mistake a budget for
        # part of the requested product: "minuman 10.000" means a price filter.
        if not any(candidate == name for _, name in self._catalog):
            candidate = self._price_parser.without_prices(candidate).strip(' ?!.,')

        if not candidate:
            return None

        # A generic one-word tag such as "nasi" keeps the preference workflow,
        # even when a catalog item happens to have the same generic name.
        if " " not in candidate and candidate in self._known_terms:
            return None

        exact = tuple(identifier for identifier, name in self._catalog if candidate == name)

        if exact:
            return EntityResolution(candidate, "IN_CATALOG", "menu_item", exact)

        # "yang ..." is an identity request only when the catalog confirms the
        # whole name. Positional, relative-price and preference references stay
        # with the conversation interpreter; don't send them to classification.
        if normalized.startswith('yang '):
            return None

        if candidate in self._known_terms or candidate.startswith(("yang ", "sesuatu ")):
            return None

        remainder = candidate

        for term in sorted(self._known_terms, key=len, reverse=True):
            remainder = re.sub(r"(?<!\w)" + re.escape(term) + r"(?!\w)", " ", remainder)

        remainder = re.sub(
            r"\b(?:yang|enak|agak|banget|sekali|sedikit|aja|saja|paling|dengan|untuk|pakai|makanan|minuman|ada|apa|dong)\b",
            " ",
            remainder,
        )

        if not remainder.strip():
            return None

        scores = sorted(
            (
                (SequenceMatcher(None, candidate, name).ratio(), name)
                for _, name in self._catalog
                if len(candidate) >= 6 and len(candidate.split()) == len(name.split())
            ),
            reverse=True,
        )

        if (
            scores
            and scores[0][0] >= 0.88
            and (len(scores) == 1 or scores[0][0] - scores[1][0] >= 0.08)
        ):
            name = scores[0][1]
            ids = tuple(identifier for identifier, item_name in self._catalog if item_name == name)

            return EntityResolution(candidate, "IN_CATALOG", "menu_item", ids)

        if candidate in self.NON_FOOD:
            return EntityResolution(candidate, "NON_FOOD_OUT_OF_SCOPE", "product")

        if candidate in self.FOOD:
            return EntityResolution(candidate, "FOOD_BUT_NOT_AVAILABLE", "food")

        return EntityResolution(candidate, "AMBIGUOUS_REQUEST", "unknown")

    @classmethod
    def validate_ai(cls, data: object, requested_entity: str) -> EntityResolution | None:
        if not isinstance(data, dict) or set(data) != {
            "requested_entity",
            "domain_status",
            "entity_type",
        }:
            return None

        if data["requested_entity"] != requested_entity:
            return None

        domain, kind = data["domain_status"], data["entity_type"]

        if not isinstance(domain, str) or not isinstance(kind, str):
            return None

        if kind not in cls.DOMAIN_TYPES.get(domain, set()):
            return None

        # Provider cannot return IDs, availability, prices or IN_CATALOG.
        return EntityResolution(requested_entity, domain, kind)
