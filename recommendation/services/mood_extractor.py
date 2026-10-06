from .language import normalize_text
import re


class MoodExtractor:
    PHRASES = {
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

    def extract(self, text):
        normalized = normalize_text(text)
        moods = set()
        for mood, phrases in self.PHRASES.items():
            if any(self._contains(normalized, normalize_text(phrase)) for phrase in phrases):
                moods.add(mood)
        return moods

    @staticmethod
    def _contains(text, phrase):
        return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text) is not None
