from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


# =====================================================================
# ABSTRACT BASE CLASSES (parent buatan sendiri untuk model menu)
# =====================================================================

# [OOP: Abstraction] MenuDomainObject adalah class abstrak (abstract = True): ia tidak punya
# tabel database sendiri dan tidak pernah dibuat objeknya langsung. Fungsinya hanya
# menetapkan "kontrak": setiap objek menu harus bisa menjawab pertanyaan is_usable().
# Class ini menjelaskan APA yang harus ada, bukan BAGAIMANA caranya.
# [OOP: Inheritance] Ini parent buatan sendiri (bukan sekadar models.Model dari Django).
# Ia sendiri mewarisi models.Model, lalu diwarisi oleh 7 class konkret di bawah:
# 5 secara langsung (Category, MenuTag, MenuTagAlias, MenuItem, VariantGroup) dan
# 2 lewat MenuPriceModifier (VariantOption, AddOn).
class MenuDomainObject(models.Model):
    """Perilaku bersama untuk semua objek yang termasuk katalog menu.

    Ini adalah model abstrak Django, sehingga tidak membuat tabel database.
    Model konkret mengimplementasikan ``is_usable`` sesuai aturan bisnisnya
    masing-masing, sementara pemanggil bisa memakai antarmuka yang sama
    secara polimorfik.
    """

    # [OOP: Abstraction] abstract = True membuat Django hanya memakai class ini sebagai
    # cetakan untuk diwarisi, bukan sebagai tabel.
    class Meta:
        abstract = True

    # [OOP: Abstraction] Method abstrak: hanya menyebut tujuan, tanpa isi.
    # raise NotImplementedError memaksa setiap anak untuk menulis versinya sendiri;
    # kalau lupa, program langsung error saat dipanggil (bukan diam-diam salah).
    # Catatan: sengaja tidak memakai abc.ABC karena bentrok dengan metaclass milik Django.
    # [OOP: Polymorphism] Inilah "satu pertanyaan, banyak jawaban": semua anak punya
    # is_usable(), tetapi aturannya berbeda-beda (lihat tiap class di bawah).
    def is_usable(self):
        """Mengembalikan apakah objek ini boleh ikut dalam katalog aktif."""
        raise NotImplementedError

    # [OOP: Inheritance] Method konkret yang ditulis SEKALI di parent dan otomatis dimiliki
    # semua anak tanpa menulis ulang (reuse kode).
    # [OOP: Polymorphism] Di dalamnya memanggil self.is_usable(). Python memilih versi milik
    # objek yang sedang dipakai: Category memakai aturan Category, AddOn memakai aturan AddOn.
    # Kodenya satu, hasilnya menyesuaikan jenis objek.
    def status_label(self):
        return "Tersedia" if self.is_usable() else "Tidak tersedia"


# [OOP: Inheritance] Pewarisan BERTINGKAT (multilevel): MenuPriceModifier mewarisi
# MenuDomainObject, lalu diwarisi lagi oleh VariantOption dan AddOn.
# Jadi VariantOption punya tiga lapis leluhur: MenuPriceModifier -> MenuDomainObject -> models.Model.
# [OOP: Abstraction] Class abstrak kedua untuk konsep "sesuatu yang menambah harga menu".
# Ia hanya menetapkan kontrak extra_price() tanpa menjelaskan cara menghitungnya.
class MenuPriceModifier(MenuDomainObject):
    """Konsep abstrak: apa pun yang menambah harga sebuah item menu.

    Varian menambah harga lewat ``price_adjustment``, add-on lewat ``price``.
    Dengan kontrak ``extra_price()``, pemanggil tidak perlu tahu nama
    field yang dipakai masing-masing.
    """

    class Meta:
        abstract = True

    # [OOP: Polymorphism] Satu nama method, dua cara menghitung (lihat VariantOption dan AddOn).
    # Pemanggil (MenuItem.calculate_price) cukup memanggil extra_price() tanpa if/else
    # untuk mengecek jenis objeknya.
    def extra_price(self):
        """Mengembalikan tambahan harga dari modifier ini. Wajib di-override oleh anak."""
        raise NotImplementedError


# =====================================================================
# MODELS
# =====================================================================

# [OOP: Inheritance] Category mewarisi MenuDomainObject (buatan sendiri) -> models.Model,
# sehingga otomatis menjadi tabel dengan method ORM (save, delete, objects) dan juga
# mendapat status_label() dari parent.
# [OOP: Encapsulation] Data (name, is_active) dan aturannya (unique, index di Meta) dibungkus
# dalam satu class.
class Category(MenuDomainObject):
    """Kategori menu beserta status aktif/nonaktifnya di katalog."""

    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # [OOP: Encapsulation] Nested class Meta membungkus konfigurasi tabel (index).
    class Meta:
        indexes = [models.Index(fields=["is_active", "name"])]

    # [OOP: Polymorphism] Override is_usable(): kategori dianggap bisa dipakai
    # kalau flag is_active-nya menyala. Aturan paling sederhana di antara semua class.
    def is_usable(self):
        return self.is_active

    # [OOP: Polymorphism] __str__ di-override agar objek tampil sebagai nama kategori.
    def __str__(self):
        return self.name


# [OOP: Inheritance] MenuTag mewarisi MenuDomainObject.
# [OOP: Encapsulation] Logika "nama tampilan" dibungkus di method label(), jadi pemanggil
# tidak perlu mengurus sendiri kasus display_name kosong.
class MenuTag(MenuDomainObject):
    """Karakteristik yang bisa dipakai ulang oleh layanan rekomendasi."""

    name = models.SlugField(max_length=50, unique=True)
    display_name = models.CharField(max_length=80, blank=True)

    # [OOP: Polymorphism] Override is_usable(): tag selalu dianggap bisa dipakai
    # (tidak punya flag aktif/nonaktif sendiri).
    def is_usable(self):
        return True

    # [OOP: Abstraction] Pemanggil cukup memanggil label() untuk mendapat teks tampilan:
    # display_name bila ada, atau name bila display_name kosong.
    def label(self):
        return self.display_name or self.name

    # [OOP: Polymorphism] __str__ di-override dengan memakai label().
    def __str__(self):
        return self.label()


# [OOP: Inheritance] MenuTagAlias mewarisi MenuDomainObject.
# [OOP: Association] Hubungan has-a: satu MenuTag punya banyak alias (ForeignKey,
# related_name="aliases"). on_delete=CASCADE berarti alias ikut terhapus bila tag-nya dihapus.
# [OOP: Encapsulation] Data alias (tag, phrase, is_active) dan aturannya (unique constraint,
# index di Meta) dibungkus dalam satu class.
class MenuTagAlias(MenuDomainObject):
    """Frasa yang dikelola staf untuk memetakan teks pengguna ke sebuah tag menu."""

    tag = models.ForeignKey(MenuTag, on_delete=models.CASCADE, related_name="aliases")
    phrase = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True, db_index=True)

    # [OOP: Encapsulation] Nested class Meta membungkus constraint dan index tabel.
    # Constraint unik mencegah alias yang sama dibuat dua kali pada tag yang sama.
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tag", "phrase"],
                name="unique_menu_tag_alias",
            )
        ]
        indexes = [models.Index(fields=["is_active", "phrase"])]

    # [OOP: Polymorphism] Override is_usable(): alias bisa dipakai bila dirinya aktif
    # DAN tag induknya juga bisa dipakai.
    # [OOP: Encapsulation] Alias bertanya ke tag-nya (self.tag.is_usable()) tanpa perlu
    # tahu aturan di dalam tag.
    def is_usable(self):
        return self.is_active and self.tag.is_usable()

    # [OOP: Polymorphism] __str__ di-override: tampil sebagai "tag: frasa".
    def __str__(self):
        return f"{self.tag}: {self.phrase}"


# [OOP: Inheritance] MenuItem mewarisi MenuDomainObject.
# [OOP: Association] ForeignKey ke Category (many-to-one: banyak menu di satu kategori,
# PROTECT = kategori tidak bisa dihapus selama masih punya menu) dan ManyToManyField ke
# MenuTag (many-to-many).
# [OOP: Encapsulation] Aturan harga >= 0 dibungkus sebagai constraint di Meta, dan logika
# harga/ketersediaan dibungkus sebagai method di dalam class ini.
class MenuItem(MenuDomainObject):
    """Item menu yang bisa dijual, lengkap dengan varian, tag, dan add-on."""

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    image = models.ImageField(upload_to="menu/", blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_available = models.BooleanField(default=True, db_index=True)
    stock_estimate = models.PositiveIntegerField(null=True, blank=True)
    tags = models.ManyToManyField(MenuTag, related_name="menu_items", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # [OOP: Encapsulation] Nested class Meta membungkus index dan constraint tabel.
    # CheckConstraint membuat database sendiri menolak harga negatif.
    class Meta:
        indexes = [models.Index(fields=["category", "is_active", "is_available"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=0),
                name="menu_item_price_nonnegative",
            )
        ]

    # [OOP: Polymorphism] Override is_usable(): aturan terlengkap di antara semua class.
    # Menu bisa dipakai bila aktif, tersedia, DAN kategorinya juga bisa dipakai.
    # [OOP: Encapsulation] Menu bertanya ke kategorinya lewat self.category.is_usable().
    def is_usable(self):
        return (
            self.is_active
            and self.is_available
            and self.category.is_usable()
        )

    # [OOP: Abstraction] Pemanggil cukup memanggil method ini untuk mendapat grup varian
    # aktif tanpa perlu menulis filter query sendiri.
    def active_variant_groups(self):
        return self.variant_groups.filter(is_active=True)

    # [OOP: Abstraction] Sama: daftar add-on yang boleh dipilih (aktif dan tersedia)
    # diambil lewat satu panggilan.
    def available_addons(self):
        return self.allowed_addons.filter(is_active=True, is_available=True)

    # [OOP: Abstraction] Seluruh rumus harga (harga dasar + semua tambahan) disembunyikan
    # di sini; pemanggil cukup memberi pilihan dan menerima total.
    # [OOP: Polymorphism] Varian dan add-on digabung dalam SATU loop. Tiap objek dipanggil
    # lewat extra_price() yang sama, dan masing-masing menjawab dengan caranya sendiri
    # (varian memakai price_adjustment, add-on memakai price). Tidak ada if/else per tipe.
    # [OOP: Encapsulation] Harga dihitung dari data model di server (bukan dari harga yang
    # dikirim klien), sehingga tidak bisa dimanipulasi dari luar.
    def calculate_price(self, variant_options=(), addons=()):
        """Menghitung harga konfigurasi ini memakai data model di sisi server."""
        modifiers = [*variant_options, *addons]
        extras_total = sum(
            (modifier.extra_price() for modifier in modifiers),
            Decimal("0.00"),
        )
        return self.price + extras_total

    # [OOP: Polymorphism] __str__ di-override agar tampil sebagai nama menu.
    def __str__(self):
        return self.name


# [OOP: Inheritance] VariantGroup mewarisi MenuDomainObject.
# [OOP: Association] Hubungan has-a: satu MenuItem punya banyak VariantGroup (ForeignKey,
# related_name="variant_groups").
# [OOP: Encapsulation] Urutan tampil (ordering) dan keunikan nama grup per menu dibungkus di Meta.
class VariantGroup(MenuDomainObject):
    """Kelompok pilihan yang bisa dipilih, milik satu item menu."""

    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.PROTECT,
        related_name="variant_groups",
    )
    name = models.CharField(max_length=100)
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    # [OOP: Encapsulation] ordering membuat grup selalu muncul urut display_order;
    # constraint mencegah dua grup bernama sama pada menu yang sama.
    class Meta:
        ordering = ["display_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["menu_item", "name"],
                name="unique_variant_group_per_item",
            )
        ]

    # [OOP: Polymorphism] Override is_usable(): grup bisa dipakai bila dirinya aktif
    # DAN menu induknya bisa dipakai (menu sendiri akan bertanya lagi ke kategorinya).
    def is_usable(self):
        return self.is_active and self.menu_item.is_usable()

    # [OOP: Abstraction] Satu panggilan untuk mendapat opsi yang aktif.
    def active_options(self):
        return self.options.filter(is_active=True)

    # [OOP: Polymorphism] __str__ di-override: "nama menu: nama grup".
    def __str__(self):
        return f"{self.menu_item}: {self.name}"


# [OOP: Inheritance] VariantOption mewarisi MenuPriceModifier -> MenuDomainObject -> models.Model
# (pewarisan bertingkat), sehingga ia wajib punya is_usable() dan extra_price().
# [OOP: Association] Hubungan has-a: satu VariantGroup punya banyak VariantOption
# (related_name="options").
# [OOP: Encapsulation] Penyesuaian harga dan status aktif disimpan bersama opsinya.
class VariantOption(MenuPriceModifier):
    """Satu pilihan varian beserta penyesuaian harganya."""

    group = models.ForeignKey(
        VariantGroup,
        on_delete=models.PROTECT,
        related_name="options",
    )
    name = models.CharField(max_length=100)
    price_adjustment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    # [OOP: Encapsulation] ordering dan constraint keunikan nama opsi per grup dibungkus di Meta.
    class Meta:
        ordering = ["display_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "name"],
                name="unique_variant_option_per_group",
            )
        ]

    # [OOP: Polymorphism] Override is_usable(): opsi bisa dipakai bila dirinya aktif
    # DAN grup induknya bisa dipakai.
    # [OOP: Encapsulation] Terbentuk rantai tanggung jawab: opsi -> grup -> menu -> kategori.
    # Tiap objek hanya bertanya ke induk terdekatnya, tanpa tahu aturan induk di atasnya.
    def is_usable(self):
        return self.is_active and self.group.is_usable()

    # [OOP: Polymorphism] Override extra_price(): untuk varian, tambahan harganya
    # adalah price_adjustment. Nama method sama dengan AddOn, isi berbeda.
    def extra_price(self):
        return self.price_adjustment

    # [OOP: Polymorphism] __str__ di-override agar tampil sebagai nama opsi.
    def __str__(self):
        return self.name


# [OOP: Inheritance] AddOn mewarisi MenuPriceModifier -> MenuDomainObject -> models.Model
# (pewarisan bertingkat), sehingga ia wajib punya is_usable() dan extra_price().
# [OOP: Association] ManyToManyField ke MenuItem: satu add-on boleh dipakai banyak menu,
# dan satu menu boleh punya banyak add-on.
# [OOP: Encapsulation] Data add-on dan perilakunya (is_usable, extra_price, dapatkan_status)
# dibungkus dalam satu class.
class AddOn(MenuPriceModifier):
    """Tambahan opsional yang bisa dipasang pada satu atau lebih item menu."""

    menu_items = models.ManyToManyField(
        MenuItem,
        related_name="allowed_addons",
        blank=True,
    )
    name = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    is_active = models.BooleanField(default=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # [OOP: Encapsulation] Nested class Meta membungkus index dan constraint tabel.
    class Meta:
        indexes = [models.Index(fields=["is_active", "is_available"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=0),
                name="addon_price_nonnegative",
            )
        ]

    # [OOP: Polymorphism] Override is_usable(): add-on bisa dipakai bila aktif DAN tersedia.
    def is_usable(self):
        return self.is_active and self.is_available

    # [OOP: Polymorphism] Override extra_price(): untuk add-on, tambahan harganya adalah price.
    def extra_price(self):
        return self.price

    # [OOP: Abstraction] Pemanggil cukup memanggil dapatkan_status() untuk mendapat teks
    # "Tersedia"/"Sedang Kosong" tanpa perlu tahu logika is_available di baliknya.
    # Method ini sengaja mempertahankan teks dan aturan lama (hanya melihat is_available),
    # sehingga kode lain yang sudah memakainya tidak berubah perilakunya.
    def dapatkan_status(self):
        return "Tersedia" if self.is_available else "Sedang Kosong"

    # [OOP: Polymorphism] __str__ di-override agar tampil sebagai nama add-on.
    def __str__(self):
        return self.name