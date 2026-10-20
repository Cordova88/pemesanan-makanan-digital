from collections.abc import Collection
from .tag_extractor import Preferences
from decimal import Decimal
from types import NotImplementedType
from typing import ClassVar, Self, TypedDict

from menu.models import MenuItem
from menu.selection import MenuSelection
from django.db.models import Q

from .language import TAG_LABELS, tag_label
from .budget import BudgetConstraint, BudgetPayload


class RecommendationMatch:
    """Read-only ranking metadata; the referenced Django model stays mutable."""

    __slots__ = ("__item", "__score", "__match_reasons", "__labels")
    __match_args__: ClassVar[tuple[str, ...]] = ("item", "score", "match_reasons", "labels")

    def __init__(
        self,
        item: MenuItem,
        score: int,
        match_reasons: tuple[str, ...],
        labels: tuple[str, ...],
    ) -> None:
        self.__item: MenuItem = item
        self.__score: int = score
        self.__match_reasons: tuple[str, ...] = match_reasons
        self.__labels: tuple[str, ...] = labels

    @property
    def item(self) -> MenuItem:
        return self.__item

    @property
    def score(self) -> int:
        return self.__score

    @property
    def match_reasons(self) -> tuple[str, ...]:
        return self.__match_reasons

    @property
    def labels(self) -> tuple[str, ...]:
        return self.__labels

    def __eq__(self, other: object) -> bool | NotImplementedType:
        if not isinstance(other, RecommendationMatch) or type(self) is not type(other):
            return NotImplemented
        return (self.item, self.score, self.match_reasons, self.labels) == (
            other.item, other.score, other.match_reasons, other.labels,
        )

    def __hash__(self) -> int:
        return hash((self.item, self.score, self.match_reasons, self.labels))

    def __repr__(self) -> str:
        return (
            f"{type(self).__qualname__}(item={self.item!r}, score={self.score!r}, "
            f"match_reasons={self.match_reasons!r}, labels={self.labels!r})"
        )


class SearchConstraintsPayload(TypedDict, total=False):
    required_tags: list[str]
    excluded_tags: list[str]
    category: str | None
    max_price: int | None
    moods: list[str]
    budget: BudgetPayload
    soft_target: str


class SearchConstraints:
    """Read-only filters for the active search, separate from saved preferences."""

    __slots__ = ("__required_tags", "__excluded_tags", "__category", "__max_price", "__moods", "__budget", "__soft_target")
    __match_args__: ClassVar[tuple[str, ...]] = (
        "required_tags", "excluded_tags", "category", "max_price", "moods",
    )

    def __init__(
        self,
        required_tags: frozenset[str] = frozenset(),
        excluded_tags: frozenset[str] = frozenset(),
        category: str | None = None,
        max_price: int | None = None,
        moods: frozenset[str] = frozenset(),
        *, budget: BudgetConstraint | None = None,
        soft_target: Decimal | None = None,
    ) -> None:
        self.__required_tags: frozenset[str] = required_tags
        self.__excluded_tags: frozenset[str] = excluded_tags
        self.__category: str | None = category
        self.__max_price: int | None = max_price
        self.__moods: frozenset[str] = moods
        self.__budget: BudgetConstraint | None = budget
        if soft_target is not None:
            BudgetConstraint(maximum=soft_target)
        self.__soft_target: Decimal | None = soft_target

    @property
    def soft_target(self) -> Decimal | None:
        return self.__soft_target

    @property
    def required_tags(self) -> frozenset[str]:
        return self.__required_tags

    @property
    def excluded_tags(self) -> frozenset[str]:
        return self.__excluded_tags

    @property
    def category(self) -> str | None:
        return self.__category

    @property
    def max_price(self) -> int | None:
        if self.budget is not None:
            return self.budget.legacy_maximum
        return self.__max_price

    @property
    def budget(self) -> BudgetConstraint | None:
        return self.__budget

    @staticmethod
    def tags_with_category(tags: Collection[str], category_name: str) -> frozenset[str]:
        """Category is sufficient evidence of drink type, never of taste/ingredients.

        This is a filter view only: stored tags, public labels and score weights
        remain based on the catalog's actual metadata.
        """
        result = set(tags)
        if category_name.strip().casefold() == 'minuman':
            result.add('drink')
        return frozenset(result)

    @property
    def moods(self) -> frozenset[str]:
        return self.__moods

    def __eq__(self, other: object) -> bool | NotImplementedType:
        if not isinstance(other, SearchConstraints) or type(self) is not type(other):
            return NotImplemented
        return (self.required_tags, self.excluded_tags, self.category, self.max_price, self.moods, self.budget, self.soft_target) == (
            other.required_tags, other.excluded_tags, other.category, other.max_price, other.moods, other.budget, other.soft_target,
        )

    def __hash__(self) -> int:
        return hash((self.required_tags, self.excluded_tags, self.category, self.max_price, self.moods, self.budget, self.soft_target))

    def __repr__(self) -> str:
        return (
            f"{type(self).__qualname__}(required_tags={self.required_tags!r}, "
            f"excluded_tags={self.excluded_tags!r}, category={self.category!r}, "
            f"max_price={self.max_price!r}, moods={self.moods!r})"
        )

    def to_dict(self) -> SearchConstraintsPayload:
        payload: SearchConstraintsPayload = {
            "required_tags": sorted(self.required_tags),
            "excluded_tags": sorted(self.excluded_tags),
            "category": self.category,
            "max_price": self.max_price,
            "moods": sorted(self.moods),
        }
        if self.budget is not None:
            payload["budget"] = self.budget.to_dict()
        if self.soft_target is not None:
            payload['soft_target'] = str(self.soft_target)
        return payload

    @classmethod
    def from_dict(cls, data: SearchConstraintsPayload) -> Self:
        return cls(
            required_tags=frozenset(data.get("required_tags", [])),
            excluded_tags=frozenset(data.get("excluded_tags", [])),
            category=data.get("category"),
            max_price=data.get("max_price"),
            moods=frozenset(data.get("moods", [])),
            budget=BudgetConstraint.from_dict(data["budget"]) if "budget" in data else None,
            soft_target=Decimal(data['soft_target']) if 'soft_target' in data else None,
        )


class RecommendationService:
    DIRECT_TAG_WEIGHT: ClassVar[int] = 4
    MOOD_TAG_WEIGHT: ClassVar[int] = 2
    CATEGORY_WEIGHT: ClassVar[int] = 3
    BUDGET_WEIGHT: ClassVar[int] = 3
    AFFORDABLE_PRICE_CEILING: ClassVar[Decimal] = Decimal("15000.00")
    SOFT_EXCLUSION_PENALTY: ClassVar[int] = 2
    PROTEIN_TAGS: ClassVar[set[str]] = {
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
        preferences: Preferences,
        limit: int = 3,
        exclude_ids: Collection[int] | None = None,
        required_tags: Collection[str] | None = None,
        constraints: SearchConstraints | None = None,
        *, include_unscored: bool = False,
    ) -> list[RecommendationMatch]:
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
        ranked: list[RecommendationMatch] = []
        prices = {}

        for item in items:
            if item.id in excluded_ids:
                continue
            payable = MenuSelection.minimum_payable(item)
            if payable is None:
                continue
            prices[item.pk] = payable
            item_tags = {tag.name for tag in item.tags.all()}
            filter_tags = SearchConstraints.tags_with_category(item_tags, item.category.name)
            if not required_tags.issubset(filter_tags):
                continue
            if filter_tags & excluded_tags:
                continue
            if constraints is not None and constraints.budget is not None and not constraints.budget.allows(payable):
                continue
            if max_price is not None and payable > max_price:
                continue
            if category and item.category.name.casefold() != category.casefold():
                continue

            score = 1 if (
                excluded_tags or preferences.soft_excluded_tags or preferences.prefer_affordable
            ) else 0
            reasons: list[str] = []
            # Missing a catalog tag does not verify the absence of an ingredient.
            # Hard exclusion filters remain active without making a "free from" claim.
            for tag in sorted(item_tags & preferences.tags):
                score += self.DIRECT_TAG_WEIGHT
                if constraints is None or tag in constraints.required_tags:
                    reasons.append(tag_label(tag))
            for tag in sorted((item_tags & preferences.mood_tags) - preferences.tags):
                score += self.MOOD_TAG_WEIGHT
                reasons.append(tag_label(tag))

            if item_tags & preferences.soft_excluded_tags:
                score -= self.SOFT_EXCLUSION_PENALTY

            if category and item.category.name.casefold() == category.casefold():
                score += self.CATEGORY_WEIGHT
                reasons.append("🍽️ Sesuai pilihan makanan")

            if max_price is not None or (constraints is not None and constraints.budget is not None):
                score += self.BUDGET_WEIGHT
                reasons.append("💰 Sesuai batas harga")
            elif preferences.prefer_affordable and payable <= self.AFFORDABLE_PRICE_CEILING:
                score += self.BUDGET_WEIGHT
                reasons.append("💰 Ramah di kantong")

            if score > 0 or include_unscored or (constraints is not None and constraints.soft_target is not None):
                labels = tuple(
                    tag_label(tag)
                    for tag in sorted(item_tags)
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
            key=lambda match: (
                abs(prices[match.item.pk] - constraints.soft_target) if constraints is not None and constraints.soft_target is not None else Decimal(0),
                -match.score, prices[match.item.pk], match.item.name.casefold(),
            )
        )
        return ranked[: max(0, limit)]

    def recommend(
        self,
        preferences: Preferences,
        limit: int = 3,
        exclude_ids: Collection[int] | None = None,
    ) -> list[MenuItem]:
        """Return MenuItems for callers that do not need explanation metadata."""
        return [
            match.item
            for match in self.rank(preferences, limit=limit, exclude_ids=exclude_ids)
        ]

    def find_catalog_matches(
        self,
        tags: Collection[str],
        excluded_tags: Collection[str] | None = None,
        category: str | None = None,
        max_price: int | None = None,
        *, budget: BudgetConstraint | None = None, soft_target: Decimal | None = None,
    ) -> list[RecommendationMatch]:
        required_tags = set(tags)
        excluded_tags = set(excluded_tags or [])
        if not required_tags:
            return []

        tag_filter = Q(tags__name__in=required_tags)
        if 'drink' in required_tags:
            tag_filter |= Q(category__name__iexact='Minuman')
        item_query = MenuItem.objects.filter(
                tag_filter,
                is_active=True,
                is_available=True,
                category__is_active=True,
            )
        if category:
            item_query = item_query.filter(category__name__iexact=category)
        items = (
            item_query
            .select_related("category")
            .prefetch_related("tags")
            .distinct()
        )
        matches: list[RecommendationMatch] = []
        prices = {}
        for item in items:
            payable = MenuSelection.minimum_payable(item)
            if payable is None or (max_price is not None and payable > max_price) or (budget is not None and not budget.allows(payable)):
                continue
            prices[item.pk] = payable
            item_tags = {tag.name for tag in item.tags.all()}
            filter_tags = SearchConstraints.tags_with_category(item_tags, item.category.name)
            if (
                not required_tags.issubset(filter_tags)
                or filter_tags & excluded_tags
            ):
                continue
            reasons = tuple(
                tag_label(tag)
                for tag in sorted(required_tags)
            )
            labels = tuple(
                tag_label(tag)
                for tag in sorted(item_tags)
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
            key=lambda match: (abs(prices[match.item.pk] - soft_target) if soft_target is not None else Decimal(0),
                               prices[match.item.pk], match.item.name.casefold()),
        )

    def get_available_match(self, item_id: int) -> RecommendationMatch | None:
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
            tag_label(tag.name)
            for tag in item.tags.all()
        )
        return RecommendationMatch(
            item=item,
            score=0,
            match_reasons=(),
            labels=labels,
        )
