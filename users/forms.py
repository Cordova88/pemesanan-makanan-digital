from django import forms

from menu.models import AddOn, Category, MenuItem, VariantGroup, VariantOption
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
class MenuItemForm(BootstrapModelForm):
    class Meta:
        model = MenuItem; fields = ('category', 'name', 'description', 'price', 'image', 'is_available', 'is_active', 'stock_estimate')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}
class VariantGroupForm(BootstrapModelForm):
    class Meta: model = VariantGroup; fields = ('menu_item', 'name', 'is_required', 'is_active', 'display_order')
class VariantOptionForm(BootstrapModelForm):
    class Meta: model = VariantOption; fields = ('group', 'name', 'price_adjustment', 'is_active', 'display_order')
class AddOnForm(BootstrapModelForm):
    class Meta: model = AddOn; fields = ('name', 'price', 'menu_items', 'is_available', 'is_active')
class TableForm(BootstrapModelForm):
    class Meta: model = Table; fields = ('number', 'is_active')
