from menu.models import MenuTag

from .conversation_interpreter import ConversationInterpreter, ConversationIntent
from .conversation.context import ConversationContext
from .conversation.preferences import PreferenceStateService
from .language import TAG_LABELS, normalize_text, tag_label
from .mood_extractor import MoodExtractor
from .mood_resolver import MoodResolver
from .recommendation import RecommendationService, SearchConstraints
from .tag_extractor import Preferences, TagExtractor
from .ai.GeminiInterpreter import GeminiInterpreter
from .ai.assistant import GeminiAssistant
from .ai.conversation import ConversationDirector
from .ai.explanations import RecommendationExplanationService
from .ai.responses import ConversationResponseService
from .gemini import GeminiClient


# [OOP: Abstraction] ChatbotService berperan sebagai fasad: view cukup memanggil reply();
# seluruh alur (normalisasi, ekstraksi tag/mood, ranking, penjelasan AI) disembunyikan di baliknya.
# [OOP: Composition] Memiliki (has-a) TagExtractor, MoodExtractor, MoodResolver,
# RecommendationService, ConversationInterpreter, GeminiClient, GeminiInterpreter, dan
# RecommendationExplanationService; semuanya dibuat di __init__ dan tugasnya didelegasikan.
# [OOP: Encapsulation] State percakapan disimpan di session lewat konstanta kunci
# (SESSION_KEY, SHOWN_KEY, dst.); method berawalan _ adalah bagian internal class.
class ChatbotService:
    # [OOP: Class attribute] Kunci session dan daftar frasa (RESET_PHRASES, MORE_PHRASES,
    # GEMINI_FOOD_CUES, dst.) milik class dan dipakai bersama semua objek, bukan state per instance.
    RESET_PHRASES = {"reset", "mulai lagi", "mulai dari awal"}
    CONFUSION_PHRASES = {
        "bingung",
        "gatau",
        "ga tau",
        "gak tau",
        "tidak tahu",
        "terserah",
        "terserah deh",
        "nggak tau",
        "susah pilih",
        "mau makan apa",
    }
    MORE_PHRASES = {
        "cari yang lain",
        "cari menu lain",
        "menu lain",
        "yang lain",
        "lainnya",
        "rekomendasi lain",
    }
    OPEN_FOLLOWUP_ANSWERS = {
        "bebas",
        "bebas aja",
        "bebas saja",
        "bebas kok",
        "apa aja",
        "apa saja",
        "terserah",
        "terserah deh",
        "mana aja",
        "mana saja",
    }
    GEMINI_FOOD_CUES = (
        "makan", "menu", "masakan", "minum", "ayam", "sapi", "nasi",
        "mie", "pedas", "manis", "gurih", "berat", "ringan", "murah",
        "mahal", "kenyang", "nagih", "eneg", "pengen", "mau", "cari",
        "ada yang", "mirip",
    )
    GEMINI_UNCERTAIN_CUES = (
        "berminyak",
        "berminya",
        "eneg",
        "bikin nagih",
    )
    SESSION_KEY = ConversationContext.SESSION_KEY
    SHOWN_KEY = ConversationContext.SHOWN_KEY
    SEARCH_KEY = ConversationContext.SEARCH_KEY
    LAST_RESULT_EMPTY_KEY = ConversationContext.LAST_RESULT_EMPTY_KEY
    # [OOP: Composition] Semua komponen dibuat di sini sebagai atribut instance (has-a).
    # [OOP: Dependency Injection] Satu GeminiClient dibagikan ke GeminiInterpreter dan
    # RecommendationExplanationService lewat parameter konstruktor.
    # [OOP: Association] session disuntikkan dari luar (request.session); class tidak membuatnya sendiri.
    def __init__(self, session):
        self.session = session
        self.context = ConversationContext(session)
        self.preference_state = PreferenceStateService(self.context)
        self.tag_extractor = TagExtractor()
        catalog_tags = MenuTag.objects.filter(
            menu_items__is_active=True,
            menu_items__category__is_active=True,
        ).values_list("name", "display_name").distinct()
        catalog_aliases = MenuTag.objects.filter(
            aliases__is_active=True,
            menu_items__is_active=True,
            menu_items__category__is_active=True,
        ).values_list("name", "aliases__phrase").distinct()
        self.tag_extractor.configure_catalog_tags(catalog_tags, catalog_aliases)
        self.mood_extractor = MoodExtractor()
        self.mood_resolver = MoodResolver()
        self.recommender = RecommendationService()
        self.interpreter = ConversationInterpreter(self.tag_extractor)
        self.gemini_client = GeminiClient()
        self.gemini_interpreter = GeminiInterpreter(
            self.gemini_client,
            allowed_tags=self.tag_extractor._aliases,
        )
        self.conversation_director = ConversationDirector(self.gemini_client)
        self.response_service = ConversationResponseService(self.gemini_client)
        self.assistant = GeminiAssistant(
            self.gemini_client,
            self.recommender,
            self.tag_extractor,
            session=self.session,
        )
        self.explanation_service = RecommendationExplanationService(self.gemini_client)

    # [OOP: Abstraction] Menghapus state percakapan di session dengan satu panggilan.
    def reset(self):
        self.context.reset()

    # [OOP: Class method] Hanya memakai atribut class (GEMINI_FOOD_CUES, GEMINI_UNCERTAIN_CUES),
    # tanpa state instance; menentukan apakah pesan layak diteruskan ke Gemini.
    @classmethod
    def _eligible_for_gemini(cls, message, interpretation):
        if len(message) > 500:
            return False
        if interpretation.contextual_revision:
            return True
        normalized = normalize_text(message)
        if any(
            cue in normalized
            for cue in ConversationInterpreter.PREFERENCE_CORRECTION_CUES
        ):
            return True
        if "mood naik" in normalized or "bikin mood" in normalized:
            return True
        if interpretation.intent in {
            ConversationIntent.RECOMMEND,
            ConversationIntent.UPDATE_PREFERENCES,
            ConversationIntent.REMOVE_PREFERENCES,
            ConversationIntent.REPLACE_PREFERENCES,
        }:
            return any(cue in normalized for cue in cls.GEMINI_UNCERTAIN_CUES)
        if interpretation.intent != ConversationIntent.UNKNOWN:
            return False
        return any(cue in normalized for cue in cls.GEMINI_FOOD_CUES)

    def _preferences(self):
        return self.context.preferences()

    def _search_constraints(self):
        return self.context.search_constraints()

    def _constraints_for_interpretation(self, interpretation, old_follow_up=None):
        return self.preference_state.constraints_for_interpretation(
            interpretation,
            old_follow_up,
        )

    # [OOP: Static method] Tidak memakai self; hanya memeriksa objek Preferences yang diberikan.
    @staticmethod
    def _has_preferences(preferences):
        return bool(
            preferences.tags
            or preferences.mood_tags
            or preferences.excluded_tags
            or preferences.soft_excluded_tags
            or preferences.max_price is not None
            or preferences.category
            or preferences.prefer_affordable
        )

    def _has_active_search(self):
        return self.context.has_active_search()

    # [OOP: Static method] Pembuat satu tombol balasan cepat; tidak butuh state objek.
    @staticmethod
    def _quick_reply(label, value, action=None):
        reply = {"label": label, "value": value}
        if action:
            reply["action"] = action
        return reply

    # [OOP: Abstraction] Menyusun pertanyaan lanjutan untuk pengguna.
    def _question(self, confused=False, source_message=""):
        if confused:
            message = "Tenang, nggak perlu mikir 😄 Aku bantu pilih. Kamu lagi lebih ke..."
            replies = [
                self._quick_reply("😋 Lapar banget", "Aku lapar banget"),
                self._quick_reply("😫 Lagi capek", "Aku lagi capek"),
                self._quick_reply("😔 Makanan yang bikin nyaman", "Butuh comfort food"),
                self._quick_reply("🔥 Pengen pedas", "Pengen yang pedas"),
                self._quick_reply("🥤 Pengen yang segar", "Lagi gerah, pengen yang segar"),
                self._quick_reply("💸 Lagi hemat", "Lagi hemat"),
            ]
        else:
            message = "Hai! Aku bisa bantu kamu memilih menu. Lagi ingin makan atau minum apa?"
            replies = [
                self._quick_reply("🍚 Makanan berat", "Makanan berat"),
                self._quick_reply("🍟 Camilan", "Camilan"),
                self._quick_reply("🥤 Minuman", "Minuman"),
                self._quick_reply("🌶️ Pedas", "Pengen yang pedas"),
                self._quick_reply("💸 Lagi hemat", "Lagi hemat"),
            ]
        replies = self._catalog_quick_replies(replies)
        ai_followup = self._ai_followup(
            source_message,
            "confusion" if confused else "general",
            replies,
        )
        if ai_followup:
            message = ai_followup["message"]
            replies = ai_followup["quick_replies"]
        self.session["last_question"] = "menu_choice"
        return {
            "message": message,
            "state": "COLLECTING_PREFERENCES",
            "preferences": Preferences().to_dict(),
            "recommendations": [],
            "quick_replies": replies,
        }

    def _ai_followup(self, source_message, mode, options, context=None):
        if not source_message or not self.conversation_director.available:
            return None
        if not self.context.consume_provider_request():
            return None
        decision = self.conversation_director.decide(
            source_message,
            mode,
            {
                **(context or {}),
                "allowed_options": options,
            },
        )
        if decision is None:
            return None
        allowed_values = {option["value"] for option in options}
        if not all(
            reply["value"] in allowed_values
            for reply in decision.quick_replies
        ):
            return None
        return {
            "should_ask_follow_up": decision.should_ask_follow_up,
            "message": decision.message,
            "quick_replies": list(decision.quick_replies),
        }

    # [OOP: Abstraction] Menyusun daftar balasan cepat untuk pertanyaan katalog.
    def _catalog_quick_replies(self, replies):
        existing_values = {reply["value"] for reply in replies}
        catalog_tags = (
            MenuTag.objects.filter(
                menu_items__is_active=True,
                menu_items__category__is_active=True,
            )
            .exclude(name__in={"spicy", "chicken", "drink"})
            .values_list("name", "display_name")
            .distinct()[:4]
        )
        for name, display_name in catalog_tags:
            label = tag_label(name)
            value = f"Pengen yang {display_name or name.replace('_', ' ')}"
            if value in existing_values:
                continue
            replies.append(self._quick_reply(label, value))
        return replies

    # [OOP: Abstraction] Menyiapkan preferensi yang dikirim ke layanan penjelasan.
    def _explanation_preferences(self, preferences, constraints):
        return Preferences(
            tags=set(constraints.required_tags),
            max_price=constraints.max_price,
            mood_tags=self.mood_resolver.resolve(set(constraints.moods)),
            excluded_tags=set(constraints.excluded_tags),
            category=constraints.category,
            prefer_affordable=preferences.prefer_affordable,
            moods=set(constraints.moods),
        )

    # [OOP: Abstraction] Menyusun respons pertanyaan jenis makanan.
    def _ask_meal_type(self, preferences, source_message=""):
        replies = [
            self._quick_reply("🍚 Makanan berat", "Makanan berat"),
            self._quick_reply("🍟 Camilan", "Camilan"),
        ]
        ai_followup = self._ai_followup(
            source_message,
            "meal_type",
            replies,
            {"preferences": sorted(preferences.all_positive_tags)},
        )
        if ai_followup and not ai_followup["should_ask_follow_up"]:
            self.session["last_question"] = None
            return self._recommend(preferences, source_message)
        self.session["last_question"] = "meal_type"
        self.context.save_preferences(
            preferences,
            "ASKING_FOLLOWUP",
            follow_up="meal_type",
        )
        return {
            "message": (
                ai_followup["message"]
                if ai_followup
                else "Wah, tim pedas nih 🌶️ Kamu lebih pengen makanan berat atau cuma mau ngemil?"
            ),
            "state": "ASKING_FOLLOWUP",
            "preferences": ConversationContext.response_preferences(
                preferences,
                "ASKING_FOLLOWUP",
                follow_up="meal_type",
            ),
            "recommendations": [],
            "quick_replies": ai_followup["quick_replies"] if ai_followup else replies,
        }

    # [OOP: Abstraction] Menyusun respons pertanyaan dasar makanan (nasi atau mie).
    def _ask_base(self, preferences, source_message=""):
        replies = [
            self._quick_reply("🍚 Nasi", "Pengen nasi"),
            self._quick_reply("🍜 Mie", "Pengen mie"),
            self._quick_reply("🤷 Bebas", "Bebas aja"),
        ]
        ai_followup = self._ai_followup(
            source_message,
            "base",
            replies,
            {"preferences": sorted(preferences.all_positive_tags)},
        )
        if ai_followup and not ai_followup["should_ask_follow_up"]:
            self.session["last_question"] = None
            return self._recommend(preferences, source_message)
        self.session["last_question"] = "base"
        self.context.save_preferences(
            preferences,
            "ASKING_FOLLOWUP",
            follow_up="base",
        )
        return {
            "message": (
                ai_followup["message"]
                if ai_followup
                else "Sip! Kamu lebih pengen nasi atau mie? Kalau bebas, bilang aja ya 😄"
            ),
            "state": "ASKING_FOLLOWUP",
            "preferences": ConversationContext.response_preferences(
                preferences,
                "ASKING_FOLLOWUP",
                follow_up="base",
            ),
            "recommendations": [],
            "quick_replies": ai_followup["quick_replies"] if ai_followup else replies,
        }

    # [OOP: Static method] Membentuk teks balasan chatbot dari data yang diberikan, tanpa state objek.
    @staticmethod
    def _response_message(
        preferences,
        source_text,
        response_kind="recommendation",
        constraints=None,
    ):
        text = normalize_text(source_text)
        active = preferences
        if constraints is not None:
            active = Preferences(
                tags=set(constraints.required_tags),
                max_price=constraints.max_price,
                mood_tags=preferences.mood_tags,
                excluded_tags=set(constraints.excluded_tags),
                category=constraints.category,
                prefer_affordable=preferences.prefer_affordable,
                moods=set(constraints.moods),
            )
        if response_kind == "correction":
            context = "Oke, kita ikuti perubahan pilihanmu 👍"
        elif response_kind == "removal":
            context = "Siap, preferensi itu aku hilangkan 👍"
        elif "hot_thirsty" in active.moods:
            context = "Lagi gerah? Kita cari yang dingin dan seger dulu 🧊"
        elif "tired" in active.moods:
            context = "Kalau lagi capek, kita cari yang mengenyangkan dan bikin puas ya 😌"
        elif "low_mood" in active.moods:
            context = "Hari yang berat cocok ditemani makanan yang bikin nyaman 😌"
        elif "very_hungry" in active.moods or "heavy_meal" in active.tags:
            context = "Wah, sepertinya kamu butuh yang mengenyangkan nih 🍚"
        elif "spicy" in active.tags:
            context = "Wah, tim pedas nih 🌶️"
        elif active.prefer_affordable:
            context = "Oke, kita cari yang tetap enak tapi ramah di kantong 💸"
        else:
            context = "Tenang, aku bantu pilih yang cocok buat kamu 😋"

        requested = []
        for tag in sorted(active.tags):
            label = tag_label(tag)
            if label and label not in requested:
                requested.append(label)
        details = []
        if requested:
            details.append(" dan ".join(requested[:3]))
        if active.category:
            details.append(active.category.casefold())
        if active.max_price is not None:
            details.append(f"maksimal Rp{active.max_price:,.0f}".replace(",", "."))
        if active.prefer_affordable and active.max_price is None:
            details.append("ramah di kantong")
        if active.excluded_tags:
            dislikes = [tag_label(tag) for tag in sorted(active.excluded_tags)]
            if dislikes:
                details.append("tanpa " + " atau ".join(dislikes[:2]))
        summary = f"Aku carikan yang {'; '.join(details)} ya. " if details else ""

        variants = (
            "Ini beberapa yang kayaknya cocok buat kamu 😋",
            "Aku nemu beberapa pilihan yang pas buat preferensimu.",
            "Kayaknya kamu bakal cocok sama beberapa menu ini 👀",
            "Nah, ini beberapa menu yang menarik buat kamu.",
            "Aku punya beberapa pilihan yang bisa kamu coba.",
        )
        variant_index = sum(ord(character) for character in text) % len(variants)
        return f"{context}\n{summary}{variants[variant_index]}"

    # [OOP: Static method] Balasan standar bila pesan tidak dipahami.
    @staticmethod
    def _unknown_response(source_text):
        variants = (
            "Hehe, aku belum menangkap maksudnya 😄",
            "Aku belum yakin maksudmu apa.",
            "Boleh kasih sedikit petunjuk?",
            "Aku masih belum menangkap yang kamu mau.",
        )
        index = sum(ord(char) for char in normalize_text(source_text)) % len(variants)
        return (
            f"{variants[index]}\nCoba kasih tahu misalnya kamu mau yang pedas, ayam, nasi, atau yang murah."
        )

    # [OOP: Abstraction] Menjalankan ranking lewat RecommendationService, lalu membentuk respons.
    # [OOP: Composition] Mendelegasikan pekerjaan ke komponen yang dimiliki (recommender, explanation_service).
    def _recommend(
        self,
        preferences,
        source_text,
        more=False,
        exclude_ids=None,
        response_kind="recommendation",
        required_tags=None,
        constraints=None,
    ):
        preferences.mood_tags = self.mood_resolver.resolve(preferences.moods)
        if constraints is None:
            if required_tags is not None:
                constraints = SearchConstraints(
                    required_tags=frozenset(required_tags),
                    category=preferences.category,
                    max_price=preferences.max_price,
                    moods=frozenset(preferences.moods),
                )
            else:
                constraints = self._search_constraints()
        self.session[self.SEARCH_KEY] = constraints.to_dict()
        self.session["recommendation_required_tags"] = sorted(
            constraints.required_tags
        )
        shown = self.session.get(self.SHOWN_KEY, [])
        if more:
            exclude_ids = list(exclude_ids or shown or [])
            shown = list(shown)
        else:
            exclude_ids = list(exclude_ids or [])
            shown = []
        matches = self.recommender.rank(
            preferences,
            exclude_ids=exclude_ids,
            constraints=constraints,
        )
        explanation_preferences = self._explanation_preferences(
            preferences,
            constraints,
        )
        explanations = {
            match.item.id: self.explanation_service.fallback(match)
            for match in matches
        }
        generated_response = None
        if self.response_service.available and self.context.consume_provider_request():
            generated_response = self.response_service.respond(
                source_text,
                preferences,
                constraints,
                matches,
                response_kind=response_kind,
            )
        generated_intro = None
        if matches and self.context.consume_provider_request():
            generated_intro, generated_explanations = (
                self.explanation_service.explain_with_intro(
                    matches,
                    explanation_preferences,
                    source_text,
                    response_kind=response_kind,
                )
            )
            explanations.update(generated_explanations)
        new_ids = [match.item.id for match in matches]
        if more:
            self.session[self.SHOWN_KEY] = shown + new_ids
        else:
            self.session[self.SHOWN_KEY] = new_ids
        self.session["last_recommendations"] = [match.item.id for match in matches] if matches else []
        self.session["shown_recommendation_ids"] = list(self.session.get(self.SHOWN_KEY, []))
        self.session[self.LAST_RESULT_EMPTY_KEY] = not matches
        self.session.modified = True
        self.context.save_preferences(preferences, "RECOMMENDING")
        return {
            "message": (
                generated_response
                or generated_intro
                or self._response_message(
                    preferences,
                    source_text,
                    response_kind=response_kind,
                    constraints=constraints,
                )
                if matches
                else generated_response
                or "Aku belum menemukan yang pas. Coba ubah pilihan atau batas harganya, ya."
            ),
            "state": "RECOMMENDING",
            "preferences": ConversationContext.response_preferences(
                preferences,
                "RECOMMENDING",
            ),
            "active_search": constraints.to_dict(),
            "recommendations": matches,
            "explanations": explanations,
            "quick_replies": [
                self._quick_reply("🔄 Cari Menu Lain", "Cari menu lain", action="more"),
                self._quick_reply("🔄 Mulai Lagi", "mulai lagi", action="reset"),
            ],
        }

    # [OOP: Abstraction] Menjawab pertanyaan katalog tanpa mengubah preferensi yang tersimpan.
    def _answer_catalog_question(self, preferences, interpretation, source_text):
        tags = interpretation.catalog_tags
        constraints = SearchConstraints(
            required_tags=frozenset(tags),
            excluded_tags=frozenset(interpretation.excluded_tags),
            category=interpretation.category,
            max_price=interpretation.max_price,
        )
        self.session[self.SEARCH_KEY] = constraints.to_dict()
        self.session["recommendation_required_tags"] = sorted(tags)
        matches = self.recommender.find_catalog_matches(
            tags,
            excluded_tags=interpretation.excluded_tags,
            category=interpretation.category,
            max_price=interpretation.max_price,
        )
        state = self.session.get(self.SESSION_KEY, {}).get(
            "state",
            "COLLECTING_PREFERENCES",
        )
        if not matches:
            tag_labels = [tag_label(tag) for tag in sorted(tags)]
            requested = " dan ".join(tag_labels) or "pilihan itu"
            self.session["last_recommendations"] = []
            self.session[self.LAST_RESULT_EMPTY_KEY] = True
            self.session.modified = True
            return {
                "message": (
                    f"Aku belum menemukan menu {requested} yang tersedia saat ini."
                ),
                "state": state,
                "preferences": ConversationContext.response_preferences(
                    preferences,
                    state,
                ),
                "active_search": constraints.to_dict(),
                "recommendations": [],
                "catalog_question": True,
                "quick_replies": [],
            }

        query_preferences = self._explanation_preferences(
            preferences,
            constraints,
        )
        explanations = {
            match.item.id: self.explanation_service.fallback(match)
            for match in matches
        }
        generated_intro = None
        if self.context.consume_provider_request():
            generated_intro, generated_explanations = (
                self.explanation_service.explain_with_intro(
                    matches,
                    query_preferences,
                    source_text,
                    response_kind="catalog_question",
                )
            )
            explanations.update(generated_explanations)

        tag_labels = [tag_label(tag) for tag in sorted(tags)]
        requested = " dan ".join(tag_labels) or "pilihanmu"
        self.session["last_recommendations"] = [match.item.id for match in matches]
        self.session[self.SHOWN_KEY] = [match.item.id for match in matches]
        self.session["shown_recommendation_ids"] = [match.item.id for match in matches]
        self.session[self.LAST_RESULT_EMPTY_KEY] = not bool(matches)
        self.session.modified = True
        return {
            "message": generated_intro
            or f"Ini pilihan menu {requested} yang tersedia di katalog.",
            "state": state,
            "preferences": ConversationContext.response_preferences(
                preferences,
                state,
            ),
            "active_search": constraints.to_dict(),
            "recommendations": matches,
            "catalog_question": True,
            "explanations": explanations,
            "quick_replies": [
                self._quick_reply("🔄 Mulai Lagi", "mulai lagi", action="reset"),
            ],
        }

    # [OOP: Static method] Memilih salah satu varian kalimat secara deterministik dari teks; tanpa state objek.
    @staticmethod
    def _deterministic_variant(text, variants):
        index = sum(ord(character) for character in normalize_text(text)) % len(variants)
        return variants[index]

    # [OOP: Abstraction] Menerapkan hasil interpretasi (tambah, hapus, ganti) ke Preferences.
    def _apply_interpretation(self, preferences, interpretation):
        current = Preferences.from_dict(self.session.get(self.SESSION_KEY, {})) if self.session.get(self.SESSION_KEY) else preferences
        if interpretation.intent == ConversationIntent.RESET:
            self.reset()
            return current
        if interpretation.intent in {ConversationIntent.GREETING, ConversationIntent.HELP, ConversationIntent.UNKNOWN, ConversationIntent.OUT_OF_SCOPE}:
            return current

        moods = set(interpretation.moods)

        for operation in interpretation.operations:
            op = operation.action
            tags = set(operation.tags)
            if op == "ADD":
                current.tags.update(tags)
                current.excluded_tags.difference_update(tags)
                current.soft_excluded_tags.difference_update(tags)
            elif op == "REMOVE":
                current.tags.difference_update(tags)
                current.excluded_tags.update(tags)
                current.soft_excluded_tags.difference_update(tags)
            elif op == "SOFT_REMOVE":
                current.tags.difference_update(tags)
                current.soft_excluded_tags.update(tags)
                current.excluded_tags.difference_update(tags)
            elif op == "REPLACE":
                current.tags.difference_update(operation.remove_tags)
                current.tags.update(tags)
                current.excluded_tags.difference_update(tags)
                current.soft_excluded_tags.difference_update(tags)
                current.excluded_tags.difference_update(operation.remove_tags)
                current.soft_excluded_tags.difference_update(operation.remove_tags)
            elif op == "CLEAR":
                current.tags.clear()
                current.excluded_tags.clear()
                current.soft_excluded_tags.clear()
                current.moods.clear()
                current.max_price = None
                current.category = None
                current.prefer_affordable = False
        if interpretation.clear_moods:
            current.moods.clear()
        if moods:
            current.moods = moods
        current.tags.difference_update(current.excluded_tags | current.soft_excluded_tags)
        current.mood_tags = self.mood_resolver.resolve(current.moods)
        current.max_price = interpretation.max_price
        current.category = interpretation.category
        if interpretation.prefer_affordable:
            current.prefer_affordable = True
        if interpretation.clear_max_price:
            current.max_price = None
        if interpretation.clear_prefer_affordable:
            current.prefer_affordable = False
        return current

    # [OOP: Abstraction] Menerjemahkan rujukan seperti "yang pertama" menjadi menu dari rekomendasi sebelumnya.
    def _select_previous_recommendation(self, interpretation, session_state):
        previous = session_state.get("last_recommendations", [])
        index = {
            "first": 0,
            "second": 1,
            "last": -1,
        }.get(interpretation.contextual_reference)
        if index is None or not previous or abs(index) > len(previous):
            return None
        match = self.recommender.get_available_match(previous[index])
        return match

    def _gemini_first_reply(self, message):
        context = self.context.gemini_context()
        response, _tool_results = self.assistant.respond(
            message or "Mulai percakapan dan bantu pelanggan memilih menu.",
            context,
            self.context.consume_provider_request,
        )
        if response is None:
            return {
                "message": (
                    "Maaf, asisten AI sedang tidak tersedia. "
                    "Silakan coba lagi sebentar."
                ),
                "state": self.session.get(self.SESSION_KEY, {}).get(
                    "state",
                    "COLLECTING_PREFERENCES",
                ),
                "preferences": ConversationContext.response_preferences(
                    self._preferences(),
                    self.session.get(self.SESSION_KEY, {}).get(
                        "state",
                        "COLLECTING_PREFERENCES",
                    ),
                ),
                "recommendations": [],
                "quick_replies": [],
            }

        matches = context.get("last_tool_matches", [])
        constraints_data = context.get("last_tool_constraints")
        if constraints_data:
            constraints = SearchConstraints.from_dict(constraints_data)
            preferences = self._preferences()
            if (
                matches
                and any(
                    phrase in normalize_text(response)
                    for phrase in ("nggak ada", "kosong")
                )
            ):
                response = self._response_message(
                    preferences,
                    message,
                    constraints=constraints,
                )
            preferences.tags.update(constraints.required_tags)
            preferences.tags.difference_update(constraints.excluded_tags)
            preferences.excluded_tags.update(constraints.excluded_tags)
            preferences.max_price = constraints.max_price
            preferences.category = constraints.category
            self.session[self.SEARCH_KEY] = constraints.to_dict()
            self.session["recommendation_required_tags"] = sorted(
                constraints.required_tags
            )
            ids = [match.item.id for match in matches]
            self.session[self.SHOWN_KEY] = ids
            self.session["last_recommendations"] = ids
            self.session["shown_recommendation_ids"] = ids
            self.session[self.LAST_RESULT_EMPTY_KEY] = not bool(matches)
            self.session["recommendation_last_message"] = message[:500]
            self.session["recommendation_last_response"] = response[:1200]
            self.session.modified = True
            self.context.save_preferences(preferences, "RECOMMENDING")
            return {
                "message": response,
                "state": "RECOMMENDING",
                "preferences": ConversationContext.response_preferences(
                    preferences,
                    "RECOMMENDING",
                ),
                "active_search": constraints.to_dict(),
                "recommendations": matches,
                "explanations": {
                    match.item.id: self.explanation_service.fallback(match)
                    for match in matches
                },
                "quick_replies": [
                    self._quick_reply(
                        "🔄 Cari Menu Lain",
                        "Cari menu lain",
                        action="more",
                    ),
                    self._quick_reply(
                        "🔄 Mulai Lagi",
                        "mulai lagi",
                        action="reset",
                    ),
                ],
            }

        state = self.session.get(self.SESSION_KEY, {}).get(
            "state",
            "COLLECTING_PREFERENCES",
        )
        self.session["recommendation_last_message"] = message[:500]
        self.session["recommendation_last_response"] = response[:1200]
        self.session.modified = True
        return {
            "message": response,
            "state": state,
            "preferences": ConversationContext.response_preferences(
                self._preferences(),
                state,
            ),
            "recommendations": [],
            "quick_replies": [],
        }

    # [OOP: Abstraction] Satu-satunya pintu masuk publik class ini (pola Facade): pesan masuk,
    # balasan lengkap keluar.
    # [OOP: Encapsulation] Seluruh method lain berawalan _ sehingga menjadi detail internal.
    def reply(self, message, more=False, action=None):
        normalized = normalize_text(message)
        action = action or ""
        if action == "reset" or normalized in self.RESET_PHRASES:
            self.reset()
            if self.assistant.available:
                return self._gemini_first_reply("")
            return self._question()

        if self.assistant.available:
            return self._gemini_first_reply(message)

        if not normalized and not self._has_preferences(self._preferences()):
            return self._question()

        session_state = self.session.get(self.SESSION_KEY, {})
        pending_question = session_state.get(
            "last_question",
            self.session.get("last_question"),
        )
        open_followup_answer = (
            normalized in self.OPEN_FOLLOWUP_ANSWERS
            and pending_question in {"meal_type", "base"}
        )
        confusion = next((phrase for phrase in self.CONFUSION_PHRASES if phrase in normalized), None)
        if confusion and not open_followup_answer:
            extracted = self.tag_extractor.extract(normalized)
            moods = self.mood_extractor.extract(normalized)
            meaningful = bool(
                extracted.tags
                or extracted.excluded_tags
                or extracted.soft_excluded_tags
                or extracted.max_price is not None
                or extracted.category
                or extracted.prefer_affordable
                or (moods - {"confused"})
            )
            if not meaningful:
                state = self.session.get(self.SESSION_KEY, {}).get("state", "COLLECTING_PREFERENCES")
                preferences = self._preferences()
                if not self._has_preferences(preferences):
                    state = "COLLECTING_PREFERENCES"
                response = self._question(
                    confused=True,
                    source_message=normalized,
                )
                return {
                    "message": response["message"],
                    "state": state,
                    "preferences": preferences.to_dict(state=state),
                    "recommendations": [],
                    "quick_replies": response["quick_replies"],
                }

        more = more or action == "more" or normalized in self.MORE_PHRASES
        preferences = self._preferences()
        session_state = self.session.get(self.SESSION_KEY, {})
        old_follow_up = session_state.get("follow_up")
        interpretation = self.interpreter.interpret(
            normalized,
            last_question=session_state.get(
                "last_question",
                self.session.get("last_question"),
            ),
            last_recommendations=session_state.get("last_recommendations", []),
            last_result_empty=self.session.get(
                self.LAST_RESULT_EMPTY_KEY,
                False,
            ),
        )
        if interpretation.intent == ConversationIntent.RETRY_SEARCH:
            updated = self._apply_interpretation(preferences, interpretation)
            constraints = self._constraints_for_interpretation(interpretation)
            self.session["last_question"] = None
            return self._recommend(
                updated,
                normalized,
                response_kind="retry",
                constraints=constraints,
            )
        if interpretation.intent == ConversationIntent.CATALOG_QUESTION:
            return self._answer_catalog_question(
                preferences,
                interpretation,
                normalized,
            )
        if open_followup_answer:
            self.session["last_question"] = None
            return self._recommend(preferences, normalized)
        if (
            self._eligible_for_gemini(normalized, interpretation)
            and self.context.consume_provider_request()
        ):
            ai_interpretation = self.gemini_interpreter.interpret(
                normalized,
                context={
                    "tags": sorted(preferences.tags),
                    "excluded_tags": sorted(preferences.excluded_tags),
                    "soft_excluded_tags": sorted(preferences.soft_excluded_tags),
                    "moods": sorted(preferences.moods),
                    "max_price": preferences.max_price,
                    "prefer_affordable": preferences.prefer_affordable,
                    "last_question": session_state.get(
                        "last_question",
                        self.session.get("last_question"),
                    ),
                    "active_search": self._search_constraints().to_dict(),
                },
            )
            if ai_interpretation is not None:
                interpretation = ai_interpretation

        if interpretation.intent == ConversationIntent.RESET:
            self.reset()
            return self._question()

        if interpretation.intent == ConversationIntent.GREETING:
            return {
                "message": "Halo! Aku bantu pilih menu yang cocok buat kamu 😊",
                "state": "COLLECTING_PREFERENCES",
                "preferences": preferences.to_dict(state="COLLECTING_PREFERENCES"),
                "recommendations": [],
                "quick_replies": [
                    self._quick_reply("🍚 Makanan berat", "Makanan berat"),
                    self._quick_reply("🍟 Camilan", "Camilan"),
                    self._quick_reply("🥤 Minuman", "Minuman"),
                ],
            }

        if interpretation.intent == ConversationIntent.HELP:
            return {
                "message": "Aku bisa bantu cari menu yang cocok. Coba bilang misalnya 'pedas', 'ayam', 'nasi', atau 'yang murah'.",
                "state": session_state.get("state", "COLLECTING_PREFERENCES"),
                "preferences": preferences.to_dict(state=session_state.get("state", "COLLECTING_PREFERENCES")),
                "recommendations": [],
                "quick_replies": [
                    self._quick_reply("🌶️ Pedas", "Pengen yang pedas"),
                    self._quick_reply("🍗 Ayam", "Aku mau ayam"),
                    self._quick_reply("💸 Murah", "Yang murah saja"),
                ],
            }

        if interpretation.intent == ConversationIntent.OUT_OF_SCOPE:
            return {
                "message": "Aku fokus bantu kamu pilih menu di sini 😊\nCoba kasih tahu kamu lagi ingin makan atau minum apa.",
                "state": "COLLECTING_PREFERENCES",
                "preferences": preferences.to_dict(state="COLLECTING_PREFERENCES"),
                "recommendations": [],
                "quick_replies": [
                    self._quick_reply("🍚 Makanan berat", "Makanan berat"),
                    self._quick_reply("🍟 Camilan", "Camilan"),
                    self._quick_reply("🥤 Minuman", "Minuman"),
                ],
            }

        if interpretation.intent == ConversationIntent.UNKNOWN:
            state = session_state.get("state", "COLLECTING_PREFERENCES")
            if not self._has_preferences(preferences):
                state = "COLLECTING_PREFERENCES"
            return {
                "message": self._unknown_response(normalized),
                "state": state,
                "preferences": preferences.to_dict(state=state),
                "recommendations": [],
                "quick_replies": [
                    self._quick_reply("🌶️ Pedas", "Pengen yang pedas"),
                    self._quick_reply("🍗 Ayam", "Aku mau ayam"),
                    self._quick_reply("💸 Murah", "yang murah"),
                ],
            }

        if interpretation.intent == ConversationIntent.SELECT_RECOMMENDATION:
            match = self._select_previous_recommendation(interpretation, session_state)
            if match is None:
                return {
                    "message": "Aku belum menemukan menu yang kamu maksud di pilihan sebelumnya. Mau aku carikan rekomendasi lagi?",
                    "state": session_state.get("state", "COLLECTING_PREFERENCES"),
                    "preferences": preferences.to_dict(state=session_state.get("state", "COLLECTING_PREFERENCES")),
                    "recommendations": [],
                    "quick_replies": [
                        self._quick_reply("🔄 Cari menu lagi", "Cari menu lain", action="more"),
                        self._quick_reply("🍗 Ayam", "Aku mau ayam"),
                    ],
                }
            return {
                "message": "Ini menu yang kamu maksud dari rekomendasi sebelumnya 😊",
                "state": session_state.get("state", "RECOMMENDING"),
                "preferences": preferences.to_dict(state=session_state.get("state", "RECOMMENDING")),
                "recommendations": [match],
                "quick_replies": [],
            }

        if interpretation.intent == ConversationIntent.REJECT_RECOMMENDATION:
            rejected_ids = list(self.session.get("shown_recommendation_ids", [])) or list(self.session.get("last_recommendations", []))
            if not rejected_ids:
                return {
                    "message": "Boleh kasih tahu preferensimu yang baru, atau aku bisa bantu cari yang lain.",
                    "state": session_state.get("state", "COLLECTING_PREFERENCES"),
                    "preferences": preferences.to_dict(state=session_state.get("state", "COLLECTING_PREFERENCES")),
                    "recommendations": [],
                    "quick_replies": [
                        self._quick_reply("🌶️ Pedas", "Pengen yang pedas"),
                        self._quick_reply("🍗 Ayam", "Aku mau ayam"),
                    ],
                }
            result = self._recommend(preferences, normalized, more=True, exclude_ids=rejected_ids)
            result["message"] = (
                self._deterministic_variant(
                    normalized,
                    (
                        "Oke, kita cari yang lain 😄",
                        "Siap, yang tadi kita lewati dulu.",
                        "Belum cocok? Kita coba pilihan lain.",
                    ),
                )
                + ("\n" + result["message"] if result["recommendations"] else "")
            )
            return result

        if interpretation.intent == ConversationIntent.CONFIRM:
            if session_state.get("last_question") == "meal_type":
                if "heavy_meal" in preferences.tags:
                    return self._ask_base(preferences)
                return self._recommend(preferences, normalized)
            if session_state.get("last_question") == "base":
                return self._recommend(preferences, normalized)
            return self._recommend(preferences, normalized)

        if interpretation.intent in {
            ConversationIntent.RECOMMEND,
            ConversationIntent.UPDATE_PREFERENCES,
            ConversationIntent.REMOVE_PREFERENCES,
            ConversationIntent.REPLACE_PREFERENCES,
        }:
            updated = self._apply_interpretation(preferences, interpretation)
            constraints = self._constraints_for_interpretation(
                interpretation,
                old_follow_up=old_follow_up,
            )
            if interpretation.intent == ConversationIntent.UPDATE_PREFERENCES and not self._has_preferences(updated):
                if interpretation.clear_moods:
                    response = self._question()
                    self.context.save_preferences(updated, "COLLECTING_PREFERENCES")
                    return response
                return self._question(confused=True)

            self.session["last_question"] = None
            self.session[self.SEARCH_KEY] = constraints.to_dict()
            updated.mood_tags = self.mood_resolver.resolve(updated.moods)
            if old_follow_up == "meal_type" and "heavy_meal" in updated.tags and not updated.tags.intersection({"rice", "noodle", "snack"}):
                return self._ask_base(updated, source_message=normalized)

            only_spicy = (
                updated.tags.intersection({"spicy"}) == {"spicy"}
                and len(updated.tags) == 1
                and not updated.moods
                and updated.max_price is None
                and not updated.prefer_affordable
                and not updated.excluded_tags
                and not updated.soft_excluded_tags
                and not updated.category
            )
            if only_spicy and old_follow_up is None:
                return self._ask_meal_type(updated, source_message=normalized)

            if not self._has_preferences(updated):
                if interpretation.clear_moods:
                    response = self._question()
                    self.context.save_preferences(updated, "COLLECTING_PREFERENCES")
                    return response
                return self._question()

            self.context.save_preferences(updated, "RECOMMENDING")
            result = self._recommend(
                updated,
                normalized,
                response_kind=(
                    "correction"
                    if interpretation.intent == ConversationIntent.REPLACE_PREFERENCES
                    else "removal"
                    if interpretation.intent == ConversationIntent.REMOVE_PREFERENCES
                    else "recommendation"
                ),
                constraints=constraints,
            )
            return result

        if more:
            if not self._has_preferences(preferences) and not self._has_active_search():
                return self._question(confused=True)
            return self._recommend(preferences, normalized, more=True)

        if not self._has_preferences(preferences):
            return self._question()
        return self._recommend(preferences, normalized)
