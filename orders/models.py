from datetime import timedelta
from decimal import Decimal
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from menu.models import AddOn, MenuItem, VariantOption


def new_public_id():
    return secrets.token_hex(4).upper()


def new_table_token():
    return secrets.token_urlsafe(18)


# =====================================================================
# CUSTOM EXCEPTION
# =====================================================================

# [OOP: Inheritance] InvalidOrderTransition mewarisi ValueError.
# Karena turunan ValueError, kode lama yang menangkap ValueError tetap jalan.
class InvalidOrderTransition(ValueError):
    """Dilempar ketika status order diubah dengan cara yang tidak diizinkan."""


# =====================================================================
# ABSTRACT BASE CLASSES (parent buatan sendiri)
# =====================================================================

# [OOP: Abstraction] Class abstrak: hanya menjelaskan "apa" (created_at & updated_at),
# tidak punya tabel sendiri (abstract = True).
# [OOP: Inheritance] Parent ini diwarisi oleh Table dan Order, sehingga field yang
# sama tidak ditulis ulang.
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# [OOP: Abstraction] Konsep "sesuatu yang menambah harga item". Class ini menetapkan
# kontrak (subtotal dan label) tanpa menjelaskan caranya; tiap anak yang mengisi.
# [OOP: Inheritance] Diwarisi oleh OrderItemVariant dan OrderItemAddOn.
class PriceModifier(models.Model):
    class Meta:
        abstract = True

    def subtotal(self):
        """Tambahan harga dari modifier ini. Wajib di-override oleh anak."""
        raise NotImplementedError("Subclass harus mengimplementasikan subtotal().")

    def label(self):
        """Teks singkat modifier ini. Wajib di-override oleh anak."""
        raise NotImplementedError("Subclass harus mengimplementasikan label().")

    # Method konkret di parent: dipakai bersama oleh semua anak (reuse lewat inheritance),
    # tapi hasilnya berbeda karena memanggil label()/subtotal() milik anak masing-masing.
    def describe(self):
        return f"{self.label()} (+{self.subtotal()})"


# =====================================================================
# MODELS
# =====================================================================

# [OOP: Inheritance] Table mewarisi TimeStampedModel (buatan sendiri), yang mewarisi models.Model.
# [OOP: Encapsulation] token QR dibuat otomatis (default=new_table_token) dan editable=False,
# jadi tidak bisa diubah sembarangan dari luar.
# [OOP: Polymorphism] __str__ di-override: "Table <nomor>".
class Table(TimeStampedModel):
    """A physical restaurant table. Its token is encoded in a permanent table QR."""

    number = models.CharField(max_length=30, unique=True)
    token = models.CharField(
        max_length=64, unique=True, default=new_table_token, editable=False
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["is_active", "number"])]

    def __str__(self):
        return f"Table {self.number}"


# [OOP: Inheritance] Order mewarisi TimeStampedModel -> models.Model.
# [OOP: Encapsulation] Data pesanan, aturan konsistensi (constraint di Meta), validasi (clean),
# dan aturan perpindahan status (mark_paid/cancel/expire/refund) dibungkus dalam satu class.
# [OOP: Association] ForeignKey ke Table dan ke User (kasir pemroses, pembatal, dan refund).
class Order(TimeStampedModel):
    # [OOP: Inheritance] Status mewarisi TextChoices (turunan enum): daftar status resmi
    # dikelompokkan sebagai konstanta, bukan string liar.
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"
        EXPIRED = "EXPIRED", "Expired"
        REFUNDED = "REFUNDED", "Refunded"

    # [OOP: Inheritance] OrderType mewarisi TextChoices; jenis pesanan dibatasi.
    class OrderType(models.TextChoices):
        DINE_IN = "DINE_IN", "Dine in"
        TAKEAWAY = "TAKEAWAY", "Takeaway"

    # [OOP: Encapsulation] Peta perpindahan status yang sah ada di satu tempat.
    ALLOWED_TRANSITIONS = {
        Status.PENDING.value: (Status.PAID, Status.CANCELLED, Status.EXPIRED),
        Status.PAID.value: (Status.REFUNDED,),
        Status.CANCELLED.value: (),
        Status.EXPIRED.value: (),
        Status.REFUNDED.value: (),
    }

    public_id = models.CharField(
        max_length=12, unique=True, default=new_public_id, editable=False
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    customer_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=32, blank=True)
    order_type = models.CharField(max_length=10, choices=OrderType.choices)
    table = models.ForeignKey(
        Table,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    note = models.TextField(blank=True)
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
    )
    # Dideklarasikan ulang agar db_index=True tetap sama seperti sebelumnya
    # (Django mengizinkan override field dari abstract parent).
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    processed_by_cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="processed_orders",
    )
    cancelled_by_cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cancelled_orders",
    )
    refunded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="refunded_orders",
    )

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["status", "expires_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(total__gte=0), name="order_total_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(order_type="DINE_IN", table__isnull=False)
                | Q(order_type="TAKEAWAY", table__isnull=True),
                name="order_table_matches_type",
            ),
        ]

    # ---------- properti (getter gaya Python) ----------

    # [OOP: Encapsulation] @property: nilai turunan dibaca seperti atribut biasa,
    # tapi logikanya tersimpan di dalam class.
    @property
    def is_pending(self):
        return self.status == self.Status.PENDING

    @property
    def is_expired(self):
        return self.is_pending and timezone.now() >= self.expires_at

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())

    # ---------- validasi & penyimpanan ----------

    # [OOP: Polymorphism] clean() meng-override method bawaan Model (method overriding).
    # [OOP: Encapsulation] Aturan bisnis "dine-in wajib meja, takeaway tanpa meja" ditaruh di model sendiri.
    def clean(self):
        if self.order_type == self.OrderType.DINE_IN and not self.table_id:
            raise ValidationError({"table": "A valid table is required for dine-in."})
        if self.order_type == self.OrderType.TAKEAWAY and self.table_id:
            raise ValidationError({"table": "Takeaway orders cannot have a table."})

    # [OOP: Polymorphism] save() di-override, lalu memanggil super().save() agar penyimpanan asli tetap jalan.
    # [OOP: Abstraction] Pembuatan public_id unik dan expires_at otomatis disembunyikan di sini;
    # pemanggil cukup memanggil save().
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=1)
        while not self.pk and Order.objects.filter(public_id=self.public_id).exists():
            self.public_id = new_public_id()
        super().save(*args, **kwargs)

    # ---------- perilaku (behavior methods) ----------

    # [OOP: Abstraction] Pemanggil cukup bertanya "boleh pindah ke status ini?"
    # tanpa tahu aturan di baliknya.
    def can_transition_to(self, new_status):
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, ())

    # [OOP: Encapsulation] Method private (awalan _): satu-satunya jalan mengganti status.
    # Aturan transisi dicek di sini, sehingga tidak bisa dilewati oleh method publik.
    def _transition(self, new_status, **fields):
        if not self.can_transition_to(new_status):
            raise InvalidOrderTransition(
                f"Order {self.public_id} cannot change from {self.status} to {new_status}."
            )
        self.status = new_status
        for name, value in fields.items():
            setattr(self, name, value)
        self.save(update_fields=["status", "updated_at", *fields.keys()])

    def mark_paid(self, cashier):
        self._transition(
            self.Status.PAID,
            paid_at=timezone.now(),
            processed_by_cashier=cashier,
        )

    def cancel(self, cashier):
        self._transition(
            self.Status.CANCELLED,
            cancelled_at=timezone.now(),
            cancelled_by_cashier=cashier,
        )

    def expire(self):
        self._transition(self.Status.EXPIRED)

    def refund(self, user):
        self._transition(
            self.Status.REFUNDED,
            refunded_at=timezone.now(),
            refunded_by=user,
        )

    # [OOP: Abstraction] Menghitung total dari item disembunyikan di sini (tidak mengubah data).
    def calculate_total(self):
        return sum((item.line_total for item in self.items.all()), Decimal("0.00"))

    # [OOP: Polymorphism] __str__ di-override: objek Order tampil sebagai public_id.
    def __str__(self):
        return self.public_id


# [OOP: Inheritance] OrderItem mewarisi models.Model.
# [OOP: Association] Hubungan has-a: Order punya banyak OrderItem (ForeignKey, related_name="items").
# [OOP: Encapsulation] Nama dan harga disimpan sebagai snapshot, sehingga perubahan menu tidak mengubah transaksi lama.
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="items")
    menu_item = models.ForeignKey(
        MenuItem,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    item_name = models.CharField(max_length=150)
    base_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    line_total = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["order", "menu_item"]),
            models.Index(fields=["menu_item"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="order_item_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(base_price__gte=0),
                name="order_item_base_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0),
                name="order_item_unit_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(line_total__gte=0),
                name="order_item_line_total_nonnegative",
            ),
        ]

    # [OOP: Polymorphism] Satu loop untuk dua tipe berbeda: varian dan add-on dipanggil
    # lewat method yang sama (subtotal), tanpa if/else per tipe.
    # Hanya untuk informasi; tidak dipakai untuk mengubah unit_price/line_total.
    @property
    def extras_total(self):
        modifiers = list(self.variants.all()) + list(self.addons.all())
        return sum((m.subtotal() for m in modifiers), Decimal("0.00"))

    # [OOP: Polymorphism] save() di-override: line_total dihitung otomatis (unit_price x quantity),
    # lalu super().save() dipanggil.
    # [OOP: Abstraction] Pemanggil tidak perlu menghitung subtotal sendiri.
    def save(self, *args, **kwargs):
        self.line_total = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    # [OOP: Polymorphism] __str__ di-override.
    def __str__(self):
        return f"{self.quantity}x {self.item_name}"


# [OOP: Inheritance] Mewarisi PriceModifier (abstract buatan sendiri) -> models.Model.
# [OOP: Association] Hubungan has-a: satu OrderItem punya banyak pilihan varian (snapshot).
class OrderItemVariant(PriceModifier):
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.PROTECT, related_name="variants"
    )
    variant_option = models.ForeignKey(
        VariantOption, null=True, blank=True, on_delete=models.PROTECT
    )
    group_name = models.CharField(max_length=100)
    option_name = models.CharField(max_length=100)
    price_adjustment = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order_item", "group_name"],
                name="one_variant_per_group_per_order_item",
            )
        ]

    # [OOP: Polymorphism] Override subtotal(): varian = selisih harga tetap.
    def subtotal(self):
        return self.price_adjustment

    def label(self):
        return f"{self.group_name}: {self.option_name}"

    def __str__(self):
        return self.label()


# [OOP: Inheritance] Mewarisi PriceModifier (abstract buatan sendiri) -> models.Model.
# [OOP: Association] Hubungan has-a: satu OrderItem punya banyak add-on (snapshot).
class OrderItemAddOn(PriceModifier):
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.PROTECT, related_name="addons"
    )
    addon = models.ForeignKey(AddOn, null=True, blank=True, on_delete=models.PROTECT)
    addon_name = models.CharField(max_length=100)
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    quantity = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order_item", "addon_name"],
                name="one_addon_name_per_order_item",
            )
        ]

    # [OOP: Polymorphism] Override subtotal(): add-on = harga satuan x jumlah.
    # Nama method sama dengan OrderItemVariant, cara hitung berbeda.
    def subtotal(self):
        return self.unit_price * self.quantity

    def label(self):
        return f"{self.addon_name} x{self.quantity}"

    def __str__(self):
        return self.label()


# [OOP: Inheritance] Payment mewarisi models.Model.
# [OOP: Association] OneToOneField ke Order: satu pesanan hanya punya satu pembayaran.
# [OOP: Inheritance] Class bersarang Method mewarisi TextChoices (CASH/CARD/QRIS/OTHER).
class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        CARD = "CARD", "Card"
        QRIS = "QRIS", "QRIS"
        OTHER = "OTHER", "Other"

    order = models.OneToOneField(
        Order, on_delete=models.PROTECT, related_name="payment"
    )
    method = models.CharField(
        max_length=12, choices=Method.choices, default=Method.CASH
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    amount_received = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    change_given = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    paid_at = models.DateTimeField(default=timezone.now)
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments"
    )
    external_reference = models.CharField(max_length=128, blank=True)

    # [OOP: Polymorphism] __str__ di-override.
    def __str__(self):
        return f"{self.get_method_display()} {self.amount}"


# [OOP: Inheritance] AuditLog mewarisi models.Model; class bersarang Action mewarisi TextChoices.
# [OOP: Encapsulation] Setiap aksi pesanan dicatat lengkap (aktor, before/after, metadata) dalam satu objek.
# [OOP: Association] ForeignKey ke Order dan ke User (aktor).
class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATED = "ORDER_CREATED", "Order created"
        MODIFIED = "ORDER_MODIFIED", "Order modified"
        ITEM_ADDED = "ITEM_ADDED", "Item added"
        ITEM_REMOVED = "ITEM_REMOVED", "Item removed"
        QUANTITY_CHANGED = "QUANTITY_CHANGED", "Quantity changed"
        CUSTOMER_CHANGED = "CUSTOMER_INFO_CHANGED", "Customer info changed"
        CANCELLED = "ORDER_CANCELLED", "Order cancelled"
        PAID = "ORDER_PAID", "Order paid"
        EXPIRED = "ORDER_EXPIRED", "Order expired"
        REFUNDED = "ORDER_REFUNDED", "Order refunded"

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name="audit_logs"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="order_audits",
    )
    actor_role = models.CharField(max_length=20, default="SYSTEM")
    action = models.CharField(max_length=32, choices=Action.choices)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["order", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

    # [OOP: Polymorphism] __str__ di-override.
    def __str__(self):
        return f"{self.get_action_display()} (order #{self.order_id})"