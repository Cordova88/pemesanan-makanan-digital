from django.contrib import admin
from .models import (
    AddOn,
    Category,
    MenuItem,
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


admin.site.register([Category, MenuItem, VariantGroup, VariantOption, AddOn])
