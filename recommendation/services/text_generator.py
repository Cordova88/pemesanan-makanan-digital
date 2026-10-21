"""Small provider-independent contract shared by the AI consumers."""

from abc import ABC, abstractmethod


class TextGenerator(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str | None:
        """Return response text, or None when generation is unavailable/failed.

        Provider adapters handle their own provider/network failures. Consumers
        remain responsible for parsing and validating the returned text.
        """

        raise NotImplementedError

    def generate_ranking(self, prompt: str) -> str | None:
        """Optional ranking format support; text-only providers keep their behavior."""

        return self.generate(prompt)
