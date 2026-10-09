from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from orders.models import Order, Table
from orders.permissions import cashier_required as check_cashier
from orders.services import expire_order_if_due

STATUS_TABS = [
    ("PENDING", "Menunggu"), ("PAID", "Dibayar"), ("CANCELLED", "Dibatalkan"),
    ("EXPIRED", "Kedaluwarsa"), ("REFUNDED", "Refund"), ("ALL", "Semua"),
]


def cashier_page_required(view):
    """Harus login (lewat /staff/login/) dan lolos aturan peran yang sama dengan API orders."""
    @login_required(login_url="staff:login")
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        check_cashier(request.user)  # melempar PermissionDenied -> halaman 403
        return view(request, *args, **kwargs)
    return wrapper


@cashier_page_required
def dashboard(request):
    q = request.GET.get("q", "").strip().upper()
    status = request.GET.get("status", "PENDING")
    if status not in dict(STATUS_TABS):
        status = "PENDING"

    if q:
        order = Order.objects.filter(public_id=q).first()
        if order:
            return redirect("kasir:order", public_id=order.public_id)

    orders = Order.objects.select_related("table").order_by("-created_at")
    if status != "ALL":
        orders = orders.filter(status=status)

    paid_today = Order.objects.filter(status=Order.Status.PAID, paid_at__date=timezone.localdate())
    return render(request, "users/kasir/dashboard.html", {
        "orders": orders[:50],
        "q": q,
        "status": status,
        "status_tabs": STATUS_TABS,
        "not_found": bool(q),
        "now": timezone.now(),
        "pending_count": Order.objects.filter(status=Order.Status.PENDING).count(),
        "paid_today_count": paid_today.count(),
        "paid_today_total": paid_today.aggregate(v=Sum("total"))["v"] or 0,
    })


@cashier_page_required
def order_detail(request, public_id):
    public_id = public_id.upper()
    try:
        order = expire_order_if_due(public_id)  # status kedaluwarsa dimaterialisasi dulu
    except Order.DoesNotExist:
        return redirect(f"{reverse('kasir:dashboard')}?q={public_id}")

    order = (Order.objects.select_related("table", "payment")
            .prefetch_related("items__variants", "items__addons")
            .get(pk=order.pk))
    tables = Table.objects.filter(is_active=True).order_by("number") if order.status == "PENDING" else []
    return render(request, "users/kasir/order.html", {"order": order, "tables": tables})