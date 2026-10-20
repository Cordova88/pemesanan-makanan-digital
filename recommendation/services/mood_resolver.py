from typing import ClassVar
from collections.abc import Iterable
class MoodResolver:
    """Translate detected situations into lower-weight menu characteristics."""

    RESOLUTIONS: ClassVar[dict[str, set[str]]] = {
        "tired": {"filling", "heavy_meal", "comfort_food"},
        "very_hungry": {"filling", "heavy_meal", "rice", "noodle"},
        "hot_thirsty": {"cold", "refreshing", "drink"},
        "quick": {"quick_meal"},
    }

    def resolve(self, moods: Iterable[str], *, explicit_tags: Iterable[str] = ()) -> set[str]:
        resolved = set().union(*(self.RESOLUTIONS.get(mood, set()) for mood in moods))
        explicit = set(explicit_tags)
        if explicit & {"warm", "hot", "warming"}:
            resolved.difference_update({"cold", "refreshing"})
        if explicit & {"rice", "noodle", "heavy_meal", "chicken", "beef", "fish"} and "drink" not in explicit:
            resolved.difference_update({"drink", "cold", "refreshing"})
        return resolved
