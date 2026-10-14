from django import forms
from menu.models import AddOn, Category, MenuItem, MenuTag, VariantGroup, VariantOption
from orders.models import Table


# [OOP: Inheritance] BootstrapModelForm mewarisi forms.ModelForm, sehingga otomatis
# punya pembuatan field dari model, validasi, dan method save() tanpa ditulis ulang.
# [OOP: Polymorphism] __init__ di-override (method overriding) lalu memanggil
# super().__init__() agar perilaku asli ModelForm tetap jalan, ditambah styling Bootstrap.
# [OOP: Encapsulation] Logika pemberian class CSS dibungkus di satu class dasar,
# sehingga semua form turunan konsisten tanpa mengulang kode.
# [OOP: Abstraction] Form turunan cukup mendefinisikan Meta; cara tiap field
# di-style disembunyikan di class dasar ini.
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


# [OOP: Inheritance] Multilevel inheritance: CategoryForm -> BootstrapModelForm -> ModelForm.
# [OOP: Encapsulation] Nested class Meta mengikat form ke model Category dan
# membatasi field yang boleh diisi (name, is_active).
class CategoryForm(BootstrapModelForm):
    class Meta: model = Category; fields = ('name', 'is_active')


# [OOP: Inheritance] MenuTagForm mewarisi BootstrapModelForm (styling otomatis).
# [OOP: Encapsulation] Label dan help_texts dibungkus di Meta, terpisah dari logika form.
class MenuTagForm(BootstrapModelForm):
    class Meta:
        model = MenuTag
        fields = ('name', 'display_name')
        labels = {'name': 'Kode tag', 'display_name': 'Nama tampilan'}
        help_texts = {
            'name': 'Kode unik tanpa spasi, misalnya spicy atau chicken. Tag baru dapat dikenali dari kode atau nama tampilannya setelah dipasang pada menu aktif dalam kategori aktif.',
            'display_name': 'Nama yang ditampilkan, misalnya Pedas atau Ayam. Jika kosong, kode tag akan ditampilkan.',
        }

# [OOP: Inheritance] MenuTagEditForm mewarisi MenuTagForm, yang mewarisi BootstrapModelForm,
# lalu ModelForm (multilevel inheritance). Field name/display_name dan styling Bootstrap
# didapat otomatis tanpa ditulis ulang.
# [OOP: Encapsulation] Field tambahan `menus` (pilihan menu yang tetap memakai tag) dibungkus
# di dalam form ini sebagai atribut class, terpisah dari form pembuatan tag biasa.
class MenuTagEditForm(MenuTagForm):
    menus = forms.ModelMultipleChoiceField(
        queryset=MenuItem.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Menu yang tetap memakai tag',
        help_text='Hilangkan centang untuk melepas tag dari menu tersebut. Menu tidak dihapus.',
    )

    # [OOP: Polymorphism] __init__ di-override (method overriding), lalu memanggil
    # super().__init__() agar perilaku form induk tetap jalan.
    # [OOP: Encapsulation] Daftar menu dan nilai awal centang dihitung dari self.instance di
    # dalam form, jadi pemanggil (view) tidak perlu menyiapkannya.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['menus'].queryset = self.instance.menu_items.order_by('name', 'pk')
        self.initial['menus'] = list(self.instance.menu_items.values_list('pk', flat=True))


# [OOP: Inheritance] MenuItemForm mewarisi BootstrapModelForm (styling Bootstrap otomatis).
# [OOP: Encapsulation] Field, widget (Textarea, CheckboxSelectMultiple, ClearableFileInput),
# label, dan help_texts untuk MenuItem dikonfigurasi di dalam Meta, bukan tersebar di view.
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

    # [OOP: Polymorphism] __init__ di-override (method overriding), lalu memanggil super().__init__()
    # agar inisialisasi BootstrapModelForm (styling) tetap berjalan.
    # [OOP: Encapsulation] Urutan pilihan tag (display_name, name, pk) diatur di dalam form,
    # bukan oleh pemanggil.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tags'].queryset = MenuTag.objects.order_by('display_name', 'name', 'pk')

# [OOP: Inheritance] VariantGroupForm mewarisi BootstrapModelForm.
# [OOP: Encapsulation] Meta mengikat form ke model VariantGroup.
class VariantGroupForm(BootstrapModelForm):
    class Meta: model = VariantGroup; fields = ('menu_item', 'name', 'is_required', 'is_active', 'display_order')


# [OOP: Inheritance] VariantOptionForm mewarisi BootstrapModelForm.
# [OOP: Encapsulation] Meta mengikat form ke model VariantOption.
class VariantOptionForm(BootstrapModelForm):
    class Meta: model = VariantOption; fields = ('group', 'name', 'price_adjustment', 'is_active', 'display_order')


# [OOP: Inheritance] AddOnForm mewarisi BootstrapModelForm.
# [OOP: Encapsulation] Meta mengikat form ke model AddOn, termasuk relasi many-to-many menu_items.
class AddOnForm(BootstrapModelForm):
    class Meta: model = AddOn; fields = ('name', 'price', 'menu_items', 'is_available', 'is_active')


# [OOP: Inheritance] TableForm mewarisi BootstrapModelForm.
# [OOP: Encapsulation] Meta mengikat form ke model Table (hanya number dan is_active
# yang bisa diubah; token QR tidak ikut karena editable=False di model).
class TableForm(BootstrapModelForm):
    class Meta: model = Table; fields = ('number', 'is_active')