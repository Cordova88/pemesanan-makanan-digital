from typing import ClassVar
from collections.abc import Iterable
from .language import normalize_text
import re


class UserContext:
    def __init__(
        self, emotions: Iterable[str] = (), physical: Iterable[str] = (),
        situations: Iterable[str] = (), cleared_physical: Iterable[str] = (),
    ) -> None:
        self.emotions: frozenset[str] = frozenset(emotions)
        self.physical: frozenset[str] = frozenset(physical)
        self.situations: frozenset[str] = frozenset(situations)
        self.cleared_physical: frozenset[str] = frozenset(cleared_physical)

    @property
    def has_context(self) -> bool:
        return bool(self.emotions or self.physical or self.situations or self.cleared_physical)


class MoodExtractor:
    EMOTIONS: ClassVar[dict[str, tuple[str, ...]]] = {
        "sad": ("sedih", "bad mood", "bete", "lagi down"),
        "happy": ("senang", "happy", "bahagia", "gembira"),
        "stressed": ("stres", "stress", "tertekan"),
        "frustrated": ("kesal", "frustrasi", "marah"),
        "disappointed": ("kecewa",),
    }
    PHYSICAL: ClassVar[dict[str, tuple[str, ...]]] = {
        "tired": ("capek", "cape", "lelah", "kecapekan", "energi habis", "butuh tenaga"),
        "hungry": ("lapar", "kelaparan", "perut kosong", "belum makan"),
        "thirsty": ("haus", "tenggorokan kering"),
        "hot": ("gerah", "kepanasan", "panas banget", "lagi panas"),
    }
    SITUATIONS: ClassVar[dict[str, tuple[str, ...]]] = {
        "hurry": ("buru-buru", "waktunya mepet", "jangan lama", "lagi sibuk"),
        "working": ("kerja", "bekerja"),
        "studying": ("kuliah", "belajar"),
        "with_friends": ("bareng teman", "bersama teman"),
    }
    PHRASES: ClassVar[dict[str, tuple[str, ...]]] = {
        "tired": (
            "capek", "cape", "lelah", "kecapekan", "habis kerja",
            "baru pulang kerja", "hari ini berat", "energi habis",
            "butuh tenaga", "capek banget",
        ),
        "low_mood": (
            "bad mood", "bete", "sedih", "lagi down", "hari ini jelek",
            "pengen dimanjain", "butuh comfort food", "lagi tidak mood",
            "makanan yang bikin happy", "sesuatu yang enak",
        ),
        "very_hungry": (
            "lapar banget", "lapar parah", "lapar gila", "kelaparan",
            "perut kosong", "belum makan seharian", "belum makan dari tadi",
            "laper parah",
        ),
        "hot_thirsty": (
            "haus", "gerah", "kepanasan", "panas banget",
            "tenggorokan kering", "lagi panas",
        ),
        "quick": (
            "buru-buru", "waktunya mepet", "mau yang cepat",
            "butuh makan cepat", "jangan lama", "lagi sibuk",
        ),
        "confused": (
            "gak tahu", "tidak tahu", "ga tau", "gatau", "bingung",
            "terserah", "bebas", "pilihin", "apa saja", "apa aja",
        ),
    }

    def extract(self, text: str) -> set[str]:
        normalized = normalize_text(text)
        normalized = re.split(r"\bsekarang\b", normalized)[-1]
        moods: set[str] = set()
        for mood, phrases in self.PHRASES.items():
            if any(self._active(normalized, normalize_text(phrase)) for phrase in phrases):
                moods.add(mood)
        context = self.extract_context(normalized)
        if "tired" not in context.physical:
            moods.discard("tired")
        if {"thirsty", "hot"} & context.cleared_physical and not ({"thirsty", "hot"} & context.physical):
            moods.discard("hot_thirsty")
        if "hungry" in context.cleared_physical:
            moods.discard("very_hungry")
        return moods

    @classmethod
    def _active(cls, text: str, phrase: str) -> bool:
        matches = list(re.finditer(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text))
        return bool(matches) and not bool(re.search(r"\b(?:(?:tidak|bukan|belum)\s+(?:(?:lagi|sedang|merasa|terlalu|sangat|begitu)\s+){0,3}|(?:bikin|membuat|supaya|agar|biar)\s+(?:aku\s+)?)$", text[:matches[-1].start()]))

    def extract_context(self, text: str) -> UserContext:
        normalized = normalize_text(text)
        full = normalized
        normalized = re.split(r"\bsekarang\b", normalized)[-1]
        emotions = {kind for kind, phrases in self.EMOTIONS.items() if any(self._active(normalized, phrase) for phrase in phrases)}
        physical: set[str] = set()
        cleared: set[str] = set()
        for kind, phrases in self.PHYSICAL.items():
            if any(self._contains(full, phrase) and not self._active(full, phrase) for phrase in phrases):
                cleared.add(kind)
        for kind, phrases in self.PHYSICAL.items():
            for phrase in phrases:
                if not self._contains(normalized, phrase):
                    continue
                if self._active(normalized, phrase):
                    physical.add(kind)
                else:
                    cleared.add(kind)
        situations = {kind for kind, phrases in self.SITUATIONS.items() if any(self._active(normalized, phrase) for phrase in phrases)}
        return UserContext(emotions, physical, situations, cleared)

    @staticmethod
    def _contains(text: str, phrase: str) -> bool:
        return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text) is not None
