from .conversation_interpreter import ConversationInterpreter, ConversationIntent
from .language import TAG_LABELS, normalize_text
from .mood_extractor import MoodExtractor
from .mood_resolver import MoodResolver
from .recommendation import RecommendationService
from .tag_extractor import Preferences, TagExtractor
from recommendation.services.ai.GeminiInterpreter import GeminiInterpreter
from django.conf import settings



class ChatbotService:
    SESSION_KEY = "recommendation_state"
    SHOWN_KEY = "recommendation_shown"
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

    def __init__(self, session):
        self.session = session
        self.tag_extractor = TagExtractor()
        self.mood_extractor = MoodExtractor()
        self.mood_resolver = MoodResolver()
        self.recommender = RecommendationService()
        self.interpreter = ConversationInterpreter()
        self.gemini_interpreter = GeminiInterpreter()

    def reset(self):
        self.session.pop(self.SESSION_KEY, None)
        self.session.pop(self.SHOWN_KEY, None)
        self.session.pop("recommendation_context", None)
        self.session.pop("shown_recommendation_ids", None)
        self.session.pop("last_recommendations", None)
        self.session.pop("last_question", None)
        self.session.modified = True

    def _preferences(self):
        return Preferences.from_dict(self.session.get(self.SESSION_KEY, {}))

    def _save(self, preferences, state, follow_up=None):
        payload = preferences.to_dict(state=state, follow_up=follow_up)
        payload["last_question"] = self.session.get("last_question")
        payload["last_recommendations"] = self.session.get("last_recommendations", [])
        payload["shown_recommendation_ids"] = self.session.get("shown_recommendation_ids", [])
        self.session[self.SESSION_KEY] = payload
        self.session.modified = True

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

    @staticmethod
    def _quick_reply(label, value, action=None):
        reply = {"label": label, "value": value}
        if action:
            reply["action"] = action
        return reply

    def _question(self, confused=False):
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
        self.session["last_question"] = "menu_choice"
        return {
            "message": message,
            "state": "COLLECTING_PREFERENCES",
            "preferences": Preferences().to_dict(),
            "recommendations": [],
            "quick_replies": replies,
        }

    def _ask_meal_type(self, preferences):
        self.session["last_question"] = "meal_type"
        self._save(preferences, "ASKING_FOLLOWUP", follow_up="meal_type")
        return {
            "message": "Wah, tim pedas nih 🌶️ Kamu lebih pengen makanan berat atau cuma mau ngemil?",
            "state": "ASKING_FOLLOWUP",
            "preferences": preferences.to_dict(state="ASKING_FOLLOWUP", follow_up="meal_type"),
            "recommendations": [],
            "quick_replies": [
                self._quick_reply("🍚 Makanan berat", "Makanan berat"),
                self._quick_reply("🍟 Camilan", "Camilan"),
            ],
        }

    def _ask_base(self, preferences):
        self.session["last_question"] = "base"
        self._save(preferences, "ASKING_FOLLOWUP", follow_up="base")
        return {
            "message": "Sip! Kamu lebih pengen nasi atau mie? Kalau bebas, bilang aja ya 😄",
            "state": "ASKING_FOLLOWUP",
            "preferences": preferences.to_dict(state="ASKING_FOLLOWUP", follow_up="base"),
            "recommendations": [],
            "quick_replies": [
                self._quick_reply("🍚 Nasi", "Pengen nasi"),
                self._quick_reply("🍜 Mie", "Pengen mie"),
                self._quick_reply("🤷 Bebas", "Bebas aja"),
            ],
        }

    @staticmethod
    def _response_message(preferences, source_text):
        text = normalize_text(source_text)
        if "hot_thirsty" in preferences.moods:
            context = "Lagi gerah? Kita cari yang dingin dan seger dulu 🧊"
        elif "tired" in preferences.moods:
            context = "Kalau lagi capek, kita cari yang mengenyangkan dan bikin puas ya 😌"
        elif "low_mood" in preferences.moods:
            context = "Hari yang berat cocok ditemani makanan yang bikin nyaman 😌"
        elif "very_hungry" in preferences.moods or "heavy_meal" in preferences.tags:
            context = "Wah, sepertinya kamu butuh yang mengenyangkan nih 🍚"
        elif "spicy" in preferences.tags:
            context = "Wah, tim pedas nih 🌶️"
        elif preferences.prefer_affordable:
            context = "Oke, kita cari yang tetap enak tapi ramah di kantong 💸"
        else:
            context = "Tenang, aku bantu pilih yang cocok buat kamu 😋"

        requested = []
        for tag in sorted(preferences.tags):
            label = TAG_LABELS.get(tag)
            if label and label not in requested:
                requested.append(label)
        details = []
        if requested:
            details.append(" dan ".join(requested[:3]))
        if preferences.max_price is not None:
            details.append(f"maksimal Rp{preferences.max_price:,.0f}".replace(",", "."))
        if preferences.prefer_affordable and preferences.max_price is None:
            details.append("ramah di kantong")
        if preferences.excluded_tags:
            dislikes = [
                TAG_LABELS[tag]
                for tag in sorted(preferences.excluded_tags)
                if tag in TAG_LABELS
            ]
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

    def _recommend(self, preferences, source_text, more=False, exclude_ids=None):
        preferences.mood_tags = self.mood_resolver.resolve(preferences.moods)
        shown = self.session.get(self.SHOWN_KEY, [])
        if more:
            exclude_ids = list(exclude_ids or shown or [])
            shown = list(shown)
        else:
            exclude_ids = list(exclude_ids or [])
            shown = []
        matches = self.recommender.rank(preferences, exclude_ids=exclude_ids)
        new_ids = [match.item.id for match in matches]
        if more:
            self.session[self.SHOWN_KEY] = shown + new_ids
        else:
            self.session[self.SHOWN_KEY] = new_ids
        self.session["last_recommendations"] = [match.item.id for match in matches] if matches else []
        self.session["shown_recommendation_ids"] = list(self.session.get(self.SHOWN_KEY, []))
        self.session.modified = True
        self._save(preferences, "RECOMMENDING")
        return {
            "message": (
                self._response_message(preferences, source_text)
                if matches
                else "Aku belum menemukan yang pas. Coba ubah pilihan atau batas harganya, ya."
            ),
            "state": "RECOMMENDING",
            "preferences": preferences.to_dict(state="RECOMMENDING"),
            "recommendations": matches,
            "quick_replies": [
                self._quick_reply("🔄 Cari Menu Lain", "Cari menu lain", action="more"),
                self._quick_reply("🔄 Mulai Lagi", "mulai lagi", action="reset"),
            ],
        }

    @staticmethod
    def _deterministic_variant(text, variants):
        index = sum(ord(character) for character in normalize_text(text)) % len(variants)
        return variants[index]

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
        if interpretation.max_price is not None:
            current.max_price = interpretation.max_price
        if interpretation.category:
            current.category = interpretation.category
        if interpretation.prefer_affordable:
            current.prefer_affordable = True
        return current

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

    def reply(self, message, more=False, action=None):
        normalized = normalize_text(message)
        action = action or ""
        if action == "reset" or normalized in self.RESET_PHRASES:
            self.reset()
            return self._question()

        if not normalized and not self._has_preferences(self._preferences()):
            return self._question()

        confusion = next((phrase for phrase in self.CONFUSION_PHRASES if phrase in normalized), None)
        if confusion:
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
                response = self._question(confused=True)
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
        )
        
        if (
            interpretation.intent == ConversationIntent.UNKNOWN
            and not interpretation.contextual_reference
            and message.strip()
            and len(message) <= 500
            and self.session.get("gemini_calls", 0) < settings.GEMINI_MAX_CALLS_PER_SESSION

        ):
            self.session["gemini_calls"] = self.session.get("gemini_calls", 0) + 1
            self.session.modified = True
            ai_interpretation = GeminiInterpreter().interpret(message)
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
            if interpretation.intent == ConversationIntent.UPDATE_PREFERENCES and not self._has_preferences(updated):
                if interpretation.clear_moods:
                    response = self._question()
                    self._save(updated, "COLLECTING_PREFERENCES")
                    return response
                return self._question(confused=True)

            self.session["last_question"] = None
            updated.mood_tags = self.mood_resolver.resolve(updated.moods)
            if old_follow_up == "meal_type" and "heavy_meal" in updated.tags and not updated.tags.intersection({"rice", "noodle", "snack"}):
                return self._ask_base(updated)

            only_spicy = (
                updated.tags.intersection({"spicy"}) == {"spicy"}
                and len(updated.tags) == 1
                and not updated.moods
                and updated.max_price is None
                and not updated.prefer_affordable
                and not updated.excluded_tags
            )
            if only_spicy and old_follow_up is None:
                return self._ask_meal_type(updated)

            if not self._has_preferences(updated):
                if interpretation.clear_moods:
                    response = self._question()
                    self._save(updated, "COLLECTING_PREFERENCES")
                    return response
                return self._question()

            self._save(updated, "RECOMMENDING")
            result = self._recommend(updated, normalized)
            if interpretation.intent in {
                ConversationIntent.REMOVE_PREFERENCES,
                ConversationIntent.REPLACE_PREFERENCES,
            }:
                variants = (
                    (
                        "Oke, kita ganti pilihannya 👍",
                        "Siap, kita ubah.",
                        "Noted! Preferensi sebelumnya aku sesuaikan.",
                    )
                    if interpretation.intent == ConversationIntent.REPLACE_PREFERENCES
                    else (
                        "Siap, pilihan itu aku hilangkan.",
                        "Oke, aku sesuaikan tanpa pilihan tadi.",
                        "Noted! Preferensinya sudah aku perbarui.",
                    )
                )
                result["message"] = (
                    self._deterministic_variant(
                        normalized,
                        variants,
                    )
                    + ("\n" + result["message"] if result["recommendations"] else "")
                )
            return result

        if more:
            if not self._has_preferences(preferences):
                return self._question(confused=True)
            return self._recommend(preferences, normalized, more=True)

        if not self._has_preferences(preferences):
            return self._question()
        return self._recommend(preferences, normalized)
