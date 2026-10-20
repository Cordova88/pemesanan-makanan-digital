from collections.abc import Sequence
import re
from types import NotImplementedType
from typing import ClassVar, cast

from .language import normalize_text
from .mood_extractor import MoodExtractor
from .tag_extractor import Preferences, TagExtractor


# Preserve the distinction between an omitted collection and explicit None.
_COLLECTION_DEFAULT: object = object()


class ConversationIntent:
    RECOMMEND: ClassVar[str] = "RECOMMEND"
    # Local coordinator outcomes; not added to the provider wire allowlist.
    UPDATE_PLAN: ClassVar[str] = "UPDATE_PLAN"
    UPDATE_BUDGET: ClassVar[str] = "UPDATE_BUDGET"
    UPDATE_PREFERENCES: ClassVar[str] = "UPDATE_PREFERENCES"
    REMOVE_PREFERENCES: ClassVar[str] = "REMOVE_PREFERENCES"
    REPLACE_PREFERENCES: ClassVar[str] = "REPLACE_PREFERENCES"
    CATALOG_QUESTION: ClassVar[str] = "CATALOG_QUESTION"
    RETRY_SEARCH: ClassVar[str] = "RETRY_SEARCH"
    SELECT_RECOMMENDATION: ClassVar[str] = "SELECT_RECOMMENDATION"
    REJECT_RECOMMENDATION: ClassVar[str] = "REJECT_RECOMMENDATION"
    REQUEST_ALTERNATIVES: ClassVar[str] = "REQUEST_ALTERNATIVES"
    CONFIRM: ClassVar[str] = "CONFIRM"
    RESET: ClassVar[str] = "RESET"
    GREETING: ClassVar[str] = "GREETING"
    HELP: ClassVar[str] = "HELP"
    UNKNOWN: ClassVar[str] = "UNKNOWN"
    OUT_OF_SCOPE: ClassVar[str] = "OUT_OF_SCOPE"


class PreferenceOperation:
    """Read-only preference delta; collections remain tuples as before."""

    __slots__ = ("__action", "__tags", "__remove_tags")
    __match_args__: ClassVar[tuple[str, ...]] = ("action", "tags", "remove_tags")

    def __init__(
        self,
        action: str,
        tags: tuple[str, ...] = (),
        remove_tags: tuple[str, ...] = (),
    ) -> None:
        self.__action: str = action
        self.__tags: tuple[str, ...] = tags
        self.__remove_tags: tuple[str, ...] = remove_tags

    @property
    def action(self) -> str:
        return self.__action

    @property
    def tags(self) -> tuple[str, ...]:
        return self.__tags

    @property
    def remove_tags(self) -> tuple[str, ...]:
        return self.__remove_tags

    def __eq__(self, other: object) -> bool | NotImplementedType:
        if not isinstance(other, PreferenceOperation) or type(self) is not type(other):
            return NotImplemented
        return (self.action, self.tags, self.remove_tags) == (
            other.action, other.tags, other.remove_tags,
        )

    def __hash__(self) -> int:
        return hash((self.action, self.tags, self.remove_tags))

    def __repr__(self) -> str:
        return (
            f"{type(self).__qualname__}(action={self.action!r}, "
            f"tags={self.tags!r}, remove_tags={self.remove_tags!r})"
        )


class ConversationInterpretation:
    """Mutable interpreter result with independent default collections."""

    __match_args__: ClassVar[tuple[str, ...]] = (
        "intent", "operations", "tags", "excluded_tags", "soft_excluded_tags",
        "moods", "max_price", "category", "prefer_affordable", "last_question",
        "contextual_reference", "message_is_meaningful", "follow_up",
        "clear_moods", "clear_max_price", "clear_prefer_affordable",
        "contextual_revision", "catalog_tags",
    )
    __hash__ = None

    def __init__(
        self,
        intent: str,
        operations: list[PreferenceOperation] = cast(list[PreferenceOperation], _COLLECTION_DEFAULT),
        tags: set[str] = cast(set[str], _COLLECTION_DEFAULT),
        excluded_tags: set[str] = cast(set[str], _COLLECTION_DEFAULT),
        soft_excluded_tags: set[str] = cast(set[str], _COLLECTION_DEFAULT),
        moods: set[str] = cast(set[str], _COLLECTION_DEFAULT),
        max_price: int | None = None,
        category: str | None = None,
        prefer_affordable: bool = False,
        last_question: str | None = None,
        contextual_reference: str | None = None,
        message_is_meaningful: bool = False,
        follow_up: str | None = None,
        clear_moods: bool = False,
        clear_max_price: bool = False,
        clear_prefer_affordable: bool = False,
        contextual_revision: bool = False,
        catalog_tags: set[str] = cast(set[str], _COLLECTION_DEFAULT),
        target_menu_id: int | None = None,
        rejected_menu_ids: tuple[int, ...] = (),
        source: str = 'local',
        *, context_action: str | None = None, constraint_scope: str | None = None,
    ) -> None:
        self.intent: str = intent
        self.operations: list[PreferenceOperation] = [] if operations is _COLLECTION_DEFAULT else operations
        self.tags: set[str] = set() if tags is _COLLECTION_DEFAULT else tags
        self.excluded_tags: set[str] = set() if excluded_tags is _COLLECTION_DEFAULT else excluded_tags
        self.soft_excluded_tags: set[str] = set() if soft_excluded_tags is _COLLECTION_DEFAULT else soft_excluded_tags
        self.moods: set[str] = set() if moods is _COLLECTION_DEFAULT else moods
        self.max_price: int | None = max_price
        self.category: str | None = category
        self.prefer_affordable: bool = prefer_affordable
        self.last_question: str | None = last_question
        self.contextual_reference: str | None = contextual_reference
        self.message_is_meaningful: bool = message_is_meaningful
        self.follow_up: str | None = follow_up
        self.clear_moods: bool = clear_moods
        self.clear_max_price: bool = clear_max_price
        self.clear_prefer_affordable: bool = clear_prefer_affordable
        self.contextual_revision: bool = contextual_revision
        self.catalog_tags: set[str] = set() if catalog_tags is _COLLECTION_DEFAULT else catalog_tags
        if target_menu_id is not None and (type(target_menu_id) is not int or target_menu_id <= 0):
            raise ValueError('Invalid catalog target')
        if source not in {'local', 'gemini'} or any(type(value) is not int or value <= 0 for value in rejected_menu_ids):
            raise ValueError('Invalid interpretation metadata')
        self.target_menu_id: int | None = target_menu_id
        self.rejected_menu_ids: tuple[int, ...] = tuple(dict.fromkeys(rejected_menu_ids))
        self.source: str = source
        if context_action is not None and context_action not in {'CONTINUE_CONTEXT', 'SWITCH_CONTEXT', 'NEW_REQUEST', 'ADD_TO_CONTEXT', 'CORRECT_PREVIOUS', 'REFER_TO_PREVIOUS', 'CLARIFY'}:
            raise ValueError('Invalid context action')
        if constraint_scope is not None and constraint_scope not in {'CURRENT_SEARCH', 'SPECIFIC_ITEM', 'PLAN_TOTAL', 'SAFETY_RESTRICTION'}:
            raise ValueError('Invalid constraint scope')
        self.context_action: str | None = context_action
        self.constraint_scope: str | None = constraint_scope

    def __eq__(self, other: object) -> bool | NotImplementedType:
        if not isinstance(other, ConversationInterpretation) or type(self) is not type(other):
            return NotImplemented
        return all(getattr(self, name) == getattr(other, name) for name in self.__match_args__) and (
            self.target_menu_id, self.rejected_menu_ids, self.source, self.context_action, self.constraint_scope,
        ) == (other.target_menu_id, other.rejected_menu_ids, other.source, other.context_action, other.constraint_scope)

    def __repr__(self) -> str:
        fields = ", ".join(f"{name}={getattr(self, name)!r}" for name in self.__match_args__)
        return f"{type(self).__qualname__}({fields})"


class ConversationInterpreter:
    @staticmethod
    def context_operation(text: str, *, category: str | None, previous_category: str | None,
                          has_active: bool, has_target: bool, plan_active: bool = False) -> tuple[str, str | None]:
        """Semantic transition policy; catalog identity/category are supplied by backend."""
        normalized = normalize_text(text)
        if re.search(r'\b(?:balik|kembali)\s+(?:ke\s+)?', normalized):
            reference = 'first' if re.search(r'\b(?:awal|pertama)\b', normalized) else category
            return 'REFER_TO_PREVIOUS', reference
        if re.search(r'\b(?:sekalian|tambahkan|tambah(?:in)?|juga)\b', normalized):
            return 'ADD_TO_CONTEXT', None
        correction = bool(re.search(r'\b(?:eh|maksudku|maksudnya|koreksi|bukan|ganti|tidak jadi)\b', normalized))
        if correction:
            return 'CORRECT_PREVIOUS', None
        if category and previous_category and category.casefold() != previous_category.casefold():
            return 'SWITCH_CONTEXT', None
        if has_target and re.search(r'\b(?:sekarang|permintaan baru)\b', normalized):
            return 'NEW_REQUEST', None
        if not has_active:
            return 'NEW_REQUEST', None
        return 'CONTINUE_CONTEXT', None
    RESET_PHRASES: ClassVar[set[str]] = {
        "reset",
        "mulai lagi",
        "mulai dari awal",
        "ulang dari awal",
        "lupa pilihan",
        "hapus pilihan sebelumnya",
        "hapus semua pilihan",
        "hapus pilihan",
    }
    GREETING_PHRASES: ClassVar[tuple[str, ...]] = ("halo", "hai", "permisi", "hi", "selamat pagi", "selamat siang", "selamat sore")
    HELP_PHRASES: ClassVar[tuple[str, ...]] = ("cara memakai", "cara pakai", "bisa bantu apa", "mau ngomong apa", "gimana caranya")
    REJECT_PHRASES: ClassVar[tuple[str, ...]] = (
        "nggak cocok",
        "tidak cocok",
        "gak cocok",
        "bukan itu",
        "yang tadi nggak cocok",
        "tidak mau yang itu",
        "nggak mau yang itu",
        "jangan yang tadi",
    )
    ALTERNATIVE_PHRASES: ClassVar[tuple[str, ...]] = (
        "cari yang lain",
        "cari menu lain",
        "menu lain",
        "yang lain",
        "yang lain dong",
        "lainnya",
        "rekomendasi lain",
        "ada yang lain",
    )
    CONFIRM_PHRASES: ClassVar[set[str]] = {"iya", "ya", "oke", "ok", "setuju", "betul", "yoi"}
    PREFERENCE_CORRECTION_CUES: ClassVar[tuple[str, ...]] = (
        "gajadi",
        "gak jadi",
        "nggak jadi",
        "tidak jadi",
        "salah",
        "maksudku",
        "maksudnya",
    )
    OUT_OF_SCOPE_HINTS: ClassVar[tuple[str, ...]] = (
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

    def __init__(self, tag_extractor: TagExtractor | None=None) -> None:
        self.tag_extractor: TagExtractor = tag_extractor or TagExtractor()
        self.mood_extractor: MoodExtractor = MoodExtractor()

    def interpret(
        self,
        text: str,
        last_question: str | None = None,
        last_recommendations: Sequence[int] | None = None,
        last_result_empty: bool = False,
    ) -> ConversationInterpretation:
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

        tag_revision = self._tag_revision(normalized)
        if tag_revision is not None:
            return tag_revision

        if any(phrase in normalized for phrase in self.REJECT_PHRASES):
            return ConversationInterpretation(
                intent=ConversationIntent.REJECT_RECOMMENDATION,
                message_is_meaningful=True,
                operations=[PreferenceOperation(action="KEEP")],
            )
        if any(self._contains_phrase(normalized, phrase) for phrase in self.ALTERNATIVE_PHRASES):
            return ConversationInterpretation(
                intent=ConversationIntent.REQUEST_ALTERNATIVES,
                message_is_meaningful=True,
                operations=[PreferenceOperation(action='KEEP')],
            )

        reference = self._pick_reference(normalized)
        if reference:
            if self._is_contextual_revision(normalized):
                return ConversationInterpretation(
                    intent=ConversationIntent.UNKNOWN,
                    message_is_meaningful=True,
                    contextual_revision=bool(last_recommendations or last_question),
                    contextual_reference=reference,
                )
            return ConversationInterpretation(
                intent=(
                    ConversationIntent.SELECT_RECOMMENDATION
                    if last_recommendations
                    else ConversationIntent.UNKNOWN
                ),
                contextual_reference=reference,
                message_is_meaningful=bool(last_recommendations),
            )

        if self._is_no_results_challenge(normalized, last_result_empty):
            extracted = self.tag_extractor.extract(normalized)
            if extracted.tags:
                return ConversationInterpretation(
                    intent=ConversationIntent.RETRY_SEARCH,
                    operations=[
                        PreferenceOperation(
                            action="ADD",
                            tags=tuple(sorted(extracted.tags)),
                        )
                    ],
                    tags=set(extracted.tags),
                    excluded_tags=set(extracted.excluded_tags),
                    soft_excluded_tags=set(extracted.soft_excluded_tags),
                    max_price=extracted.max_price,
                    category=extracted.category,
                    prefer_affordable=extracted.prefer_affordable,
                    message_is_meaningful=True,
                    catalog_tags=set(extracted.tags),
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

        extracted = self._extract_preferences(normalized)
        tags = set(extracted.tags)
        if self._is_catalog_question(normalized) and tags:
            return ConversationInterpretation(
                intent=ConversationIntent.CATALOG_QUESTION,
                tags=tags,
                excluded_tags=set(extracted.excluded_tags),
                soft_excluded_tags=set(extracted.soft_excluded_tags),
                max_price=extracted.max_price,
                category=extracted.category,
                catalog_tags=tags,
                message_is_meaningful=True,
            )

        moods = self.mood_extractor.extract(normalized)
        moods.discard("confused")
        moods.discard("low_mood")
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
            operations: list[PreferenceOperation] = []

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

        is_explicit_correction = any(
            cue in normalized for cue in self.PREFERENCE_CORRECTION_CUES
        )
        if is_explicit_correction and not replacement:
            operations = [
                PreferenceOperation(action="CLEAR"),
                *(
                    operation
                    for operation in operations
                    if operation.action != "KEEP"
                ),
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
            contextual_revision=bool(excluded or soft or replacement or re.match(r"^(?:yang|tapi|namun)\b", normalized)),
        )

    def _tag_revision(self, text: str) -> ConversationInterpretation | None:
        """Targeted local edits do not erase unrelated tags or monetary bounds."""
        if re.fullmatch(r"(?:hapus|bersihkan|reset) (?:semua )?(?:tag|selera)(?: makanan)?", text):
            return ConversationInterpretation(
                ConversationIntent.REMOVE_PREFERENCES,
                operations=[PreferenceOperation("CLEAR_TAGS")],
                message_is_meaningful=True, contextual_revision=True,
            )
        match = re.fullmatch(r"(?:hapus|buang|lupakan) (?:preferensi |tag )?(.+?)(?: saja)?", text)
        action = "DROP"
        if not match:
            match = re.fullmatch(r"(?:yang\s+)?(.+?)\s+(?:nanti(?:\s+(?:aja|saja))?|ditunda(?:\s+dulu)?)", text)
        if not match and not re.search(r"\b(?:mau|ingin)\b", text):
            match = re.fullmatch(r"(?:tidak jadi|gajadi|gak jadi|ga jadi|nggak jadi|enggak jadi)\s+([^,;]+)", text)
        if not match:
            match = re.fullmatch(r"(?:boleh|boleh pakai|tidak apa-apa pakai) (.+?)(?: lagi)?", text)
            action = "RELAX"
        if not match:
            match = re.fullmatch(r"(?:sekarang\s+)?(.+?)\s+(?:sudah\s+)?boleh(?:\s+lagi)?", text)
            action = "RELAX"
        if not match:
            match = re.fullmatch(r"sekarang\s+boleh(?:\s+pakai)?\s+(.+)", text)
            action = "RELAX"
        if match:
            tags = self.tag_extractor.extract(match.group(1)).tags
            if tags:
                return ConversationInterpretation(
                    ConversationIntent.REMOVE_PREFERENCES,
                    operations=[PreferenceOperation(action, tuple(sorted(tags)))],
                    message_is_meaningful=True, contextual_revision=True,
                )
        # A reference with a catalog-specific tag has enough local evidence.
        # Keep legacy ambiguous references delegated rather than guessing tags.
        extracted = self._extract_preferences(text)
        dynamic = (extracted.tags | extracted.excluded_tags | extracted.soft_excluded_tags) - set(TagExtractor.ALIASES)
        if self._pick_reference(text) and (dynamic or extracted.excluded_tags):
            return ConversationInterpretation(
                ConversationIntent.REMOVE_PREFERENCES,
                operations=[PreferenceOperation("REMOVE", tuple(sorted(extracted.excluded_tags))),
                            PreferenceOperation("SOFT_REMOVE", tuple(sorted(extracted.soft_excluded_tags))),
                            PreferenceOperation("ADD", tuple(sorted(extracted.tags)))],
                tags=set(extracted.tags), excluded_tags=set(extracted.excluded_tags),
                soft_excluded_tags=set(extracted.soft_excluded_tags),
                message_is_meaningful=True, contextual_revision=True,
            )
        return None

    def _extract_preferences(self, text: str) -> Preferences:
        extracted = self.tag_extractor.extract(text)
        context = self.mood_extractor.extract_context(text)
        # Negating a physical condition is not a permanent food prohibition.
        for condition, tag, explicit in (
            ('thirsty', 'drink', r'\b(?:minum|minuman)\b'),
            ('hungry', 'filling', r'\b(?:makanan|kenyang|mengenyangkan)\b'),
        ):
            if condition in context.cleared_physical and not re.search(explicit, text):
                extracted.excluded_tags.discard(tag)
                extracted.soft_excluded_tags.discard(tag)
        return extracted

    @staticmethod
    def _pick_reference(normalized: str) -> str | None:
        if any(phrase in normalized for phrase in ("yang pertama", "menu pertama", "nomor satu", "yang 1")):
            return "first"
        if any(phrase in normalized for phrase in ("yang kedua", "menu kedua", "nomor dua", "yang 2", "nomor 2")):
            return "second"
        if any(phrase in normalized for phrase in ("yang terakhir", "menu terakhir", "yang tadi")):
            return "last"
        return None

    @staticmethod
    def _is_contextual_revision(text: str) -> bool:
        revision_cues = (
            "terlalu",
            "lebih",
            "kurang",
            "ganti",
            "ubah",
            "mirip",
            "tapi",
            "namun",
        )
        return any(cue in text for cue in revision_cues)

    @staticmethod
    def _is_no_results_challenge(text: str, last_result_empty: bool) -> bool:
        challenge_cues = (
            "masa tidak ada",
            "masa gak ada",
            "masa nggak ada",
            "kok tidak ada",
            "kok gak ada",
            "kok nggak ada",
            "memang tidak ada",
            "emang gak ada",
            "serius tidak ada",
            "serius gak ada",
            "serius nggak ada",
        )
        return last_result_empty and any(
            cue in text for cue in challenge_cues
        )

    @staticmethod
    def _contains_phrase(text: str, phrase: str) -> bool:
        return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text) is not None

    @staticmethod
    def _has_explicit_budget(text: str) -> bool:
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

    def _replacement_tags(self, text: str) -> tuple[set[str], set[str]] | None:
        match = re.search(
            r"\b(?:ganti|ubah)\s+(?:yang\s+)?(.+?)\s+(?:jadi|menjadi|ke)\s+(.+)$",
            text,
        )
        if not match:
            match = re.search(r"\b(?:tidak jadi|gajadi)\s+(.+?)[,;]?\s+(?:aku\s+)?(?:mau|ingin)\s+(.+)$", text)
        if not match:
            return None
        old_tags = self.tag_extractor.extract(match.group(1)).tags
        new_tags = self.tag_extractor.extract(match.group(2)).tags
        if not old_tags or not new_tags:
            return None
        return old_tags, new_tags

    @staticmethod
    def _contextual_answer_removals(tags: set[str], last_question: str | None) -> set[str]:
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
    def _clears_mood(text: str) -> bool:
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
    def _detect_follow_up(text: str) -> str | None:
        normalized = normalize_text(text)
        if "makanan berat" in normalized or "makanan yang berat" in normalized:
            return "meal_type"
        if "nasi" in normalized or "mie" in normalized:
            return "base"
        return None

    @staticmethod
    def _looks_out_of_scope(text: str) -> bool:
        return any(hint in text for hint in ConversationInterpreter.OUT_OF_SCOPE_HINTS)

    @staticmethod
    def _is_catalog_question(text: str) -> bool:
        explicit_question_cues = (
            "apa aja",
            "apa saja",
            "ada menu",
            "ada pilihan",
            "ada gak",
            "ada nggak",
            "ada tidak",
        )
        return any(cue in text for cue in explicit_question_cues) or (
            "pilihan" in text and ("apa" in text or "?" in text)
        )
