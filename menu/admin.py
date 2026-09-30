from django.contrib import admin
from .models import AddOn, Category, MenuItem, VariantGroup, VariantOption
admin.site.register([Category,MenuItem,VariantGroup,VariantOption,AddOn])
