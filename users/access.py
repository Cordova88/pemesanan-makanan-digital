"""Existing staff access decisions, kept separate from HTTP and transactions."""
from django.contrib.auth.models import AbstractUser, AnonymousUser


class StaffAccess:
    def __init__(self, user: AbstractUser | AnonymousUser) -> None:
        self._user: AbstractUser | AnonymousUser = user

    @property
    def can_manage_catalog(self) -> bool:
        return self._user.is_authenticated and self._user.is_staff

    @property
    def is_cashier(self) -> bool:
        return self._user.is_authenticated and self._user.groups.filter(name="Cashier").exists()

    @property
    def can_use_cashier(self) -> bool:
        return self._user.is_authenticated and (self._user.is_staff or self.is_cashier)

    @property
    def home_route(self) -> str:
        if self._user.is_staff:
            return "staff:dashboard"
        return "kasir:dashboard" if self.is_cashier else "storefront"
