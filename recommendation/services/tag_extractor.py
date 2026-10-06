import re
from dataclasses import dataclass, field

@dataclass
class Preferences:
    tags: set = field(default_factory=set)
    max_price: int | None = None
    category: str | None = None

class TagExtractor:
    KEYWORDS = {"spicy": ("pedas", "spicy", "sambal", "cabai"), "chicken": ("ayam",), "beef": ("sapi", "daging"), "noodle": ("mie", "mi"), "rice": ("nasi",), "sweet": ("manis",), "filling": ("kenyang", "lapar", "mengenyangkan"), "snack": ("camilan", "cemilan", "snack"), "drink": ("minum", "minuman", "haus"), "cold": ("dingin", "segar", "es"), "crispy": ("crispy", "renyah", "garing"), "cheesy": ("keju", "cheese", "mozzarella")}
    def extract(self, text):
        text = (text or "").lower(); tags = {tag for tag, words in self.KEYWORDS.items() if any(re.search(r"\b" + re.escape(word) + r"\b", text) for word in words)}
        max_price = 20000 if any(word in text for word in ("murah", "hemat", "budget")) else None
        match = re.search(r"(?:rp\.?\s*)?(\d{2,3})(?:\.?000)?", text)
        if match and ("rp" in text or "budget" in text): max_price = int(match.group(1)) * (1000 if int(match.group(1)) < 1000 else 1)
        return Preferences(tags=tags, max_price=max_price)
