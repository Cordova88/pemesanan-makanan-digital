from dataclasses import dataclass, field
from decimal import Decimal

from menu.models import MenuItem

from .language import TAG_LABELS, tag_label

# [OOP: Encapsulation] RecommendationMatch adalah value object yang membungkus hasil satu
# rekomendasi (item, skor, alasan, label). frozen=True membuatnya immutable (tidak bisa diubah
# setelah dibuat).
# [OOP: Abstraction] @dataclass membuat __init__, __repr__, dan __eq__ secara otomatis.
# [OOP: Association] Memegang referensi ke model MenuItem (item: MenuItem).
@dataclass(frozen=True)
class RecommendationMatch:
    item: MenuItem
    score: int
    match_reasons: tuple[str, ...]
    labels: tuple[str, ...]

# [OOP: Encapsulation] SearchConstraints membungkus batasan pencarian (tag wajib/dilarang,
# kategori, harga, mood) sebagai objek yang tidak bisa diubah (frozen).
@dataclass(frozen=True)
class SearchConstraints:
    required_tags: frozenset[str] = field(default_factory=frozenset)
    excluded_tags: frozenset[str] = field(default_factory=frozenset)
    category: str | None = None
    max_price: int | None = None
    moods: frozenset[str] = field(default_factory=frozenset)

    # [OOP: Abstraction] Mengubah objek menjadi dict sederhana (mis. untuk disimpan di session).
    def to_dict(self):
        return {
            "required_tags": sorted(self.required_tags),
            "excluded_tags": sorted(self.excluded_tags),
            "category": self.category,
            "max_price": self.max_price,
            "moods": sorted(self.moods),
        }

    # [OOP: Class method / Factory] Constructor alternatif: membuat SearchConstraints dari dict.
    @classmethod
    def from_dict(cls, data):
        return cls(
            required_tags=frozenset(data.get("required_tags", [])),
            excluded_tags=frozenset(data.get("excluded_tags", [])),
            category=data.get("category"),
            max_price=data.get("max_price"),
            moods=frozenset(data.get("moods", [])),
        )


# [OOP: Abstraction] Menyediakan antarmuka sederhana (rank, recommend, find_catalog_matches,
# get_available_match) untuk mencari menu; query database dan perhitungan skor disembunyikan.
# [OOP: Encapsulation] Bobot skor (DIRECT_TAG_WEIGHT, dst.) dan himpunan PROTEIN_TAGS
# dibungkus sebagai konstanta class.
# [OOP: Association] Memakai model MenuItem dan mengembalikan objek RecommendationMatch.
class RecommendationService:
    # [OOP: Class attribute] Konstanta konfigurasi ranking milik class, bukan milik tiap objek.
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

    # [OOP: Abstraction] Satu method yang menyaring dan menghitung skor menu (tag, mood, harga,
    # kategori, pantangan); pemanggil hanya menerima daftar hasil terurut.
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
        has_criteria = bool(
            required_tags
            or excluded_tags
            or category
            or max_price is not None
            or preferences.tags
            or preferences.mood_tags
            or preferences.soft_excluded_tags
            or preferences.prefer_affordable
        )

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
                "✅ Tanpa " + tag_label(tag)
                for tag in sorted(excluded_tags & set(TAG_LABELS))
            )
            scoring_tags = item_tags & preferences.tags
            if constraints is not None:
                scoring_tags |= item_tags & set(constraints.required_tags)
            for tag in sorted(scoring_tags):
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

            if max_price is not None:
                score += self.BUDGET_WEIGHT
                reasons.append("💰 Sesuai batas harga")
            elif preferences.prefer_affordable and item.price <= self.AFFORDABLE_PRICE_CEILING:
                score += self.BUDGET_WEIGHT
                reasons.append("💰 Ramah di kantong")

            if score > 0 or not has_criteria:
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
            key=lambda match: (-match.score, match.item.price, match.item.name.casefold())
        )
        return ranked[: max(0, limit)]

    # [OOP: Abstraction] Pembungkus (wrapper) tipis di atas rank() yang hanya mengembalikan
    # MenuItem, untuk pemanggil yang tidak butuh metadata alasan.
    def recommend(self, preferences, limit=3, exclude_ids=None):
        """Return MenuItems for callers that do not need explanation metadata."""
        return [
            match.item
            for match in self.rank(preferences, limit=limit, exclude_ids=exclude_ids)
        ]

    # [OOP: Abstraction] Mencari menu yang cocok dengan tag tertentu, tanpa pemanggil perlu tahu
    # query ORM-nya.
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
            key=lambda match: (match.item.price, match.item.name.casefold()),
        )

    # [OOP: Abstraction] Mengambil satu menu yang masih tersedia sebagai RecommendationMatch.
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
            tag_label(tag.name)
            for tag in item.tags.all()
        )
        return RecommendationMatch(
            item=item,
            score=0,
            match_reasons=(),
            labels=labels,
        )
