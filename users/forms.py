from django import forms

from menu.models import AddOn, Category, MenuItem, MenuTag, VariantGroup, VariantOption
from orders.models import Table


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
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
            'name': 'Kode unik tanpa spasi, misalnya spicy atau chicken. Tag baru dapat dikenali dari kode atau nama tampilannya setelah dipasang pada menu aktif dalam kategori aktif.',
            'display_name': 'Nama yang ditampilkan, misalnya Pedas atau Ayam. Jika kosong, kode tag akan ditampilkan.',
        }
class MenuTagEditForm(MenuTagForm):
    menus = forms.ModelMultipleChoiceField(
        queryset=MenuItem.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Menu yang tetap memakai tag',
        help_text='Hilangkan centang untuk melepas tag dari menu tersebut. Menu tidak dihapus.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['menus'].queryset = self.instance.menu_items.order_by('name', 'pk')
        self.initial['menus'] = list(self.instance.menu_items.values_list('pk', flat=True))


class MenuItemForm(BootstrapModelForm):
    class Meta:
        model = MenuItem; fields = ('category', 'name', 'description', 'price', 'image', 'tags', 'is_available', 'is_active', 'stock_estimate')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'tags': forms.CheckboxSelectMultiple,
            'image': forms.ClearableFileInput(attrs={'data-menu-image-input': ''}),
        }
        labels = {
            'category': 'Kategori', 'name': 'Nama menu', 'description': 'Deskripsi',
            'price': 'Harga (Rp)', 'image': 'Gambar menu', 'tags': 'Tag menu',
            'is_available': 'Tersedia untuk dipesan', 'is_active': 'Tampilkan di katalog',
            'stock_estimate': 'Perkiraan stok',
        }
        help_texts = {'tags': 'Centang semua tag yang sesuai. Kelola pilihan tag di halaman Tag Menu.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tags'].queryset = MenuTag.objects.order_by('display_name', 'name', 'pk')
class VariantGroupForm(BootstrapModelForm):
    class Meta: model = VariantGroup; fields = ('menu_item', 'name', 'is_required', 'is_active', 'display_order')
class VariantOptionForm(BootstrapModelForm):
    class Meta: model = VariantOption; fields = ('group', 'name', 'price_adjustment', 'is_active', 'display_order')
class AddOnForm(BootstrapModelForm):
    class Meta: model = AddOn; fields = ('name', 'price', 'menu_items', 'is_available', 'is_active')
class TableForm(BootstrapModelForm):
    class Meta: model = Table; fields = ('number', 'is_active')
