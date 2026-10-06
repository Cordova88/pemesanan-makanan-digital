from .language import TAG_LABELS, normalize_text
from .mood_extractor import MoodExtractor
from .mood_resolver import MoodResolver
from .recommendation import RecommendationService
from .tag_extractor import Preferences, TagExtractor


class ChatbotService:
    SESSION_KEY = "recommendation_state"
    SHOWN_KEY = "recommendation_shown"
    RESET_PHRASES = {"reset", "mulai lagi", "mulai dari awal"}
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

    def reset(self):
        self.session.pop(self.SESSION_KEY, None)
        self.session.pop(self.SHOWN_KEY, None)
        self.session.modified = True

    def _preferences(self):
        return Preferences.from_dict(self.session.get(self.SESSION_KEY, {}))

    def _save(self, preferences, state, follow_up=None):
        self.session[self.SESSION_KEY] = preferences.to_dict(
            state=state,
            follow_up=follow_up,
        )
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
        return {
            "message": message,
            "state": "COLLECTING_PREFERENCES",
            "preferences": Preferences().to_dict(),
            "recommendations": [],
            "quick_replies": replies,
        }

    def _ask_meal_type(self, preferences):
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

    def _recommend(self, preferences, source_text, more=False):
        preferences.mood_tags = self.mood_resolver.resolve(preferences.moods)
        previously_shown = self.session.get(self.SHOWN_KEY, []) if more else []
        matches = self.recommender.rank(
            preferences,
            exclude_ids=previously_shown,
        )
        self.session[self.SHOWN_KEY] = previously_shown + [
            match.item.id for match in matches
        ]
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

    def reply(self, message, more=False, action=None):
        normalized = normalize_text(message)
        action = action or ""
        if action == "reset" or normalized in self.RESET_PHRASES:
            self.reset()
            return self._question()

        more = more or action == "more" or normalized in self.MORE_PHRASES
        preferences = self._preferences()
        old_follow_up = self.session.get(self.SESSION_KEY, {}).get("follow_up")
        extracted = self.tag_extractor.extract(normalized)
        preferences.tags.update(extracted.tags)
        preferences.excluded_tags.update(extracted.excluded_tags)
        preferences.soft_excluded_tags.update(extracted.soft_excluded_tags)
        preferences.tags.difference_update(preferences.excluded_tags)
        preferences.tags.difference_update(preferences.soft_excluded_tags)
        preferences.excluded_tags.difference_update(preferences.tags)
        preferences.moods.update(self.mood_extractor.extract(normalized))
        preferences.mood_tags = self.mood_resolver.resolve(preferences.moods)
        if extracted.max_price is not None:
            preferences.max_price = extracted.max_price
        if extracted.category:
            preferences.category = extracted.category
        preferences.prefer_affordable = (
            preferences.prefer_affordable or extracted.prefer_affordable
        )

        if more:
            if not self._has_preferences(preferences):
                return self._question(confused=True)
            return self._recommend(preferences, normalized, more=True)

        if "confused" in self.mood_extractor.extract(normalized):
            meaningful_detail = bool(
                preferences.tags
                or preferences.mood_tags
                or preferences.excluded_tags
                or preferences.soft_excluded_tags
                or preferences.max_price is not None
                or preferences.prefer_affordable
            )
            if not meaningful_detail:
                return self._question(confused=True)
            return self._recommend(preferences, normalized)

        if (
            old_follow_up == "meal_type"
            and "heavy_meal" in preferences.tags
            and not preferences.tags.intersection({"rice", "noodle", "snack"})
        ):
            return self._ask_base(preferences)

        only_spicy = (
            preferences.tags.intersection({"spicy"}) == {"spicy"}
            and len(preferences.tags) == 1
            and not preferences.moods
            and preferences.max_price is None
            and not preferences.prefer_affordable
            and not preferences.excluded_tags
        )
        if only_spicy and old_follow_up is None:
            return self._ask_meal_type(preferences)

        if not self._has_preferences(preferences):
            return self._question()

        return self._recommend(preferences, normalized)
