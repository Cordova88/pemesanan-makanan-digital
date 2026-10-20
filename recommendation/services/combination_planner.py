"""Pure bounded search over already eligible, already quoted catalog facts."""
from collections.abc import Mapping, Sequence
from decimal import Decimal


class CombinationCandidate:
    def __init__(self, menu_id: int, unit_price: Decimal) -> None:
        if type(menu_id) is not int or menu_id <= 0 or not unit_price.is_finite() or unit_price < 0:
            raise ValueError('Invalid candidate fact')
        self.menu_id = menu_id
        self.unit_price = unit_price


class CombinationProposal:
    def __init__(self, quantities: Mapping[int, int], total: Decimal | None,
                 *, limited: bool, nodes: int, reason: str | None = None) -> None:
        self.quantities = dict(quantities)
        self.total = total
        self.limited = limited
        self.nodes = nodes
        self.reason = reason


class CombinationPlanner:
    MAX_CANDIDATES = 16
    MAX_ROLES = 3
    MAX_SLOTS = 8
    MAX_ENTRIES = 8
    MAX_NODES = 10000

    def propose(self, pools: Mapping[str, Sequence[CombinationCandidate]],
                quantities: Mapping[str, int], *, maximum: Decimal | None,
                category_limits: Mapping[str, Decimal] | None = None,
                people: int | None = None, per_person: Decimal | None = None,
                individual: bool = False) -> CombinationProposal:
        """Find a feasible multiset; no database, filters, sessions or repricing.

        The first feasible plan follows the caller's deterministic preference
        order. It is not advertised as the optimal or only possible plan.
        """
        if (not quantities or len(quantities) > self.MAX_ROLES
                or any(type(qty) is not int or qty < 1 for qty in quantities.values())
                or sum(quantities.values()) > self.MAX_SLOTS
                or set(pools) != set(quantities)):
            return CombinationProposal({}, None, limited=True, nodes=0, reason='bounds')
        limited = any(len(pool) > self.MAX_CANDIDATES for pool in pools.values())
        selected = {role: tuple(pool[:self.MAX_CANDIDATES]) for role, pool in pools.items()}
        # One SKU cannot belong to two roles. Reject malformed fact pools.
        owners = {}
        for role, pool in selected.items():
            for candidate in pool:
                if candidate.menu_id in owners and owners[candidate.menu_id] != role:
                    raise ValueError('Candidate belongs to multiple roles')
                owners[candidate.menu_id] = role
        slots = [role for role, quantity in quantities.items() for _ in range(quantity)]
        counts: dict[int, int] = {}
        role_totals = {role: Decimal(0) for role in quantities}
        costs = {candidate.menu_id: candidate.unit_price for pool in selected.values() for candidate in pool}
        caps = category_limits or {}
        nodes = 0
        exhausted = False

        def visit(position: int, total: Decimal, first_index: int = 0) -> dict[int, int] | None:
            nonlocal nodes, exhausted
            if position == len(slots):
                if individual and per_person is not None:
                    # Conservative bound shared with the coordinator. Unknown
                    # mixed assignment must not be declared individually safe.
                    if not people or sum((costs[key] * ((qty + people - 1) // people)
                                         for key, qty in counts.items()), Decimal(0)) > per_person:
                        return None
                return dict(counts)
            role = slots[position]
            for index in range(first_index, len(selected[role])):
                if nodes >= self.MAX_NODES:
                    exhausted = True
                    return None
                nodes += 1
                candidate = selected[role][index]
                price = candidate.unit_price
                if maximum is not None and total + price > maximum:
                    continue
                if role in caps and role_totals[role] + price > caps[role]:
                    continue
                counts[candidate.menu_id] = counts.get(candidate.menu_id, 0) + 1
                role_totals[role] += price
                same_role = position + 1 < len(slots) and slots[position + 1] == role
                found = visit(position + 1, total + price, index if same_role else 0)
                role_totals[role] -= price
                counts[candidate.menu_id] -= 1
                if not counts[candidate.menu_id]:
                    del counts[candidate.menu_id]
                if found is not None:
                    return found
                if exhausted:
                    return None
            return None

        result = visit(0, Decimal(0))
        return CombinationProposal(result or {},
            sum((costs[key] * qty for key, qty in result.items()), Decimal(0)) if result else None,
            limited=limited or exhausted, nodes=nodes,
            reason=None if result else 'limited' if limited or exhausted else 'no_match')
