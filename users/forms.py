from django import forms
from menu.forms import MenuPhotoForm

from menu.models import AddOn, Category, MenuItem, MenuTag, VariantGroup, VariantOption
from orders.models import Table


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, forms.SelectMultiple):
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs['class'] = 'form-control'


class CategoryForm(BootstrapModelForm):
    class Meta:
        model = Category
        fields = ('name', 'is_active')
        labels = {'name': 'Nama kategori', 'is_active': 'Aktif'}
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

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields['menus'].queryset = self.instance.menu_items.order_by('name', 'pk')
        self.initial['menus'] = list(self.instance.menu_items.values_list('pk', flat=True))


class MenuItemForm(BootstrapModelForm, MenuPhotoForm):
    class Meta:
        model = MenuItem; fields = ('category', 'name', 'description', 'price', 'image', 'detail_image', 'tags', 'is_available', 'is_active', 'stock_estimate')
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

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields['tags'].queryset = MenuTag.objects.order_by('display_name', 'name', 'pk')
        self.fields['category'].empty_label = 'Pilih kategori'
class VariantGroupForm(BootstrapModelForm):
    class Meta:
        model = VariantGroup
        fields = ('menu_item', 'name', 'is_required', 'is_active', 'display_order')
        labels = {'menu_item': 'Menu', 'name': 'Nama grup', 'is_required': 'Wajib dipilih',
                  'is_active': 'Aktif', 'display_order': 'Urutan tampilan'}
        help_texts = {'is_required': 'Pelanggan harus memilih satu opsi dari grup aktif ini.',
                      'display_order': 'Angka lebih kecil ditampilkan lebih dahulu.'}
        error_messages = {'__all__': {'unique_together': 'Grup dengan nama ini sudah ada pada menu yang dipilih.'}}

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields['menu_item'].empty_label = 'Pilih menu'
class VariantOptionForm(BootstrapModelForm):
    class Meta:
        model = VariantOption
        fields = ('group', 'name', 'price_adjustment', 'is_active', 'display_order')
        labels = {'group': 'Grup varian', 'name': 'Nama opsi', 'price_adjustment': 'Tambahan harga (Rp)',
                  'is_active': 'Aktif', 'display_order': 'Urutan tampilan'}
        help_texts = {'price_adjustment': 'Ditambahkan ke harga menu. Isi 0 untuk tanpa tambahan harga.',
                      'display_order': 'Angka lebih kecil ditampilkan lebih dahulu.'}
        error_messages = {'__all__': {'unique_together': 'Opsi dengan nama ini sudah ada pada grup yang dipilih.'}}

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields['group'].empty_label = 'Pilih grup varian'
class AddOnForm(BootstrapModelForm):
    class Meta:
        model = AddOn
        fields = ('name', 'price', 'menu_items', 'is_available', 'is_active')
        widgets = {'menu_items': forms.CheckboxSelectMultiple}
        labels = {'name': 'Nama tambahan', 'price': 'Harga (Rp)', 'menu_items': 'Menu terkait',
                  'is_available': 'Tersedia untuk dipesan', 'is_active': 'Aktif'}
        help_texts = {'menu_items': 'Pilih menu yang boleh memakai tambahan ini. Tanpa pilihan, tambahan tidak tersedia pada menu pelanggan.'}
        error_messages = {'name': {'unique': 'Nama tambahan ini sudah digunakan.'}}

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields['menu_items'].queryset = MenuItem.objects.order_by('name', 'pk')
class TableForm(BootstrapModelForm):
    class Meta:
        model = Table
        fields = ('number', 'is_active')
        labels = {'number': 'Nomor / nama meja', 'is_active': 'Aktif'}
        help_texts = {'is_active': 'Meja nonaktif tidak dapat dipakai untuk pemesanan melalui QR. Mengubah nama atau status tidak mengganti QR.'}
        error_messages = {'number': {'unique': 'Nomor / nama meja ini sudah digunakan.'}}
