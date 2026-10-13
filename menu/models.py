from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

# Class untuk kategori menu, item menu, grup varian, opsi varian, dan add-on.
# [OOP: Inheritance] Category mewarisi models.Model sehingga otomatis jadi tabel database
# dengan method ORM (save, delete, objects) tanpa menulis SQL.
# [OOP: Encapsulation] Data (name, is_active) dan aturannya (unique, index di Meta) dibungkus di satu class.
# [OOP: Polymorphism] __str__ di-override agar objek tampil sebagai nama kategori.
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # [OOP: Encapsulation] Nested class Meta membungkus konfigurasi tabel (index, constraint, ordering).
    class Meta:
        indexes = [models.Index(fields=["is_active", "name"])]

    def __str__(self):
        return self.name

# [OOP: Inheritance] MenuTag mewarisi models.Model.
# [OOP: Polymorphism] __str__ di-override: menampilkan display_name, atau name bila kosong.
class MenuTag(models.Model):
    name = models.SlugField(max_length=50, unique=True)
    display_name = models.CharField(max_length=80, blank=True)

    def __str__(self):
        return self.display_name or self.name

# [OOP: Inheritance] MenuTagAlias mewarisi models.Model sehingga otomatis menjadi tabel
# database dengan method ORM (save, delete, objects) tanpa menulis SQL.
# [OOP: Association] Hubungan has-a: satu MenuTag punya banyak alias (ForeignKey,
# related_name="aliases"). on_delete=CASCADE berarti alias ikut terhapus bila tag-nya dihapus.
# [OOP: Encapsulation] Data alias (tag, phrase, is_active) dan aturannya (unique constraint,
# index di Meta) dibungkus dalam satu class.
class MenuTagAlias(models.Model):
    tag = models.ForeignKey(MenuTag, on_delete=models.CASCADE, related_name="aliases")
    phrase = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True, db_index=True)

    # [OOP: Encapsulation] Nested class Meta membungkus konfigurasi tabel (index, constraint, ordering).
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tag", "phrase"],
                name="unique_menu_tag_alias",
            )
        ]
        indexes = [models.Index(fields=["is_active", "phrase"])]

    # [OOP: Polymorphism] __str__ di-override (method overriding) agar objek tampil
    # sebagai "tag: frasa" di Django Admin dan saat dicetak.
    def __str__(self):
        return f"{self.tag}: {self.phrase}"

# Class untuk item menunya langsung
# [OOP: Inheritance] MenuItem mewarisi models.Model.
# [OOP: Association] ForeignKey ke Category (many-to-one: banyak menu di satu kategori)
# dan ManyToManyField ke MenuTag (many-to-many).
# [OOP: Encapsulation] Aturan harga >= 0 dibungkus sebagai constraint di Meta.
# [OOP: Polymorphism] __str__ di-override agar tampil sebagai nama menu.
class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    image = models.ImageField(upload_to="menu/", blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_available = models.BooleanField(default=True, db_index=True)
    stock_estimate = models.PositiveIntegerField(null=True, blank=True)
    tags = models.ManyToManyField(MenuTag, related_name="menu_items", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # [OOP: Encapsulation] Nested class Meta membungkus konfigurasi tabel (index, constraint, ordering).
    class Meta:
        indexes = [models.Index(fields=["category", "is_active", "is_available"])]
        constraints = [models.CheckConstraint(condition=Q(price__gte=0), name="menu_item_price_nonnegative")]

    def __str__(self):
        return self.name

# Class untuk variasi menu, termasuk grup varian dan opsi varian
# [OOP: Inheritance] VariantGroup mewarisi models.Model.
# [OOP: Association] Hubungan has-a: satu MenuItem punya banyak VariantGroup (ForeignKey).
# [OOP: Polymorphism] __str__ di-override: "nama menu: nama grup".
class VariantGroup(models.Model):
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="variant_groups")
    name = models.CharField(max_length=100)
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    # [OOP: Encapsulation] Nested class Meta membungkus konfigurasi tabel (index, constraint, ordering).
    class Meta:
        ordering = ["display_order", "id"]
        constraints = [models.UniqueConstraint(fields=["menu_item", "name"], name="unique_variant_group_per_item")]

    def __str__(self):
        return f"{self.menu_item}: {self.name}"

# Class untuk opsi varian, termasuk penyesuaian harga dan status aktif
# [OOP: Inheritance] VariantOption mewarisi models.Model.
# [OOP: Association] Hubungan has-a: satu VariantGroup punya banyak VariantOption.
# [OOP: Encapsulation] Penyesuaian harga dan status aktif disimpan bersama opsinya.
class VariantOption(models.Model):
    group = models.ForeignKey(VariantGroup, on_delete=models.PROTECT, related_name="options")
    name = models.CharField(max_length=100)
    price_adjustment = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    # [OOP: Encapsulation] Nested class Meta membungkus konfigurasi tabel (index, constraint, ordering).
    class Meta:
        ordering = ["display_order", "id"]
        constraints = [models.UniqueConstraint(fields=["group", "name"], name="unique_variant_option_per_group")]

    def __str__(self):
        return self.name

# [OOP: Inheritance] AddOn mewarisi models.Model.
# [OOP: Association] ManyToManyField ke MenuItem: satu add-on boleh dipakai banyak menu.
# [OOP: Encapsulation] Data add-on dan perilakunya (dapatkan_status) dibungkus dalam satu class.
class AddOn(models.Model):
    menu_items = models.ManyToManyField(MenuItem, related_name="allowed_addons", blank=True)
    name = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # [OOP: Encapsulation] Nested class Meta membungkus konfigurasi tabel (index, constraint, ordering).
    class Meta:
        indexes = [models.Index(fields=["is_active", "is_available"])]
        constraints = [models.CheckConstraint(condition=Q(price__gte=0), name="addon_price_nonnegative")]

    # [OOP: Abstraction] Pemanggil cukup memanggil dapatkan_status() untuk mendapat teks
    # "Tersedia"/"Sedang Kosong" tanpa perlu tahu logika is_available di baliknya.
    def dapatkan_status(self):
        return "Tersedia" if self.is_available else "Sedang Kosong"

    def __str__(self):
        return self.name
