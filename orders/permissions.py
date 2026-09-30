from django.core.exceptions import PermissionDenied
def cashier_required(user):
    if not user.is_authenticated or not (user.is_staff or user.groups.filter(name="Cashier").exists()): raise PermissionDenied("Cashier access required.")
