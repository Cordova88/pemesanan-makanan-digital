from collections.abc import Iterable
from django.contrib.auth.models import AbstractUser, AnonymousUser
from django.db.models import Model
from django.forms import ModelForm
from django.http import HttpRequest
from io import BytesIO
from base64 import b64encode
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.utils.http import url_has_allowed_host_and_scheme

from menu.models import AddOn, Category, MenuItem, MenuTag, VariantGroup, VariantOption
from orders.models import AuditLog, Order, Table
from recommendation.services.tag_extractor import TagExtractor
from .access import StaffAccess
from .forms import AddOnForm, CategoryForm, MenuItemForm, MenuTagForm, MenuTagEditForm, TableForm, VariantGroupForm, VariantOptionForm


def _cms_user(user: AbstractUser | AnonymousUser) -> bool: return StaffAccess(user).can_manage_catalog
cms_required = user_passes_test(_cms_user, login_url='staff:login')

def _is_cashier(user: AbstractUser | AnonymousUser) -> bool:
    return StaffAccess(user).is_cashier

def _home_for(user: AbstractUser | AnonymousUser) -> str:
    return StaffAccess(user).home_route

@require_http_methods(['GET', 'POST'])
def staff_login(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect(_home_for(request.user))
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        if not (user.is_staff or _is_cashier(user)):
            form.add_error(None, 'Akun ini tidak memiliki akses staf.')
        else:
            login(request, user)
            nxt = request.GET.get('next', '')
            if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
                return redirect(nxt)
            return redirect(_home_for(user))
    return render(request, 'users/login.html', {'form': form})

@login_required
def staff_logout(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect('staff:login')

@cms_required
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, 'users/dashboard.html', {
        'active_menu_items': MenuItem.objects.filter(is_active=True, is_available=True).count(),
        'categories_count': Category.objects.count(),
        'pending_orders': Order.objects.filter(status=Order.Status.PENDING).count(),
        'today_orders': Order.objects.filter(created_at__date=timezone.localdate()).count(),
        'low_stock': MenuItem.objects.filter(stock_estimate__isnull=False, stock_estimate__lte=5, is_active=True).order_by('stock_estimate', 'name'),
        'recent_orders': Order.objects.select_related('table').order_by('-created_at')[:8],
    })

def _save_form(
    request: HttpRequest,
    form_class: type[ModelForm],
    instance: Model | None,
    template: str,
    title: str,
    success_url: str,
    **context: object,
) -> HttpResponse:
    form = form_class(request.POST or None, request.FILES or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        form.save(); messages.success(request, 'Data berhasil disimpan.')
        return redirect(success_url)
    return render(request, template, {'form': form, 'title': title, **context})

@cms_required
@require_http_methods(['GET', 'POST'])
def tables(request: HttpRequest) -> HttpResponse:
    records = Table.objects.order_by('number')
    if request.method == 'POST': return _save_form(request, TableForm, None, 'users/tables.html', 'Tambah Meja', 'staff:tables', tables=records)
    return render(request, 'users/tables.html', {'form': TableForm(), 'tables': records})

@cms_required
@require_http_methods(['GET', 'POST'])
def table_edit(request: HttpRequest, pk: int) -> HttpResponse: return _save_form(request, TableForm, get_object_or_404(Table, pk=pk), 'users/form.html', 'Edit Meja', 'staff:tables', cancel_url=reverse('staff:tables'))

def _table_url(request: HttpRequest, table: Table) -> str: return request.build_absolute_uri('%s?table=%s' % (reverse('storefront'), table.token))
def _qr_png(data: str) -> bytes:
    try: import qrcode
    except ImportError as exc: raise RuntimeError('Paket qrcode belum terpasang. Jalankan pip install -r requirements.txt.') from exc
    image = qrcode.make(data); output = BytesIO(); image.save(output, format='PNG'); return output.getvalue()

@cms_required
def table_qr(request: HttpRequest, pk: int) -> HttpResponse:
    table = get_object_or_404(Table, pk=pk)
    try: qr_data = _qr_png(_table_url(request, table))
    except RuntimeError as exc: messages.error(request, str(exc)); return redirect('staff:tables')
    return render(request, 'users/table_qr.html', {
        'table': table, 'table_url': _table_url(request, table), 'qr_data': b64encode(qr_data).decode(),
        'local_qr_host': request.get_host().split(':')[0] in {'127.0.0.1', 'localhost'},
    })

@cms_required
def table_qr_download(request: HttpRequest, pk: int) -> HttpResponse:
    table = get_object_or_404(Table, pk=pk)
    try: response = HttpResponse(_qr_png(_table_url(request, table)), content_type='image/png')
    except RuntimeError as exc: return HttpResponse(str(exc), status=503, content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename="rasakita-table-%s.png"' % table.pk
    return response

@cms_required
@require_http_methods(['GET', 'POST'])
def categories(request: HttpRequest) -> HttpResponse:
    records = Category.objects.order_by('name')
    if request.method == 'POST': return _save_form(request, CategoryForm, None, 'users/categories.html', 'Tambah Kategori', 'staff:categories', categories=records)
    return render(request, 'users/categories.html', {'form': CategoryForm(), 'categories': records})
@cms_required
@require_http_methods(['GET', 'POST'])
def category_edit(request: HttpRequest, pk: int) -> HttpResponse: return _save_form(request, CategoryForm, get_object_or_404(Category, pk=pk), 'users/form.html', 'Edit Kategori', 'staff:categories', cancel_url=reverse('staff:categories'))

def _mark_recognized(records: Iterable[MenuTag]) -> list[MenuTag]:
    known = set(TagExtractor.ALIASES)
    rows = list(records)
    for tag in rows:
        tag.recognized = tag.name in known
    return rows

@cms_required
@require_http_methods(['GET', 'POST'])
def tags(request: HttpRequest) -> HttpResponse:
    query = request.GET.get('q', '').strip()
    records = MenuTag.objects.annotate(menu_count=Count('menu_items')).order_by('name')
    total = records.count()
    if query:
        records = records.filter(Q(name__icontains=query) | Q(display_name__icontains=query))
    context = {'tags': _mark_recognized(records), 'query': query, 'tag_total': total}
    if request.method == 'POST':
        return _save_form(request, MenuTagForm, None, 'users/tags.html', 'Tambah Tag Menu', 'staff:tags', **context)
    return render(request, 'users/tags.html', {'form': MenuTagForm(), **context})

@cms_required
@require_http_methods(['GET', 'POST'])
def tag_edit(request: HttpRequest, pk: int) -> HttpResponse:
    with transaction.atomic():
        tag = get_object_or_404(MenuTag.objects.select_for_update(), pk=pk)
        form = MenuTagEditForm(request.POST if request.method == 'POST' else None, instance=tag)
        if request.method == 'POST' and form.is_valid():
            form.save()
            tag.menu_items.set(form.cleaned_data['menus'])
            messages.success(request, 'Tag dan pemakaiannya pada menu berhasil disimpan.')
            return redirect('staff:tags')
    return render(request, 'users/form.html', {
        'form': form, 'title': 'Edit Tag Menu', 'cancel_url': reverse('staff:tags'),
        'tag_usage_count': tag.menu_items.count(), 'show_tag_usage': True,
    })

@cms_required
@require_http_methods(['GET', 'POST'])
def tag_delete(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method == 'POST':
        with transaction.atomic():
            tag = get_object_or_404(MenuTag.objects.select_for_update(), pk=pk)
            if tag.menu_items.exists() and request.POST.get('confirm_detach') != 'yes':
                messages.error(request, 'Konfirmasikan pelepasan tag dari semua menu sebelum menghapusnya.')
            else:
                tag.menu_items.clear()
                tag.delete()
                messages.success(request, 'Tag berhasil dihapus. Semua menu tetap tersimpan.')
        return redirect('staff:tags')
    tag = get_object_or_404(MenuTag, pk=pk)
    return render(request, 'users/tag_confirm_delete.html', {
        'tag': tag,
        'items': tag.menu_items.order_by('name'),
        'alias_count': tag.aliases.count(),
    })

@cms_required
@require_http_methods(['GET', 'POST'])
def menu_items(request: HttpRequest) -> HttpResponse:
    query = request.GET.get('q', '').strip(); records = MenuItem.objects.select_related('category').prefetch_related('tags').order_by('category__name', 'name')
    if query: records = records.filter(Q(name__icontains=query) | Q(category__name__icontains=query))
    if request.method == 'POST': return _save_form(request, MenuItemForm, None, 'users/menu_items.html', 'Tambah Menu', 'staff:menu-items', items=records, query=query)
    return render(request, 'users/menu_items.html', {'form': MenuItemForm(), 'items': records, 'query': query})
@cms_required
@require_http_methods(['GET', 'POST'])
def menu_item_edit(request: HttpRequest, pk: int) -> HttpResponse: return _save_form(request, MenuItemForm, get_object_or_404(MenuItem, pk=pk), 'users/menu_item_form.html', 'Edit Menu', 'staff:menu-items')

@cms_required
@require_http_methods(['GET', 'POST'])
def variants(request: HttpRequest) -> HttpResponse:
    groups = VariantGroup.objects.select_related('menu_item').prefetch_related('options').all()
    posted = request.method == 'POST'
    is_option = request.POST.get('kind') == 'option'
    # Bind only the submitted form; distinct IDs avoid duplicate label targets.
    group_form = VariantGroupForm(request.POST if posted and not is_option else None, auto_id='group_%s')
    option_form = VariantOptionForm(request.POST if posted and is_option else None, auto_id='option_%s')
    submitted_form = option_form if is_option else group_form
    if posted and submitted_form.is_valid():
        submitted_form.save()
        messages.success(request, 'Data berhasil disimpan.')
        return redirect('staff:variants')
    return render(request, 'users/variants.html', {'groups': groups, 'group_form': group_form, 'option_form': option_form})
@cms_required
@require_http_methods(['GET', 'POST'])
def variant_group_edit(request: HttpRequest, pk: int) -> HttpResponse: return _save_form(request, VariantGroupForm, get_object_or_404(VariantGroup, pk=pk), 'users/form.html', 'Edit Grup Varian', 'staff:variants', cancel_url=reverse('staff:variants'))
@cms_required
@require_http_methods(['GET', 'POST'])
def variant_option_edit(request: HttpRequest, pk: int) -> HttpResponse: return _save_form(request, VariantOptionForm, get_object_or_404(VariantOption, pk=pk), 'users/form.html', 'Edit Opsi Varian', 'staff:variants', cancel_url=reverse('staff:variants'))

@cms_required
@require_http_methods(['GET', 'POST'])
def addons(request: HttpRequest) -> HttpResponse:
    records = AddOn.objects.prefetch_related('menu_items').order_by('name')
    if request.method == 'POST': return _save_form(request, AddOnForm, None, 'users/addons.html', 'Tambah Add-on', 'staff:addons', addons=records)
    return render(request, 'users/addons.html', {'form': AddOnForm(), 'addons': records})
@cms_required
@require_http_methods(['GET', 'POST'])
def addon_edit(request: HttpRequest, pk: int) -> HttpResponse: return _save_form(request, AddOnForm, get_object_or_404(AddOn, pk=pk), 'users/form.html', 'Edit Tambahan', 'staff:addons', cancel_url=reverse('staff:addons'))

@cms_required
def orders(request: HttpRequest) -> HttpResponse:
    qs = Order.objects.select_related('table').order_by('-created_at', '-pk')

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    order_type = request.GET.get('type', '')
    period = request.GET.get('period', '')

    status_choices = list(Order._meta.get_field('status').choices)
    type_choices = list(Order._meta.get_field('order_type').choices)

    if q:
        qs = qs.filter(Q(public_id__icontains=q) | Q(customer_name__icontains=q) | Q(table__number__icontains=q))
    if status in {value for value, _ in status_choices}:
        qs = qs.filter(status=status)
    else:
        status = ''
    if order_type in {value for value, _ in type_choices}:
        qs = qs.filter(order_type=order_type)
    else:
        order_type = ''
    if period == 'today':
        qs = qs.filter(created_at__date=timezone.localdate())
    elif period == '7':
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=7))
    else:
        period = ''

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = {key: value for key, value in {'q': q, 'status': status, 'type': order_type, 'period': period}.items() if value}

    return render(request, 'users/orders.html', {
        'orders': page_obj,
        'page_obj': page_obj,
        'total': paginator.count,
        'q': q,
        'status': status,
        'order_type': order_type,
        'period': period,
        'status_choices': status_choices,
        'type_choices': type_choices,
        'querystring': urlencode(params),
        'filtered': bool(q or status or order_type or period),
    })

@cms_required
def audit_log(request: HttpRequest) -> HttpResponse:
    records = AuditLog.objects.select_related('order', 'actor').order_by('-created_at', '-pk')
    q = request.GET.get('q', '').strip()
    action = request.GET.get('action', '')
    period = request.GET.get('period', '')
    action_choices = list(AuditLog.Action.choices)
    if q:
        records = records.filter(Q(order__public_id__icontains=q) | Q(order__customer_name__icontains=q) | Q(actor__username__icontains=q))
    if action in {value for value, _ in action_choices}:
        records = records.filter(action=action)
    else:
        action = ''
    if period == 'today':
        records = records.filter(created_at__date=timezone.localdate())
    elif period == '7':
        records = records.filter(created_at__gte=timezone.now() - timedelta(days=7))
    else:
        period = ''
    paginator = Paginator(records, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = {key: value for key, value in {'q': q, 'action': action, 'period': period}.items() if value}
    return render(request, 'users/audit_log.html', {
        'logs': page_obj, 'page_obj': page_obj, 'total': paginator.count,
        'q': q, 'action': action, 'period': period, 'action_choices': action_choices,
        'querystring': urlencode(params), 'filtered': bool(params),
    })
