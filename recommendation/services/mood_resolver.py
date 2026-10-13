# [OOP: Abstraction] resolve() menerjemahkan mood menjadi tag karakteristik; pemanggil tidak
# perlu tahu isi tabel pemetaannya.
# [OOP: Encapsulation] Tabel RESOLUTIONS dibungkus sebagai atribut class.
class MoodResolver:
    """Translate detected situations into lower-weight menu characteristics."""

    RESOLUTIONS = {
        "tired": {"filling", "heavy_meal", "comfort_food"},
        "low_mood": {"comfort_food", "sweet", "crispy", "rich"},
        "very_hungry": {"filling", "heavy_meal", "rice", "noodle"},
        "hot_thirsty": {"cold", "refreshing", "drink"},
        "quick": {"quick_meal"},
    }

    # [OOP: Abstraction] Menggabungkan tag dari semua mood yang terdeteksi menjadi satu himpunan.
    def resolve(self, moods):
        return set().union(*(self.RESOLUTIONS.get(mood, set()) for mood in moods))
