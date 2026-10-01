from datetime import timedelta
from decimal import Decimal
import secrets

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from menu.models import AddOn, MenuItem, VariantOption

def new_public_id(): return secrets.token_hex(4).upper()
def new_table_token(): return secrets.token_urlsafe(18)

class Table(models.Model):
    """A physical restaurant table. Its token is encoded in a permanent table QR."""
    number=models.CharField(max_length=30, unique=True)
    token=models.CharField(max_length=64, unique=True, default=new_table_token, editable=False)
    is_active=models.BooleanField(default=True, db_index=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta: indexes=[models.Index(fields=["is_active","number"])]
    def __str__(self): return f"Table {self.number}"

class Order(models.Model):
    class Status(models.TextChoices):
        PENDING="PENDING", "Pending"; PAID="PAID", "Paid"; CANCELLED="CANCELLED", "Cancelled"; EXPIRED="EXPIRED", "Expired"; REFUNDED="REFUNDED", "Refunded"
    class OrderType(models.TextChoices): DINE_IN="DINE_IN", "Dine in"; TAKEAWAY="TAKEAWAY", "Takeaway"
    public_id=models.CharField(max_length=12, unique=True, default=new_public_id, editable=False)
    status=models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    customer_name=models.CharField(max_length=150); phone=models.CharField(max_length=32, blank=True)
    order_type=models.CharField(max_length=10, choices=OrderType.choices); table=models.ForeignKey(Table,null=True,blank=True,on_delete=models.PROTECT,related_name="orders"); note=models.TextField(blank=True)
    total=models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(0)])
    created_at=models.DateTimeField(auto_now_add=True, db_index=True); updated_at=models.DateTimeField(auto_now=True); expires_at=models.DateTimeField(db_index=True)
    paid_at=models.DateTimeField(null=True, blank=True); cancelled_at=models.DateTimeField(null=True, blank=True); refunded_at=models.DateTimeField(null=True, blank=True)
    processed_by_cashier=models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="processed_orders")
    cancelled_by_cashier=models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="cancelled_orders")
    refunded_by=models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="refunded_orders")
    class Meta:
        indexes=[models.Index(fields=["status","created_at"]),models.Index(fields=["status","expires_at"])]
        constraints=[models.CheckConstraint(condition=Q(total__gte=0),name="order_total_nonnegative"),models.CheckConstraint(condition=Q(order_type="DINE_IN",table__isnull=False)|Q(order_type="TAKEAWAY",table__isnull=True),name="order_table_matches_type")]
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.order_type==self.OrderType.DINE_IN and not self.table_id: raise ValidationError({"table":"A valid table is required for dine-in."})
        if self.order_type==self.OrderType.TAKEAWAY and self.table_id: raise ValidationError({"table":"Takeaway orders cannot have a table."})
    def save(self,*args,**kwargs):
        if not self.expires_at: self.expires_at=timezone.now()+timedelta(hours=1)
        while not self.pk and Order.objects.filter(public_id=self.public_id).exists(): self.public_id=new_public_id()
        super().save(*args,**kwargs)
    def __str__(self): return self.public_id

class OrderItem(models.Model):
    order=models.ForeignKey(Order,on_delete=models.PROTECT,related_name="items"); menu_item=models.ForeignKey(MenuItem,null=True,blank=True,on_delete=models.PROTECT,related_name="order_items")
    item_name=models.CharField(max_length=150); base_price=models.DecimalField(max_digits=12,decimal_places=2,validators=[MinValueValidator(0)]); unit_price=models.DecimalField(max_digits=12,decimal_places=2,validators=[MinValueValidator(0)])
    quantity=models.PositiveIntegerField(validators=[MinValueValidator(1)]); line_total=models.DecimalField(max_digits=12,decimal_places=2,validators=[MinValueValidator(0)]); created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes=[models.Index(fields=["order","menu_item"]),models.Index(fields=["menu_item"])]
        constraints=[models.CheckConstraint(condition=Q(quantity__gt=0),name="order_item_quantity_positive"),models.CheckConstraint(condition=Q(base_price__gte=0),name="order_item_base_price_nonnegative"),models.CheckConstraint(condition=Q(unit_price__gte=0),name="order_item_unit_price_nonnegative"),models.CheckConstraint(condition=Q(line_total__gte=0),name="order_item_line_total_nonnegative")]
    def save(self,*args,**kwargs): self.line_total=self.unit_price*self.quantity; super().save(*args,**kwargs)

class OrderItemVariant(models.Model):
    order_item=models.ForeignKey(OrderItem,on_delete=models.PROTECT,related_name="variants"); variant_option=models.ForeignKey(VariantOption,null=True,blank=True,on_delete=models.PROTECT)
    group_name=models.CharField(max_length=100); option_name=models.CharField(max_length=100); price_adjustment=models.DecimalField(max_digits=12,decimal_places=2,validators=[MinValueValidator(0)])
    class Meta: constraints=[models.UniqueConstraint(fields=["order_item","group_name"],name="one_variant_per_group_per_order_item")]

class OrderItemAddOn(models.Model):
    order_item=models.ForeignKey(OrderItem,on_delete=models.PROTECT,related_name="addons"); addon=models.ForeignKey(AddOn,null=True,blank=True,on_delete=models.PROTECT)
    addon_name=models.CharField(max_length=100); unit_price=models.DecimalField(max_digits=12,decimal_places=2,validators=[MinValueValidator(0)]); quantity=models.PositiveIntegerField(default=1,validators=[MinValueValidator(1)])
    class Meta: constraints=[models.UniqueConstraint(fields=["order_item","addon_name"],name="one_addon_name_per_order_item")]

class Payment(models.Model):
    class Method(models.TextChoices): CASH="CASH","Cash"; CARD="CARD","Card"; QRIS="QRIS","QRIS"; OTHER="OTHER","Other"
    order=models.OneToOneField(Order,on_delete=models.PROTECT,related_name="payment"); method=models.CharField(max_length=12,choices=Method.choices,default=Method.CASH); amount=models.DecimalField(max_digits=12,decimal_places=2,validators=[MinValueValidator(0)]); paid_at=models.DateTimeField(default=timezone.now); cashier=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="payments"); external_reference=models.CharField(max_length=128,blank=True)

class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATED="ORDER_CREATED","Order created"; MODIFIED="ORDER_MODIFIED","Order modified"; ITEM_ADDED="ITEM_ADDED","Item added"; ITEM_REMOVED="ITEM_REMOVED","Item removed"; QUANTITY_CHANGED="QUANTITY_CHANGED","Quantity changed"; CUSTOMER_CHANGED="CUSTOMER_INFO_CHANGED","Customer info changed"; CANCELLED="ORDER_CANCELLED","Order cancelled"; PAID="ORDER_PAID","Order paid"; EXPIRED="ORDER_EXPIRED","Order expired"; REFUNDED="ORDER_REFUNDED","Order refunded"
    order=models.ForeignKey(Order,on_delete=models.PROTECT,related_name="audit_logs"); actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT,related_name="order_audits"); actor_role=models.CharField(max_length=20,default="SYSTEM"); action=models.CharField(max_length=32,choices=Action.choices); before=models.JSONField(default=dict,blank=True); after=models.JSONField(default=dict,blank=True); metadata=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: indexes=[models.Index(fields=["order","created_at"]),models.Index(fields=["action","created_at"])]
