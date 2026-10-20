from django.contrib import admin
from .forms import MenuPhotoForm
from .models import (
    AddOn,
    Category,
    MenuItem,
    MenuItemAlias,
    MenuTag,
    MenuTagAlias,
    VariantGroup,
    VariantOption,
)


@admin.register(MenuTag)
class MenuTagAdmin(admin.ModelAdmin):
    list_display = ("name", "display_name")
    search_fields = ("name", "display_name")


@admin.register(MenuTagAlias)
class MenuTagAliasAdmin(admin.ModelAdmin):
    list_display = ("phrase", "tag", "is_active")
    list_filter = ("is_active", "tag")
    search_fields = ("phrase", "tag__name", "tag__display_name")


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    form = MenuPhotoForm
    search_fields = ("name",)


@admin.register(MenuItemAlias)
class MenuItemAliasAdmin(admin.ModelAdmin):
    list_display = ("phrase", "menu_item", "is_active")
    list_filter = ("is_active", "menu_item__category")
    search_fields = ("phrase", "menu_item__name")
    autocomplete_fields = ("menu_item",)


admin.site.register([Category, VariantGroup, VariantOption, AddOn])
