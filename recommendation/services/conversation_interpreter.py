from __future__ import annotations

import re
from dataclasses import dataclass, field

from .language import normalize_text
from .mood_extractor import MoodExtractor
from .tag_extractor import TagExtractor


class ConversationIntent:
    RECOMMEND = "RECOMMEND"
    UPDATE_PREFERENCES = "UPDATE_PREFERENCES"
    REMOVE_PREFERENCES = "REMOVE_PREFERENCES"
    REPLACE_PREFERENCES = "REPLACE_PREFERENCES"
    SELECT_RECOMMENDATION = "SELECT_RECOMMENDATION"
    REJECT_RECOMMENDATION = "REJECT_RECOMMENDATION"
    CONFIRM = "CONFIRM"
    RESET = "RESET"
    GREETING = "GREETING"
    HELP = "HELP"
    UNKNOWN = "UNKNOWN"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(frozen=True)
class PreferenceOperation:
    action: str
    tags: tuple[str, ...] = ()
    remove_tags: tuple[str, ...] = ()


@dataclass
class ConversationInterpretation:
    intent: str
    operations: list[PreferenceOperation] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)
    excluded_tags: set[str] = field(default_factory=set)
    soft_excluded_tags: set[str] = field(default_factory=set)
    moods: set[str] = field(default_factory=set)
    max_price: int | None = None
    category: str | None = None
    prefer_affordable: bool = False
    last_question: str | None = None
    contextual_reference: str | None = None
    message_is_meaningful: bool = False
    follow_up: str | None = None
    clear_moods: bool = False


class ConversationInterpreter:
    RESET_PHRASES = {
        "reset",
        "mulai lagi",
        "mulai dari awal",
        "ulang dari awal",
        "lupa pilihan",
        "hapus pilihan sebelumnya",
        "hapus semua pilihan",
        "hapus pilihan",
    }
    GREETING_PHRASES = ("halo", "hai", "permisi", "hi", "selamat pagi", "selamat siang", "selamat sore")
    HELP_PHRASES = ("cara memakai", "cara pakai", "bisa bantu apa", "mau ngomong apa", "gimana caranya")
    REJECT_PHRASES = (
        "nggak cocok",
        "tidak cocok",
        "gak cocok",
        "bukan itu",
        "yang tadi nggak cocok",
        "tidak mau yang itu",
        "nggak mau yang itu",
        "jangan yang tadi",
        "cari yang lain",
        "cari menu lain",
        "menu lain",
        "yang lain",
        "yang lain dong",
        "lainnya",
        "rekomendasi lain",
        "ada yang lain",
    )
    CONFIRM_PHRASES = {"iya", "ya", "oke", "ok", "setuju", "betul", "yoi"}
    OUT_OF_SCOPE_HINTS = (
        "python",
        "javascript",
        "java",
        "presiden",
        "politik",
        "cuaca",
        "joke",
        "teori quantum",
        "cerita",
        "write code",
        "buatkan code",
    )

    def __init__(self):
        self.tag_extractor = TagExtractor()
        self.mood_extractor = MoodExtractor()

    def interpret(self, text, last_question=None, last_recommendations=None):
        normalized = normalize_text(text or "")
        last_recommendations = last_recommendations or []
        if not normalized:
            return ConversationInterpretation(
                intent=ConversationIntent.UNKNOWN,
                message_is_meaningful=False,
            )

        if any(self._contains_phrase(normalized, phrase) for phrase in self.RESET_PHRASES):
            return ConversationInterpretation(
                intent=ConversationIntent.RESET,
                message_is_meaningful=True,
                operations=[PreferenceOperation(action="CLEAR")],
            )

        if any(self._contains_phrase(normalized, phrase) for phrase in self.GREETING_PHRASES):
            return ConversationInterpretation(
                intent=ConversationIntent.GREETING,
                message_is_meaningful=False,
            )

        if any(self._contains_phrase(normalized, phrase) for phrase in self.HELP_PHRASES):
            return ConversationInterpretation(
                intent=ConversationIntent.HELP,
                message_is_meaningful=False,
            )

        if any(phrase in normalized for phrase in self.REJECT_PHRASES):
            return ConversationInterpretation(
                intent=ConversationIntent.REJECT_RECOMMENDATION,
                message_is_meaningful=True,
                operations=[PreferenceOperation(action="KEEP")],
            )

        reference = self._pick_reference(normalized)
        if reference:
            return ConversationInterpretation(
                intent=(
                    ConversationIntent.SELECT_RECOMMENDATION
                    if last_recommendations
                    else ConversationIntent.UNKNOWN
                ),
                contextual_reference=reference,
                message_is_meaningful=bool(last_recommendations),
            )

        if last_question and normalized in self.CONFIRM_PHRASES:
            return ConversationInterpretation(
                intent=ConversationIntent.CONFIRM,
                message_is_meaningful=True,
                last_question=last_question,
                operations=[PreferenceOperation(action="KEEP")],
            )

        if self._looks_out_of_scope(normalized):
            return ConversationInterpretation(
                intent=ConversationIntent.OUT_OF_SCOPE,
                message_is_meaningful=False,
            )

        extracted = self.tag_extractor.extract(normalized)
        tags = set(extracted.tags)
        moods = self.mood_extractor.extract(normalized)
        moods.discard("confused")
        clear_moods = self._clears_mood(normalized) or (
            "sekarang" in normalized
            and bool(tags.intersection({"refreshing", "cold", "hot", "warm", "warming"}))
        )
        if clear_moods:
            moods.discard("tired")

        excluded = set(extracted.excluded_tags)
        soft = set(extracted.soft_excluded_tags)
        max_price = (
            extracted.max_price
            if self._has_explicit_budget(normalized)
            else None
        )

        replacement = self._replacement_tags(normalized)
        intent = ConversationIntent.UPDATE_PREFERENCES
        if replacement:
            old_tags, new_tags = replacement
            operations = [
                PreferenceOperation(
                    action="REPLACE",
                    tags=tuple(sorted(new_tags)),
                    remove_tags=tuple(sorted(old_tags)),
                )
            ]
            tags = new_tags
            excluded = set()
            soft = set()
            intent = ConversationIntent.REPLACE_PREFERENCES
        elif excluded or soft:
            operations = [
                PreferenceOperation(action="REMOVE", tags=tuple(sorted(excluded)))
            ] if excluded else []
            if soft:
                operations.append(
                    PreferenceOperation(action="SOFT_REMOVE", tags=tuple(sorted(soft)))
                )
            if tags:
                operations.append(PreferenceOperation(action="ADD", tags=tuple(sorted(tags))))
            intent = ConversationIntent.REMOVE_PREFERENCES
        elif tags:
            operations = [PreferenceOperation(action="ADD", tags=tuple(sorted(tags)))]
            intent = ConversationIntent.RECOMMEND
        else:
            operations = []

        has_new_preference = bool(
            operations
            or moods
            or clear_moods
            or max_price is not None
            or extracted.prefer_affordable
            or extracted.category
        )
        if not has_new_preference:
            return ConversationInterpretation(
                intent=ConversationIntent.UNKNOWN,
                message_is_meaningful=False,
            )

        if intent not in {
            ConversationIntent.REMOVE_PREFERENCES,
            ConversationIntent.REPLACE_PREFERENCES,
        }:
            intent = (
                ConversationIntent.RECOMMEND
                if tags and not excluded and not soft
                else ConversationIntent.UPDATE_PREFERENCES
            )

        answer_removals = self._contextual_answer_removals(tags, last_question)
        if answer_removals and tags and not excluded and not soft and not replacement:
            operations = [
                PreferenceOperation(
                    action="REPLACE",
                    tags=tuple(sorted(tags)),
                    remove_tags=tuple(sorted(answer_removals)),
                )
            ]
            intent = ConversationIntent.REPLACE_PREFERENCES

        return ConversationInterpretation(
            intent=intent,
            operations=operations or [PreferenceOperation(action="KEEP")],
            tags=tags,
            excluded_tags=excluded,
            soft_excluded_tags=soft,
            moods=set(moods),
            max_price=max_price,
            category=extracted.category,
            prefer_affordable=extracted.prefer_affordable,
            message_is_meaningful=True,
            follow_up=self._detect_follow_up(normalized),
            clear_moods=clear_moods,
        )

    @staticmethod
    def _pick_reference(normalized):
        if any(phrase in normalized for phrase in ("yang pertama", "menu pertama", "nomor satu", "yang 1")):
            return "first"
        if any(phrase in normalized for phrase in ("yang kedua", "menu kedua", "nomor dua", "yang 2", "nomor 2")):
            return "second"
        if any(phrase in normalized for phrase in ("yang terakhir", "menu terakhir", "yang tadi")):
            return "last"
        return None

    @staticmethod
    def _contains_phrase(text, phrase):
        return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text) is not None

    @staticmethod
    def _has_explicit_budget(text):
        return any(
            phrase in text
            for phrase in (
                "rp",
                "ribu",
                " rb",
                " rib",
                "budget",
                "maks",
                "di bawah",
                "dibawah",
                "kurang dari",
                "jangan lebih",
                "tidak lebih",
                "sekitar",
                "kisaran",
                "murah",
                "hemat",
                "mahal",
            )
        ) or any(
            re.fullmatch(r"\d+(?:k|rb)", token) is not None
            for token in text.split()
        )

    def _replacement_tags(self, text):
        match = re.search(
            r"\b(?:ganti|ubah)\s+(?:yang\s+)?(.+?)\s+(?:jadi|menjadi|ke)\s+(.+)$",
            text,
        )
        if not match:
            return None
        old_tags = self.tag_extractor.extract(match.group(1)).tags
        new_tags = self.tag_extractor.extract(match.group(2)).tags
        if not old_tags or not new_tags:
            return None
        return old_tags, new_tags

    @staticmethod
    def _contextual_answer_removals(tags, last_question):
        dimensions = {
            "meal_type": {"heavy_meal", "light_meal", "snack", "filling", "light"},
            "base": {"rice", "noodle", "fried_rice", "fried_noodle"},
            "protein": {"chicken", "beef", "seafood", "shrimp", "fish", "egg", "tofu", "tempeh"},
        }
        dimension = dimensions.get(last_question)
        if not dimension or not tags.intersection(dimension):
            return set()
        return dimension - tags

    @staticmethod
    def _clears_mood(text):
        return any(
            phrase in text
            for phrase in (
                "tidak capek",
                "tidak lelah",
                "sudah tidak capek",
                "sudah tidak lelah",
                "udah tidak capek",
                "sekarang sudah baikan",
            )
        )

    @staticmethod
    def _detect_follow_up(text):
        normalized = normalize_text(text)
        if "makanan berat" in normalized or "makanan yang berat" in normalized:
            return "meal_type"
        if "nasi" in normalized or "mie" in normalized:
            return "base"
        return None

    @staticmethod
    def _looks_out_of_scope(text):
        return any(hint in text for hint in ConversationInterpreter.OUT_OF_SCOPE_HINTS)
