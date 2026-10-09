from django import forms

from menu.models import AddOn, Category, MenuItem, MenuTag, VariantGroup, VariantOption
from orders.models import Table


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, forms.SelectMultiple):
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs['class'] = 'form-control'


class CategoryForm(BootstrapModelForm):
    class Meta: model = Category; fields = ('name', 'is_active')
class MenuTagForm(BootstrapModelForm):
    class Meta:
        model = MenuTag
        fields = ('name', 'display_name')
        labels = {'name': 'Kode tag', 'display_name': 'Nama tampilan'}
        help_texts = {
            'name': 'Kode unik tanpa spasi, misalnya spicy atau chicken. Gunakan kode yang dikenali chatbot agar tag dipakai dalam rekomendasi.',
            'display_name': 'Nama yang ditampilkan, misalnya Pedas atau Ayam. Jika kosong, kode tag akan ditampilkan.',
        }
class MenuItemForm(BootstrapModelForm):
    class Meta:
        model = MenuItem; fields = ('category', 'name', 'description', 'price', 'image', 'tags', 'is_available', 'is_active', 'stock_estimate')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}
        labels = {'tags': 'Tag menu'}
        help_texts = {'tags': 'Boleh pilih lebih dari satu tag. Tahan Ctrl (Windows) atau Command (Mac) saat memilih. Kelola pilihan di halaman Tag Menu.'}
class VariantGroupForm(BootstrapModelForm):
    class Meta: model = VariantGroup; fields = ('menu_item', 'name', 'is_required', 'is_active', 'display_order')
class VariantOptionForm(BootstrapModelForm):
    class Meta: model = VariantOption; fields = ('group', 'name', 'price_adjustment', 'is_active', 'display_order')
class AddOnForm(BootstrapModelForm):
    class Meta: model = AddOn; fields = ('name', 'price', 'menu_items', 'is_available', 'is_active')
class TableForm(BootstrapModelForm):
    class Meta: model = Table; fields = ('number', 'is_active')
