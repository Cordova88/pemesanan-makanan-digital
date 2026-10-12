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
            if isinstance(field.widget, forms.CheckboxInput):
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
            'name': 'Kode unik tanpa spasi, misalnya spicy atau chicken. Gunakan kode yang dikenali chatbot agar tag dipakai dalam rekomendasi.',
            'display_name': 'Nama yang ditampilkan, misalnya Pedas atau Ayam. Jika kosong, kode tag akan ditampilkan.',
        }


# [OOP: Inheritance] MenuItemForm mewarisi BootstrapModelForm.
# [OOP: Encapsulation] Field, widget (Textarea), label, dan help_texts untuk MenuItem
# dikonfigurasi di dalam Meta, bukan tersebar di view.
class MenuItemForm(BootstrapModelForm):
    class Meta:
        model = MenuItem; fields = ('category', 'name', 'description', 'price', 'image', 'tags', 'is_available', 'is_active', 'stock_estimate')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}
        labels = {'tags': 'Tag menu'}
        help_texts = {'tags': 'Boleh pilih lebih dari satu tag. Tahan Ctrl (Windows) atau Command (Mac) saat memilih. Kelola pilihan di halaman Tag Menu.'}


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