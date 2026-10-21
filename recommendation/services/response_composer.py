"""Local language variants; persists template IDs, never conversation text."""

from collections.abc import Sequence
from hashlib import sha256
from decimal import Decimal
from typing import ClassVar
import re

from django.contrib.sessions.backends.base import SessionBase
from .budget import BudgetConstraint
from .language import tag_label
from .response_plan import ResponsePlan


class LocalResponseComposer:
    HISTORY_KEY: ClassVar[str] = 'recommendation_response_templates'
    MAX_BANKS: ClassVar[int] = 24
    MAX_RECENT: ClassVar[int] = 9
    NONFOOD: ClassVar[tuple[str, ...]] = (
        'Untuk {entity}, aku tidak bisa membantu pembelian barang itu di sini. Aku bisa bantu memilih makanan atau minuman dari menu kami.',
        'Di sini tidak menjual {entity}. Kalau ingin makanan atau minuman, aku bisa bantu melihat pilihan menu.',
        '{entity} bukan bagian dari menu restoran ini. Mau mencari makanan atau minuman?',
        'Kalau mencari {entity}, pilihan itu tidak ada di menu kami. Aku bisa bantu memilih makanan atau minuman.',
        'Untuk {entity}, restoran ini tidak menyediakan barang tersebut. Pilihan makanan atau minuman bisa kita lihat bersama.',
        'Aku belum bisa membantu mencari {entity} di sini. Yang bisa kubantu adalah memilih makanan atau minuman dari menu restoran.',
        'Menu kami berisi makanan dan minuman, jadi {entity} tidak dijual di sini. Lagi ingin yang seperti apa?',
        'Sepertinya kamu sedang mencari {entity}. Di sini pilihannya makanan atau minuman. Aku bisa bantu mencarikan menu.',
        '{entity} tidak termasuk barang yang dijual restoran ini. Kalau mau beralih mencari makanan atau minuman, aku siap membantu.',
        'Aku bisa membantu urusan menu makanan atau minuman, tetapi bukan pembelian {entity}. Mau melihat pilihan menu?',
    )

    def __init__(self, session: SessionBase) -> None:
        self._session: SessionBase = session

    def _history(self) -> dict[str, list[int]]:
        stored = self._session.get(self.HISTORY_KEY, {})
        history: dict[str, list[int]] = {}

        if isinstance(stored, dict):
            for key, values in list(stored.items())[-self.MAX_BANKS :]:
                if isinstance(key, str) and len(key) <= 32 and isinstance(values, list):
                    history[key] = [
                        value
                        for value in values[-self.MAX_RECENT :]
                        if type(value) is int and value >= 0
                    ]

        return history

    def choose(self, bank: str, variants: Sequence[str]) -> str:
        if not variants:
            raise ValueError('At least one response variant is required')

        history = self._history()
        recent = [value for value in history.get(bank, []) if value < len(variants)]
        blocked = (
            set(recent[-min(self.MAX_RECENT, len(variants) - 1) :]) if len(variants) > 1 else set()
        )
        selected = next((index for index in range(len(variants)) if index not in blocked), 0)
        history.pop(bank, None)
        history[bank] = (recent + [selected])[-self.MAX_RECENT :]
        self._session[self.HISTORY_KEY] = dict(list(history.items())[-self.MAX_BANKS :])

        return variants[selected]

    def nonfood(self, entity: str) -> str:
        return self.choose('nonfood', self.NONFOOD).format(entity=entity)

    @staticmethod
    def money(amount: Decimal) -> str:
        """Presentation only; retain meaningful rupiah fractions."""
        value = BudgetConstraint.rupiah(amount)

        return value[:-3] if value.endswith(',00') else value

    @staticmethod
    def readable_label(tag: str) -> str:
        return re.sub(r'^[^\w]+', '', tag_label(tag)).strip().casefold()

    def compose(self, plan: ResponsePlan) -> str:
        if plan.required_clarification is not None:
            return plan.required_clarification

        banks = {
            'correction': (
                'Oke, aku ikuti perubahan pilihanmu.',
                'Baik, kita pakai pilihan yang baru.',
                'Siap, pencariannya sudah mengikuti perubahanmu.',
            ),
            'removal': (
                'Siap, pencarian mengikuti perubahan preferensimu.',
                'Oke, kita sesuaikan pilihannya.',
                'Baik, ini hasil setelah perubahan preferensimu.',
            ),
        }
        opening = self.choose(
            'opening_' + plan.purpose,
            banks.get(
                plan.purpose,
                (
                    'Ini pilihan {kind} untukmu.',
                    'Aku pilihkan {kind} yang bisa kamu pertimbangkan.',
                    'Untuk {kind}, ini pilihannya.',
                    'Yuk, lihat pilihan {kind}nya.',
                ),
            ),
        )
        payload = plan.to_dict()
        constraints = payload['constraints']
        category = constraints.get('category')
        opening = opening.format(kind=category.casefold() if category else 'menu')
        labels = list(
            dict.fromkeys(self.readable_label(tag) for tag in constraints.get('required_tags', []))
        )

        if category:
            labels = [label for label in labels if label != category.casefold()]

        empty = not plan.selected_menu_ids

        if empty:
            opening = self.choose(
                'empty',
                (
                    'Aku belum menemukan {category} yang sesuai dengan pencarianmu.',
                    'Untuk pencarian ini, aku belum menemukan {category} yang memenuhi pilihanmu.',
                    'Dengan pilihan saat ini, aku belum menemukan {category} yang sesuai.',
                ),
            ).format(category=category.casefold() if category else 'menu')

        details = []

        if labels:
            details.append('Kamu ingin yang ' + ' dan '.join(labels[:3]) + '.')

        if 'budget' in constraints:
            description = (
                BudgetConstraint.from_dict(constraints['budget']).description().replace(',00', '')
            )
            details.append('Aku cari yang ' + description + ' per menu.')
        elif constraints.get('max_price') is not None:
            details.append(
                'Aku cari yang maksimal '
                + self.money(Decimal(constraints['max_price']))
                + ' per menu.'
            )
        elif payload['prefer_affordable']:
            details.append('Aku utamakan pilihan yang hemat.')

        if constraints.get('soft_target') is not None:
            details.append(
                'Aku utamakan harga mendekati '
                + self.money(Decimal(constraints['soft_target']))
                + ' sebagai perkiraan, bukan batas maksimum.'
            )

        excluded = constraints.get('excluded_tags', [])

        if excluded:
            details.append(
                'Aku tetap menghindari '
                + ' dan '.join(self.readable_label(tag) for tag in excluded[:2])
                + '.'
            )

        summary = ' '.join(details)

        if empty:
            question = (
                'Mau cari pilihan lain dengan budget yang sama, atau ubah budgetnya?'
                if 'budget' in constraints or constraints.get('max_price') is not None
                else 'Mau mencoba jenis makanan atau minuman lain?'
            )

            return opening + ('\n' + summary if summary else '') + '\n' + question

        return opening + ('\n' + summary if summary else '')

    def selection(self, name: str, *, switching: bool = False) -> str:
        bank = 'switching' if switching else 'selection'
        variants = (
            (
                'Oke, pilihanmu beralih ke {name}.',
                'Baik, sekarang kita lihat {name}.',
                'Siap, ini pilihan yang baru: {name}.',
            )
            if switching
            else (
                'Ini menu yang kamu maksud: {name}.',
                'Baik, ini pilihan {name}.',
                'Oke, kita lihat {name}.',
            )
        )

        return self.choose(bank, variants).format(name=name)

    @staticmethod
    def option_boundary() -> str:
        return (
            'Tambahan dan varian dipilih melalui “Lihat pilihan menu” pada kartu menu. '
            'Kalau belum memilih menu, pilih menunya terlebih dahulu. '
            'Permintaan tambahan atau varianmu belum diterapkan. '
            'Harga akhir mengikuti pilihan di halaman menu atau keranjang.'
        )

    def accept_generated(self, text: str) -> bool:
        """Recognize a recent generated phrase using only a bounded numeric ID."""
        identifier = int.from_bytes(
            sha256(' '.join(text.casefold().split()).encode('utf-8')).digest()[:8], 'big'
        )
        history = self._history()
        recent = history.get('generated', [])

        if identifier in recent:
            return False

        history.pop('generated', None)
        history['generated'] = (recent + [identifier])[-self.MAX_RECENT :]
        self._session[self.HISTORY_KEY] = dict(list(history.items())[-self.MAX_BANKS :])

        return True
