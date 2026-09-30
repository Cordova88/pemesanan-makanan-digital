from django.contrib import admin
from .models import AuditLog, Order, OrderItem, OrderItemAddOn, OrderItemVariant, Payment
class ItemInline(admin.TabularInline): model=OrderItem; extra=0; readonly_fields=("item_name","base_price","unit_price","line_total")
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display=("public_id","customer_name","status","total","expires_at","processed_by_cashier"); list_filter=("status","order_type"); search_fields=("public_id","customer_name","phone"); inlines=[ItemInline]
@admin.register(AuditLog)
class AuditAdmin(admin.ModelAdmin): list_display=("order","action","actor","created_at"); readonly_fields=("order","action","actor","actor_role","before","after","metadata","created_at")
admin.site.register([OrderItem,OrderItemVariant,OrderItemAddOn,Payment])
