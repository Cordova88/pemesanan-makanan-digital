from menu.models import MenuItem

class RecommendationService:
    def recommend(self, preferences, limit=3, exclude_ids=None):
        items = MenuItem.objects.filter(is_active=True, is_available=True, category__is_active=True).prefetch_related('tags')
        exclude_ids = set(exclude_ids or [])
        ranked = []
        for item in items:
            if item.id in exclude_ids: continue
            if preferences.max_price and item.price > preferences.max_price: continue
            tags = {tag.name for tag in item.tags.all()}; score = len(tags & set(preferences.tags)) * 3
            if preferences.max_price and item.price <= preferences.max_price: score += 2
            if score: ranked.append((score, item))
        return [item for _, item in sorted(ranked, key=lambda pair: (-pair[0], pair[1].price, pair[1].name))[:limit]]
