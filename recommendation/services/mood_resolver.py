class MoodResolver:
    """Translate detected situations into lower-weight menu characteristics."""

    RESOLUTIONS = {
        "tired": {"filling", "heavy_meal", "comfort_food"},
        "low_mood": {"comfort_food", "sweet", "crispy", "rich"},
        "very_hungry": {"filling", "heavy_meal", "rice", "noodle"},
        "hot_thirsty": {"cold", "refreshing", "drink"},
        "quick": {"quick_meal"},
    }

    def resolve(self, moods):
        return set().union(*(self.RESOLUTIONS.get(mood, set()) for mood in moods))
