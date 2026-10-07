from dataclasses import dataclass
from decimal import Decimal

from menu.models import MenuItem

from .language import TAG_LABELS


@dataclass(frozen=True)
class RecommendationMatch:
    item: MenuItem
    score: int
    match_reasons: tuple[str, ...]
    labels: tuple[str, ...]


class RecommendationService:
    DIRECT_TAG_WEIGHT = 4
    MOOD_TAG_WEIGHT = 2
    CATEGORY_WEIGHT = 3
    BUDGET_WEIGHT = 3
    AFFORDABLE_PRICE_CEILING = Decimal("15000.00")
    SOFT_EXCLUSION_PENALTY = 2

    def rank(self, preferences, limit=3, exclude_ids=None):
        items = (
            MenuItem.objects.filter(
                is_active=True,
                is_available=True,
                category__is_active=True,
            )
            .select_related("category")
            .prefetch_related("tags")
        )
        excluded_ids = set(exclude_ids or [])
        ranked = []

        for item in items:
            if item.id in excluded_ids:
                continue

            item_tags = {tag.name for tag in item.tags.all()}
            if item_tags & preferences.excluded_tags:
                continue
            if preferences.max_price is not None and item.price > preferences.max_price:
                continue

            score = 1 if (
                preferences.excluded_tags or preferences.soft_excluded_tags
            ) else 0
            reasons = []
            reasons.extend(
                "✅ Tanpa " + TAG_LABELS[tag]
                for tag in sorted(preferences.excluded_tags & set(TAG_LABELS))
            )
            for tag in sorted(item_tags & preferences.tags):
                score += self.DIRECT_TAG_WEIGHT
                reasons.append(TAG_LABELS.get(tag))
            for tag in sorted((item_tags & preferences.mood_tags) - preferences.tags):
                score += self.MOOD_TAG_WEIGHT
                reasons.append(TAG_LABELS.get(tag))

            if item_tags & preferences.soft_excluded_tags:
                score -= self.SOFT_EXCLUSION_PENALTY

            if preferences.category and item.category.name.casefold() == preferences.category.casefold():
                score += self.CATEGORY_WEIGHT
                reasons.append("🍽️ Sesuai pilihan makanan")

            if preferences.max_price is not None:
                score += self.BUDGET_WEIGHT
                reasons.append("💰 Sesuai batas harga")
            elif preferences.prefer_affordable and item.price <= self.AFFORDABLE_PRICE_CEILING:
                score += self.BUDGET_WEIGHT
                reasons.append("💰 Ramah di kantong")

            if score > 0:
                labels = tuple(
                    TAG_LABELS[tag]
                    for tag in sorted(item_tags)
                    if tag in TAG_LABELS
                )
                ranked.append(
                    RecommendationMatch(
                        item=item,
                        score=score,
                        match_reasons=tuple(reason for reason in reasons if reason),
                        labels=labels,
                    )
                )

        ranked.sort(
            key=lambda match: (-match.score, match.item.price, match.item.name.casefold())
        )
        return ranked[: max(0, limit)]

    def recommend(self, preferences, limit=3, exclude_ids=None):
        """Return MenuItems for callers that do not need explanation metadata."""
        return [
            match.item
            for match in self.rank(preferences, limit=limit, exclude_ids=exclude_ids)
        ]

    def get_available_match(self, item_id):
        item = (
            MenuItem.objects.filter(
                pk=item_id,
                is_active=True,
                is_available=True,
                category__is_active=True,
            )
            .select_related("category")
            .prefetch_related("tags")
            .first()
        )
        if item is None:
            return None
        labels = tuple(
            TAG_LABELS[tag.name]
            for tag in item.tags.all()
            if tag.name in TAG_LABELS
        )
        return RecommendationMatch(
            item=item,
            score=0,
            match_reasons=(),
            labels=labels,
        )
