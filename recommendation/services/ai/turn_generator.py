"""One provider attempt per reply, shared by every optional AI consumer."""

from collections.abc import Callable
import re

from ..text_generator import TextGenerator


class TurnGenerator(TextGenerator):
    def __init__(self, provider: TextGenerator) -> None:
        self.provider = provider
        self.reset()

    def reset(self) -> None:
        self._reserved = False
        self._attempted = False
        self._private = False

    def protect(self, message: str, *, sensitive_context: bool = False) -> None:
        # Conservative bypass: never try to ask a provider to redact private data.
        self._private |= sensitive_context or bool(
            re.search(
                r'@|https?://|\b\d{7,}\b|\b(?:alamat|telepon|telpon|whatsapp|email|'
                r'password|passwd|token|secret|api[_ -]?key|nik|rekening|depresi|'
                r'diagnosa|diagnosis|diabetes|hamil|alergi|allergy)\b',
                message,
                re.I,
            )
        )

    @property
    def reservation_block_reason(self) -> str | None:
        """Coarse gate metadata only; no message, usage count or provider details."""

        if self._private:
            return 'private_turn'

        if self._reserved or self._attempted:
            return 'turn_slot_used'

        if getattr(self.provider, 'available', True) is False:
            return 'provider_unavailable'

        return None

    def reserve(self, consume: Callable[[], bool]) -> bool:
        if self.reservation_block_reason is not None:
            return False

        if not consume():
            return False

        self._reserved = True

        return True

    def generate(self, prompt: str) -> str | None:
        if self._private or not self._reserved or self._attempted:
            return None

        # Claim before dispatch; exceptions and invalid results cannot refund it.
        self._attempted = True

        try:
            return self.provider.generate(prompt)
        except Exception:
            return None
