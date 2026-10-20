"""Bounded plan deltas. Catalog, prices and persistence stay with existing services."""
from collections.abc import Iterable
from decimal import Decimal
import re

from .language import IndonesianPriceParser, normalize_text


class PlanDelta:
    def __init__(self) -> None:
        self.person_count: int | None = None
        self.quantity: int | None = None
        self.quantity_only: bool = False
        self.per_person_quantity: bool = False
        self.serving_mode: str | None = None
        self.target_role: str | None = None
        self.requested_roles: tuple[str, ...] = ()
        self.cancel_role: str | None = None
        self.category_budgets: dict[str, str] = {}
        self.role_quantities: dict[str, int] = {}
        self.total_budget: Decimal | None = None
        self.per_person_budget: Decimal | None = None
        self.entity_text: str | None = None
        self.implicit_total: Decimal | None = None
        self.clarification: str | None = None
        self.combination_request: bool = False


class PlanInterpreter:
    def __init__(self, parser: IndonesianPriceParser, categories: Iterable[str]) -> None:
        self.parser = parser
        available = {normalize_text(name): name for name in categories}
        vocabulary = {'makanan': ('makanan', 'makan'), 'minuman': ('minuman', 'minum'),
                      'camilan': ('camilan', 'cemilan')}
        self.roles = {phrase: available[name] for name, phrases in vocabulary.items()
                      if name in available for phrase in phrases}
        self.roles.update(available)

    def _count(self, value: str) -> int | None:
        amount = Decimal(value.replace(',', '.')) if re.fullmatch(r'\d+(?:[.,]\d+)?', value) else None
        if amount is None:
            integer = self.parser._word_integer(value)
            amount = Decimal(integer) if integer is not None else None
        if amount is None or amount != amount.to_integral_value() or not 1 <= amount <= 99:
            return None
        return int(amount)

    def interpret(self, text: str) -> PlanDelta:
        normalized = self.parser.normalize_money_input(text)
        delta = PlanDelta()
        mentions = self.parser.numeric_roles(normalized)
        money = [mention for mention in mentions if mention.role == 'MONEY']
        people = [mention for mention in mentions if mention.role == 'PERSON_COUNT']
        if any(normalized[:mention.start].rstrip().endswith('-') for mention in people):
            delta.clarification = 'Jumlah orang tidak boleh negatif.'
            return delta
        if people and not money:
            if len(people) != 1 or people[0].value != people[0].value.to_integral_value() or not 1 <= people[0].value <= 99:
                delta.clarification = 'Sebutkan satu jumlah orang yang utuh antara 1 dan 99.'
            elif re.search(r'\b(?:jadi|sekarang|ubah|ganti|eh|koreksi|untuk)\b', normalized) or re.fullmatch(r'.+\s+orang[.!?]*', normalized):
                delta.person_count = int(people[0].value)
        if re.search(r'\b(?:masing[- ]masing|sendiri[- ]sendiri)\b', normalized):
            delta.serving_mode = 'individual'
        elif re.search(r'\b(?:berbagi|sharing|patungan)\b', normalized):
            delta.serving_mode = 'shared'

        role_pattern = '|'.join(re.escape(name) for name in sorted(self.roles, key=len, reverse=True)) or r'(?!)'
        delta.requested_roles = tuple(dict.fromkeys(self.roles[match[1]] for match in re.finditer(r'\b(' + role_pattern + r')(?:nya)?\b', normalized)))
        delta.combination_request = bool(
            re.search(r'\b(?:kombinasi|susun paket)\b', normalized)
            or (money and len(delta.requested_roles) > 1 and re.search(r'\b(?:buat|carikan|cari)\b', normalized))
            or (money and people and delta.serving_mode == 'individual' and delta.requested_roles)
        )
        bound_role = re.match(r'^(?:aku |saya )?(' + role_pattern + r')nya\s+', normalized)
        effective = normalized
        if bound_role:
            delta.target_role = self.roles[bound_role[1]]
            effective = 'mau ' + normalized[bound_role.end():]
        cancel = re.search(r'\b(?:batal(?:kan)?|hapus|tidak jadi)\s+(?:menu\s+)?(' + role_pattern + r')(?:nya)?\b', normalized)
        if cancel is None:
            cancel = re.search(r'\b(' + role_pattern + r')(?:nya)?\s+(?:batal|dihapus|tidak jadi)\b', normalized)
        if cancel:
            delta.cancel_role = self.roles[cancel[1]]
            return delta

        digits = r'\d+(?:[.,]\d+)?'
        vocabulary = '|'.join(self.parser.WORD_DIGITS) + '|belas|puluh|ratus'
        count = r'(?:' + digits + r'|(?:' + vocabulary + r')(?:\s+(?:' + vocabulary + r')){0,5})'
        for role_count in re.finditer(r'\b(' + count + r')\s+(?:(?:porsi|menu)\s+)?(' + role_pattern + r')\b', normalized):
            if any(mention.start <= role_count.start() < mention.end for mention in money):
                continue
            if normalized[:role_count.start()].rstrip().endswith('-'):
                delta.clarification = 'Jumlah kategori tidak boleh negatif.'
                return delta
            quantity = self._count(role_count[1])
            role = self.roles[role_count[2]]
            if quantity is None or role in delta.role_quantities:
                delta.clarification = 'Sebutkan satu jumlah kategori yang utuh antara 1 dan 99.'
            else:
                delta.role_quantities[role] = quantity
        # A clear total with roles/counts can use the existing bounded planner.
        if (len(money) == 1 and (len(delta.requested_roles) > 1 or delta.role_quantities)
                and (not people or delta.serving_mode == 'individual')
                and not re.search(r'\b(?:per (?:menu|item|porsi|orang|kepala)|sekitar|kisaran|kira)\b', normalized)):
            delta.combination_request = True
        changed = re.search(r'\b(?:jadi|menjadi|ubah ke)\s+(' + count + r')\s*(?:porsi|gelas|buah|item)\b', effective)
        if changed:
            delta.quantity = self._count(changed[1])
            delta.quantity_only = True
            remainder = (effective[:changed.start()] + effective[changed.end():]).strip(' .!?')
            remainder = re.sub(r'^(?:eh|ubah|ganti)\s*', '', remainder).strip()
            if remainder and remainder not in {'mau', 'yang tadi', 'yang itu', 'itu', 'tadi'}:
                delta.entity_text = 'mau ' + remainder
            if delta.quantity is None:
                delta.clarification = 'Jumlah item harus bilangan utuh antara 1 dan 99.'
            return delta
        effective = re.sub(r'\b(?:masing[- ]masing|sendiri[- ]sendiri)\s*', '', effective).strip()
        # Only a single literal amount explicitly linked to the following items
        # can move out of the entity phrase. People/finance/ranges stay separate.
        leading_total = False
        if len(money) == 1 and not people and re.fullmatch(
                r'\s*(?:(?:budget|anggaran)\s+)?(?:total\s+)?', normalized[:money[0].start]):
            linked = re.fullmatch(r'\s+(?:untuk|buat)\s+(.+)', normalized[money[0].end:])
            if linked:
                effective = linked[1]
                if re.match(r'-\s*(' + count + r')\b', effective):
                    delta.clarification = 'Jumlah item tidak boleh negatif.'
                    return delta
                if re.search(r'\bper (?:orang|kepala)\b', effective):
                    delta.clarification = 'Untuk batas per orang, sebutkan jumlah orang dan porsi masing-masing agar nominal serta jumlah item tidak tertukar.'
                    return delta
                leading_total = True
                if delta.role_quantities and not re.search(r'\bper (?:menu|item|porsi)\b', effective):
                    delta.total_budget = money[0].value
        prefix = re.match(r'^(?P<lead>(?:(?:aku|saya)\s+)?(?:(?:mau|ingin|pesan|ambil|tambahkan|tambah|sekalian)\s+)?)'
                          r'(?P<number>' + count + r')\s+(?:(?:porsi|gelas|buah|item)\s+)?(?P<item>.+)$', effective)
        if prefix and not delta.role_quantities and (leading_total or not any(mention.start <= prefix.start('number') < mention.end for mention in money)):
            delta.quantity = self._count(prefix['number'])
            delta.per_person_quantity = delta.serving_mode == 'individual'
            delta.entity_text = (prefix['lead'] or 'mau ') + prefix['item']
            if leading_total and re.search(r'\bper (?:menu|item|porsi)\b', effective):
                # Reordering quantity must not discard the explicit unit cap.
                delta.entity_text += ' ' + normalized[money[0].start:money[0].end]
            if delta.quantity is None:
                delta.clarification = 'Jumlah item harus bilangan utuh antara 1 dan 99.'
            elif len(money) == 1 and not re.search(r'\b(?:per (?:menu|item|porsi)|maksimal|minimal|di bawah|di atas)\b', normalized):
                delta.implicit_total = money[0].value
            if re.search(r'\b(?:dan|serta)\s+(' + count + r')\s+', prefix['item']):
                delta.clarification = 'Ada beberapa menu dengan jumlah berbeda. Sebutkan satu menu beserta jumlahnya per pesan agar tidak tertukar.'
        elif bound_role:
            delta.entity_text = effective

        allocations: dict[str, str] = {}
        used = 0
        total_seen = False
        for index, mention in enumerate(money):
            before, after = normalized[:mention.start], normalized[mention.end:]
            # Bind only adjacent category words inside this amount's clause.
            # Do not reach past another amount or a conjunction to borrow a role.
            clause_before = before[money[index - 1].end:] if index else before
            clause_before = re.split(r'[,;]|\b(?:dan|serta)\b', clause_before)[-1]
            role = re.search(r'\b(' + role_pattern + r')(?:nya)?\s*(?:(?:maksimal|budget|anggaran|jatah|alokasi)\s*)?$', clause_before)
            following = re.match(r'\s+(?:(?:buat|untuk)\s+)?(' + role_pattern + r')(?:nya)?\b', after)
            total = bool(re.search(r'\b(?:total|keseluruhan)\s*$', clause_before)
                         or re.match(r'\s+(?:total|keseluruhan)\b', after))
            if total:
                if len(money) > 1 and (role or following):
                    delta.clarification = 'Nominal ini untuk total atau kategori? Pisahkan cakupannya agar jelas.'
                if total_seen:
                    delta.clarification = 'Sebutkan satu budget total agar nominalnya tidak tertukar.'
                total_seen = True
                delta.total_budget = mention.value
                used += 1
            elif re.match(r'\s+per (?:orang|kepala)\b', after) or re.search(
                    r'\b(?:masing[- ]masing|sendiri[- ]sendiri)\s*$', before):
                delta.per_person_budget = mention.value
                used += 1
            elif role or following:
                category = self.roles[(role or following)[1]]
                if following:
                    tail = re.split(r'[,;]|\b(?:dan|serta)\b', after[following.end():])[0].strip(' .!?')
                    if len(money) > 1 and tail:
                        delta.clarification = 'Sebutkan nominal dan satu kategori untuk setiap alokasi. Pisahkan pilihan menu dalam pesan berikutnya.'
                if role and following and self.roles[following[1]] != category:
                    delta.clarification = 'Nominal ini berada di antara dua kategori. Pisahkan setiap alokasi dengan koma atau dan.'
                if category in allocations:
                    delta.clarification = 'Ada lebih dari satu nominal untuk kategori yang sama. Sebutkan satu batas alokasinya.'
                allocations[category] = str(mention.value)
                used += 1
        allocation_request = (len(money) > 1 and bool(allocations) and len(delta.requested_roles) > 1) or len(allocations) > 1 or (allocations and (
            re.search(r'\b(?:alokasi|jatah)\b', normalized) or delta.total_budget is not None))
        if allocation_request:
            delta.category_budgets = allocations
        if (allocation_request or delta.total_budget is not None and delta.per_person_budget is not None
                or delta.per_person_budget is not None and delta.serving_mode == 'individual') and used != len(money):
            delta.clarification = 'Sebagian nominal belum jelas cakupannya. Sebutkan total, per orang, atau kategori untuk setiap nominal.'
        if allocation_request:
            if re.search(r'\b(?:sekitar|kisaran|kira|minimal|di atas|lebih dari|di bawah|kurang dari|sampai|hingga|atau)\b', normalized) or any(
                    normalized[:mention.start].rstrip().endswith('-') for mention in money):
                delta.clarification = 'Sebutkan satu batas maksimal yang jelas untuk setiap kategori, tanpa rentang atau perkiraan.'
            if len(allocations) > 1:
                combined = sum((Decimal(value) for value in allocations.values()), Decimal(0))
                if delta.total_budget is not None and combined > delta.total_budget:
                    delta.clarification = 'Jumlah alokasi kategori melebihi budget total yang disebutkan. Sesuaikan total atau alokasinya.'
                elif delta.total_budget is None and delta.per_person_budget is None:
                    delta.implicit_total = combined
                # Explicit allocation edits keep the existing selected plan;
                # natural category requests use the established bounded solver.
                if not re.search(r'\b(?:alokasi|jatah)\b', normalized):
                    delta.combination_request = True
        if delta.combination_request:
            bindings = list(re.finditer(r'(?:^|[,;]\s*)(' + role_pattern + r')nya\s+([^,;]+)', normalized))
            if len(bindings) > 1 or bindings and bindings[0].end() != len(normalized):
                delta.clarification = 'Sebutkan satu pilihan menu kategori yang spesifik per pesan agar tidak tertukar.'
            elif bindings:
                delta.target_role = self.roles[bindings[0][1]]
                delta.entity_text = 'mau ' + bindings[0][2].strip()
        return delta
