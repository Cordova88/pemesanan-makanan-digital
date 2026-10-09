from io import BytesIO
from base64 import b64encode

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
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
from .forms import AddOnForm, CategoryForm, MenuItemForm, MenuTagForm, TableForm, VariantGroupForm, VariantOptionForm


def _cms_user(user): return user.is_authenticated and user.is_staff
cms_required = user_passes_test(_cms_user, login_url='staff:login')

def _is_cashier(user):
    return user.is_authenticated and user.groups.filter(name='Cashier').exists()

def _home_for(user):
    if user.is_staff:
        return 'staff:dashboard'
    return 'kasir:dashboard' if _is_cashier(user) else 'storefront'

@require_http_methods(['GET', 'POST'])
def staff_login(request):
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
def staff_logout(request):
    logout(request)
    return redirect('staff:login')

@cms_required
def dashboard(request):
    return render(request, 'users/dashboard.html', {
        'active_menu_items': MenuItem.objects.filter(is_active=True, is_available=True).count(),
        'categories_count': Category.objects.count(),
        'pending_orders': Order.objects.filter(status=Order.Status.PENDING).count(),
        'today_orders': Order.objects.filter(created_at__date=timezone.localdate()).count(),
        'low_stock': MenuItem.objects.filter(stock_estimate__isnull=False, stock_estimate__lte=5, is_active=True).order_by('stock_estimate', 'name'),
        'recent_orders': Order.objects.select_related('table').order_by('-created_at')[:8],
    })

def _save_form(request, form_class, instance, template, title, success_url, **context):
    form = form_class(request.POST or None, request.FILES or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        form.save(); messages.success(request, 'Data berhasil disimpan.')
        return redirect(success_url)
    return render(request, template, {'form': form, 'title': title, **context})

@cms_required
@require_http_methods(['GET', 'POST'])
def tables(request):
    records = Table.objects.order_by('number')
    if request.method == 'POST': return _save_form(request, TableForm, None, 'users/tables.html', 'Tambah Meja', 'staff:tables', tables=records)
    return render(request, 'users/tables.html', {'form': TableForm(), 'tables': records})

@cms_required
@require_http_methods(['GET', 'POST'])
def table_edit(request, pk): return _save_form(request, TableForm, get_object_or_404(Table, pk=pk), 'users/form.html', 'Edit Meja', 'staff:tables')

def _table_url(request, table): return request.build_absolute_uri('%s?table=%s' % (reverse('storefront'), table.token))
def _qr_png(data):
    try: import qrcode
    except ImportError as exc: raise RuntimeError('Paket qrcode belum terpasang. Jalankan pip install -r requirements.txt.') from exc
    image = qrcode.make(data); output = BytesIO(); image.save(output, format='PNG'); return output.getvalue()

@cms_required
def table_qr(request, pk):
    table = get_object_or_404(Table, pk=pk)
    try: qr_data = _qr_png(_table_url(request, table))
    except RuntimeError as exc: messages.error(request, str(exc)); return redirect('staff:tables')
    return render(request, 'users/table_qr.html', {'table': table, 'table_url': _table_url(request, table), 'qr_data': b64encode(qr_data).decode()})

@cms_required
def table_qr_download(request, pk):
    table = get_object_or_404(Table, pk=pk)
    try: response = HttpResponse(_qr_png(_table_url(request, table)), content_type='image/png')
    except RuntimeError as exc: return HttpResponse(str(exc), status=503, content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename="rasakita-table-%s.png"' % table.number
    return response

@cms_required
@require_http_methods(['GET', 'POST'])
def categories(request):
    records = Category.objects.order_by('name')
    if request.method == 'POST': return _save_form(request, CategoryForm, None, 'users/categories.html', 'Tambah Kategori', 'staff:categories', categories=records)
    return render(request, 'users/categories.html', {'form': CategoryForm(), 'categories': records})
@cms_required
@require_http_methods(['GET', 'POST'])
def category_edit(request, pk): return _save_form(request, CategoryForm, get_object_or_404(Category, pk=pk), 'users/form.html', 'Edit Kategori', 'staff:categories')

@cms_required
@require_http_methods(['GET', 'POST'])
def tags(request):
    records = MenuTag.objects.annotate(menu_count=Count('menu_items')).order_by('name')
    if request.method == 'POST':
        return _save_form(request, MenuTagForm, None, 'users/tags.html', 'Tambah Tag Menu', 'staff:tags', tags=records)
    return render(request, 'users/tags.html', {'form': MenuTagForm(), 'tags': records})

@cms_required
@require_http_methods(['GET', 'POST'])
def tag_edit(request, pk):
    return _save_form(request, MenuTagForm, get_object_or_404(MenuTag, pk=pk), 'users/form.html', 'Edit Tag Menu', 'staff:tags')

@cms_required
@require_http_methods(['GET', 'POST'])
def tag_delete(request, pk):
    if request.method == 'POST':
        with transaction.atomic():
            tag = get_object_or_404(MenuTag.objects.select_for_update(), pk=pk)
            if tag.menu_items.exists():
                messages.error(request, 'Tag masih dipakai menu. Lepaskan tag dari semua menu sebelum menghapusnya.')
            else:
                tag.delete()
                messages.success(request, 'Tag berhasil dihapus.')
        return redirect('staff:tags')
    tag = get_object_or_404(MenuTag, pk=pk)
    return render(request, 'users/tag_confirm_delete.html', {
        'tag': tag,
        'items': tag.menu_items.order_by('name'),
    })

@cms_required
@require_http_methods(['GET', 'POST'])
def menu_items(request):
    query = request.GET.get('q', '').strip(); records = MenuItem.objects.select_related('category').prefetch_related('tags').order_by('category__name', 'name')
    if query: records = records.filter(Q(name__icontains=query) | Q(category__name__icontains=query))
    if request.method == 'POST': return _save_form(request, MenuItemForm, None, 'users/menu_items.html', 'Tambah Menu', 'staff:menu-items', items=records, query=query)
    return render(request, 'users/menu_items.html', {'form': MenuItemForm(), 'items': records, 'query': query})
@cms_required
@require_http_methods(['GET', 'POST'])
def menu_item_edit(request, pk): return _save_form(request, MenuItemForm, get_object_or_404(MenuItem, pk=pk), 'users/form.html', 'Edit Menu', 'staff:menu-items')

@cms_required
@require_http_methods(['GET', 'POST'])
def variants(request):
    groups = VariantGroup.objects.select_related('menu_item').prefetch_related('options').all(); options = VariantOption.objects.select_related('group', 'group__menu_item').all()
    form_class = VariantOptionForm if request.POST.get('kind') == 'option' else VariantGroupForm
    if request.method == 'POST': return _save_form(request, form_class, None, 'users/variants.html', 'Varians', 'staff:variants', groups=groups, options=options, group_form=VariantGroupForm(), option_form=VariantOptionForm())
    return render(request, 'users/variants.html', {'groups': groups, 'options': options, 'group_form': VariantGroupForm(), 'option_form': VariantOptionForm()})
@cms_required
@require_http_methods(['GET', 'POST'])
def variant_group_edit(request, pk): return _save_form(request, VariantGroupForm, get_object_or_404(VariantGroup, pk=pk), 'users/form.html', 'Edit Grup Varian', 'staff:variants')
@cms_required
@require_http_methods(['GET', 'POST'])
def variant_option_edit(request, pk): return _save_form(request, VariantOptionForm, get_object_or_404(VariantOption, pk=pk), 'users/form.html', 'Edit Opsi Varian', 'staff:variants')

@cms_required
@require_http_methods(['GET', 'POST'])
def addons(request):
    records = AddOn.objects.prefetch_related('menu_items').order_by('name')
    if request.method == 'POST': return _save_form(request, AddOnForm, None, 'users/addons.html', 'Tambah Add-on', 'staff:addons', addons=records)
    return render(request, 'users/addons.html', {'form': AddOnForm(), 'addons': records})
@cms_required
@require_http_methods(['GET', 'POST'])
def addon_edit(request, pk): return _save_form(request, AddOnForm, get_object_or_404(AddOn, pk=pk), 'users/form.html', 'Edit Add-on', 'staff:addons')
@cms_required
def orders(request): return render(request, 'users/orders.html', {'orders': Order.objects.select_related('table').order_by('-created_at')[:100]})
@cms_required
def audit_log(request): return render(request, 'users/audit_log.html', {'logs': AuditLog.objects.select_related('order', 'actor').order_by('-created_at')[:150]})
