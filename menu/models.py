from django.core.exceptions import ValidationError
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

    def __str__(self) -> str:
        return self.name


class MenuTag(models.Model):
    name = models.SlugField(max_length=50, unique=True)
    display_name = models.CharField(max_length=80, blank=True)

    def __str__(self) -> str:
        return self.display_name or self.name


class MenuTagAlias(models.Model):
    tag = models.ForeignKey(MenuTag, on_delete=models.CASCADE, related_name="aliases")
    phrase = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tag", "phrase"],
                name="unique_menu_tag_alias",
            )
        ]
        indexes = [models.Index(fields=["is_active", "phrase"])]

    def __str__(self) -> str:
        return f"{self.tag}: {self.phrase}"

# Class untuk item menunya langsung
class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    image = models.ImageField(upload_to="menu/", blank=True)
    detail_image = models.ImageField(upload_to="menu/detail/", blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_available = models.BooleanField(default=True, db_index=True)
    stock_estimate = models.PositiveIntegerField(null=True, blank=True)
    tags = models.ManyToManyField(MenuTag, related_name="menu_items", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["category", "is_active", "is_available"])]
        constraints = [models.CheckConstraint(condition=Q(price__gte=0), name="menu_item_price_nonnegative")]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: object, **kwargs: object) -> None:
        update_fields = kwargs.get("update_fields")
        for field_name in ("image", "detail_image"):
            image = getattr(self, field_name)
            if image and not image._committed and (update_fields is None or field_name in update_fields):
                from .image_processing import archive_original, prepare_photo
                photo = prepare_photo(image.file)
                archive_original(photo)
                setattr(self, field_name, photo)
        return super().save(*args, **kwargs)

class MenuItemAlias(models.Model):
    """Staff-managed identity phrase; collisions across items require clarification."""

    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name="identity_aliases")
    phrase = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["menu_item", "phrase"], name="unique_menu_item_alias")]
        indexes = [models.Index(fields=["is_active", "phrase"], name="menu_item_alias_active_idx")]

    @staticmethod
    def normalize_phrase(value: str) -> str:
        return " ".join(value.casefold().split())

    def clean(self) -> None:
        super().clean()
        self.phrase = self.normalize_phrase(self.phrase)
        if not self.phrase or len(self.phrase) > 100:
            raise ValidationError({"phrase": "Alias harus berisi 1–100 karakter."})

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.menu_item}: {self.phrase}"


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

    def __str__(self) -> str:
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

    def __str__(self) -> str:
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

    def dapatkan_status(self) -> str:
        return "Tersedia" if self.is_available else "Sedang Kosong"

    def __str__(self) -> str:
        return self.name
