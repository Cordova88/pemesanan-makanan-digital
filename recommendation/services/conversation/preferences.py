from recommendation.services.recommendation import SearchConstraints


class PreferenceStateService:
    """Derives validated active-search constraints from an interpretation."""

    def __init__(self, context):
        self.context = context

    def constraints_for_interpretation(self, interpretation, old_follow_up=None):
        previous = self.context.search_constraints()
        has_previous = bool(
            previous.required_tags
            or previous.excluded_tags
            or previous.category
            or previous.max_price is not None
            or previous.moods
        )
        constraint_only_update = (
            not interpretation.tags
            and not interpretation.excluded_tags
            and not interpretation.category
            and (
                interpretation.max_price is not None
                or interpretation.clear_max_price
                or interpretation.prefer_affordable
                or interpretation.clear_prefer_affordable
            )
        )
        continuing = (
            old_follow_up in {"meal_type", "base"}
            or (constraint_only_update and has_previous)
        )
        explicit_clear = any(
            operation.action == "CLEAR"
            for operation in interpretation.operations
        )
        if interpretation.intent == "REPLACE_PREFERENCES":
            continuing = continuing and not explicit_clear
        if interpretation.intent == "RETRY_SEARCH":
            continuing = False

        base = previous if continuing else SearchConstraints()
        required_tags = set(base.required_tags)
        current_tags = set(interpretation.tags)
        if old_follow_up == "meal_type":
            current_tags.difference_update({"heavy_meal", "filling"})
        if continuing and interpretation.intent == "REPLACE_PREFERENCES":
            for operation in interpretation.operations:
                if operation.action == "REPLACE":
                    required_tags.difference_update(operation.remove_tags)
        required_tags.update(current_tags)
        excluded_tags = set(base.excluded_tags)
        excluded_tags.update(interpretation.excluded_tags)
        category = interpretation.category or (base.category if continuing else None)
        if interpretation.clear_max_price:
            max_price = None
        elif interpretation.max_price is not None:
            max_price = interpretation.max_price
        elif interpretation.prefer_affordable:
            max_price = None
        else:
            max_price = base.max_price if continuing else None
        moods = set(base.moods)
        if interpretation.clear_moods:
            moods.clear()
        if interpretation.moods:
            moods = set(interpretation.moods)
        return SearchConstraints(
            required_tags=frozenset(required_tags),
            excluded_tags=frozenset(excluded_tags),
            category=category,
            max_price=max_price,
            moods=frozenset(moods),
        )
