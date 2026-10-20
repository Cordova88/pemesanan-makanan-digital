from django.contrib.auth.models import AbstractUser, AnonymousUser
from django.core.exceptions import PermissionDenied
from users.access import StaffAccess


def cashier_required(user: AbstractUser | AnonymousUser) -> None:
    if not StaffAccess(user).can_use_cashier:
        raise PermissionDenied("Cashier access required.")
