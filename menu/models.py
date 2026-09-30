from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

# Class untuk kategori menu, item menu, grup varian, opsi varian, dan add-on.
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["is_active", "name"])]

    def __str__(self):
        return self.name

# Class untuk item menunya langsung
class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    image = models.ImageField(upload_to="menu/", blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_available = models.BooleanField(default=True, db_index=True)
    stock_estimate = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["category", "is_active", "is_available"])]
        constraints = [models.CheckConstraint(condition=Q(price__gte=0), name="menu_item_price_nonnegative")]

    def __str__(self):
        return self.name

# Class untuk variasi menu, termasuk grup varian dan opsi varian
class VariantGroup(models.Model):
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="variant_groups")
    name = models.CharField(max_length=100)
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]
        constraints = [models.UniqueConstraint(fields=["menu_item", "name"], name="unique_variant_group_per_item")]

    def __str__(self):
        return f"{self.menu_item}: {self.name}"

# Class untuk opsi varian, termasuk penyesuaian harga dan status aktif
class VariantOption(models.Model):
    group = models.ForeignKey(VariantGroup, on_delete=models.PROTECT, related_name="options")
    name = models.CharField(max_length=100)
    price_adjustment = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]
        constraints = [models.UniqueConstraint(fields=["group", "name"], name="unique_variant_option_per_group")]

    def __str__(self):
        return self.name


class AddOn(models.Model):
    menu_items = models.ManyToManyField(MenuItem, related_name="allowed_addons", blank=True)
    name = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["is_active", "is_available"])]
        constraints = [models.CheckConstraint(condition=Q(price__gte=0), name="addon_price_nonnegative")]

    def __str__(self):
        return self.name
