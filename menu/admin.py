from django.contrib import admin
from .models import AddOn, Category, MenuItem, MenuTag, VariantGroup, VariantOption
admin.site.register([Category,MenuItem,MenuTag,VariantGroup,VariantOption,AddOn])
