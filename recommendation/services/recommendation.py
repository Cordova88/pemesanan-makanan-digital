from dataclasses import dataclass, field
from decimal import Decimal

from menu.models import MenuItem

from .language import TAG_LABELS


@dataclass(frozen=True)
class RecommendationMatch:
    item: MenuItem
    score: int
    match_reasons: tuple[str, ...]
    labels: tuple[str, ...]


@dataclass(frozen=True)
class SearchConstraints:
    required_tags: frozenset[str] = field(default_factory=frozenset)
    excluded_tags: frozenset[str] = field(default_factory=frozenset)
    category: str | None = None
    max_price: int | None = None
    moods: frozenset[str] = field(default_factory=frozenset)

    def to_dict(self):
        return {
            "required_tags": sorted(self.required_tags),
            "excluded_tags": sorted(self.excluded_tags),
            "category": self.category,
            "max_price": self.max_price,
            "moods": sorted(self.moods),
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            required_tags=frozenset(data.get("required_tags", [])),
            excluded_tags=frozenset(data.get("excluded_tags", [])),
            category=data.get("category"),
            max_price=data.get("max_price"),
            moods=frozenset(data.get("moods", [])),
        )


class RecommendationService:
    DIRECT_TAG_WEIGHT = 4
    MOOD_TAG_WEIGHT = 2
    CATEGORY_WEIGHT = 3
    BUDGET_WEIGHT = 3
    AFFORDABLE_PRICE_CEILING = Decimal("15000.00")
    SOFT_EXCLUSION_PENALTY = 2
    PROTEIN_TAGS = {
        "chicken",
        "beef",
        "seafood",
        "shrimp",
        "fish",
        "egg",
        "tofu",
        "tempeh",
    }

    def rank(
        self,
        preferences,
        limit=3,
        exclude_ids=None,
        required_tags=None,
        constraints=None,
    ):
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
        if constraints is not None:
            required_tags = set(constraints.required_tags)
            max_price = constraints.max_price
            category = constraints.category
            excluded_tags = preferences.excluded_tags | set(constraints.excluded_tags)
        else:
            required_tags = (
                set(required_tags)
                if required_tags is not None
                else preferences.tags & self.PROTEIN_TAGS
            )
            max_price = preferences.max_price
            category = preferences.category
            excluded_tags = preferences.excluded_tags
        ranked = []

        for item in items:
            if item.id in excluded_ids:
                continue
            item_tags = {tag.name for tag in item.tags.all()}
            if not required_tags.issubset(item_tags):
                continue
            if item_tags & excluded_tags:
                continue
            if max_price is not None and item.price > max_price:
                continue
            if category and item.category.name.casefold() != category.casefold():
                continue

            score = 1 if (
                excluded_tags or preferences.soft_excluded_tags
            ) else 0
            reasons = []
            reasons.extend(
                "✅ Tanpa " + TAG_LABELS[tag]
                for tag in sorted(excluded_tags & set(TAG_LABELS))
            )
            for tag in sorted(item_tags & preferences.tags):
                score += self.DIRECT_TAG_WEIGHT
                if constraints is None or tag in constraints.required_tags:
                    reasons.append(TAG_LABELS.get(tag))
            for tag in sorted((item_tags & preferences.mood_tags) - preferences.tags):
                score += self.MOOD_TAG_WEIGHT
                reasons.append(TAG_LABELS.get(tag))

            if item_tags & preferences.soft_excluded_tags:
                score -= self.SOFT_EXCLUSION_PENALTY

            if category and item.category.name.casefold() == category.casefold():
                score += self.CATEGORY_WEIGHT
                reasons.append("🍽️ Sesuai pilihan makanan")

            if max_price is not None:
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

    def find_catalog_matches(
        self,
        tags,
        excluded_tags=None,
        category=None,
        max_price=None,
    ):
        required_tags = set(tags)
        excluded_tags = set(excluded_tags or [])
        if not required_tags:
            return []

        item_query = MenuItem.objects.filter(
                is_active=True,
                is_available=True,
                category__is_active=True,
                tags__name__in=required_tags,
            )
        if category:
            item_query = item_query.filter(category__name__iexact=category)
        if max_price is not None:
            item_query = item_query.filter(price__lte=max_price)
        items = (
            item_query
            .select_related("category")
            .prefetch_related("tags")
            .distinct()
        )
        matches = []
        for item in items:
            item_tags = {tag.name for tag in item.tags.all()}
            if (
                not required_tags.issubset(item_tags)
                or item_tags & excluded_tags
            ):
                continue
            reasons = tuple(
                TAG_LABELS[tag]
                for tag in sorted(required_tags)
                if tag in TAG_LABELS
            )
            labels = tuple(
                TAG_LABELS[tag]
                for tag in sorted(item_tags)
                if tag in TAG_LABELS
            )
            matches.append(
                RecommendationMatch(
                    item=item,
                    score=0,
                    match_reasons=reasons,
                    labels=labels,
                )
            )
        return sorted(
            matches,
            key=lambda match: (match.item.price, match.item.name.casefold()),
        )

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
