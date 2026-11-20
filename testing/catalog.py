"""Showcase catalog data. Plain data only; testing/seeding.py writes it to the database."""
from dataclasses import dataclass


@dataclass(frozen=True)
class VariantSpec:
    name: str
    options: tuple[tuple[str, int], ...]  # (option name, price adjustment)
    required: bool = True


@dataclass(frozen=True)
class MenuSpec:
    name: str
    category: str
    price: int
    svg: str = ""  # file in testing/svg/; empty = no photo (placeholder)
    description: str = ""
    tags: tuple[str, ...] = ()
    variants: tuple[VariantSpec, ...] = ()
    addons: tuple[str, ...] = ()
    available: bool = True


SPICE = VariantSpec("Tingkat pedas", (("Tidak pedas", 0), ("Sedang", 0), ("Pedas", 0), ("Extra pedas", 2000)))
PORTION = VariantSpec("Porsi", (("Reguler", 0), ("Jumbo", 6000)))
TEMPERATURE = VariantSpec("Suhu", (("Dingin", 0), ("Hangat", 0)))
SUGAR = VariantSpec("Gula", (("Normal", 0), ("Kurang manis", 0), ("Tanpa gula", 0)), required=False)

ADDONS: dict[str, int] = {
    "Telur ceplok": 4000,
    "Nasi tambahan": 5000,
    "Kerupuk": 2000,
    "Sambal ekstra": 2000,
    "Keju parut": 5000,
    "Boba": 4000,
    "Es krim vanila": 6000,
}

CATEGORIES = ("Makanan", "Minuman", "Camilan", "Penutup")

TABLES = tuple(str(number) for number in range(1, 9))

MENU: tuple[MenuSpec, ...] = (
    # --- Normal catalog: transparent cut-out artwork ---
    MenuSpec("Nasi Goreng Spesial", "Makanan", 22000, "nasi-goreng.svg",
             "Nasi goreng kecap dengan telur, ayam suwir, dan acar.",
             ("rice", "fried_rice", "savory", "egg", "filling", "heavy_meal", "comfort_food"),
             (SPICE, PORTION), ("Telur ceplok", "Kerupuk", "Sambal ekstra")),
    MenuSpec("Mie Goreng Jawa", "Makanan", 20000, "mie-goreng.svg",
             "Mie goreng bumbu jawa dengan sayur dan bakso.",
             ("noodle", "fried_noodle", "savory", "umami", "filling", "heavy_meal"),
             (SPICE, PORTION), ("Telur ceplok", "Kerupuk")),
    MenuSpec("Ayam Bakar Madu", "Makanan", 28000, "ayam-bakar.svg",
             "Ayam bakar olesan madu, nasi putih, lalapan, dan sambal.",
             ("chicken", "rice", "sweet", "savory", "heavy_meal", "satisfying"),
             (SPICE,), ("Nasi tambahan", "Sambal ekstra")),
    MenuSpec("Soto Ayam Lamongan", "Makanan", 21000, "soto-ayam.svg",
             "Kuah kuning gurih dengan koya, telur, dan soun.",
             ("chicken", "soup", "brothy", "warming", "comfort_food", "breakfast"),
             (), ("Nasi tambahan", "Kerupuk")),
    MenuSpec("Gado-Gado", "Makanan", 18000, "gado-gado.svg",
             "Sayur rebus, tahu, tempe, lontong, siram saus kacang.",
             ("tofu", "tempeh", "savory", "mild", "light_meal"),
             (SPICE,), ("Kerupuk",)),
    MenuSpec("Sate Ayam Madura", "Makanan", 25000, "sate-ayam.svg",
             "Sepuluh tusuk sate ayam dengan bumbu kacang dan lontong.",
             ("chicken", "savory", "sweet", "sharing", "satisfying"),
             (), ("Nasi tambahan",)),
    MenuSpec("Pisang Goreng Keju", "Camilan", 15000, "pisang-goreng.svg",
             "Pisang kepok goreng renyah dengan keju dan susu kental manis.",
             ("snack", "sweet", "crispy", "sharing"),
             (), ("Keju parut", "Es krim vanila")),
    MenuSpec("Es Jeruk Peras", "Minuman", 10000, "es-jeruk.svg",
             "Jeruk peras segar.",
             ("drink", "sour", "refreshing", "cold"),
             (TEMPERATURE, SUGAR)),
    MenuSpec("Es Teh Manis", "Minuman", 6000, "es-teh.svg",
             "Teh melati seduh, manis pas.",
             ("drink", "sweet", "refreshing", "cold"),
             (TEMPERATURE, SUGAR), ("Boba",)),
    MenuSpec("Kopi Susu Gula Aren", "Minuman", 18000, "kopi-susu.svg",
             "Espresso, susu segar, dan gula aren.",
             ("drink", "sweet", "creamy", "late_night"),
             (TEMPERATURE, SUGAR), ("Boba",)),
    MenuSpec("Es Campur", "Penutup", 16000, "es-campur.svg",
             "Serutan es, buah, cincau, kolang-kaling, dan sirup merah.",
             ("dessert", "sweet", "refreshing", "cold"),
             (), ("Es krim vanila",)),

    # --- Edge cases: check the card layout with awkward images and data ---
    MenuSpec("Nasi Campur Bali", "Makanan", 32000, "edge-photo-landscape.svg",
             "Foto buram (tanpa latar transparan), lanskap 16:10.",
             ("rice", "chicken", "spicy", "filling", "heavy_meal"), (SPICE,)),
    MenuSpec("Rawon Daging", "Makanan", 30000, "edge-photo-portrait.svg",
             "Foto buram potret 9:16.",
             ("soup", "brothy", "warming", "heavy_meal")),
    MenuSpec("Tahu Tempe Penyet", "Makanan", 16000, "edge-panorama.svg",
             "Gambar panorama sangat lebar (4:1).",
             ("tofu", "tempeh", "spicy", "light_meal"), (SPICE,)),
    MenuSpec("Es Teler Jumbo", "Penutup", 20000, "edge-very-tall.svg",
             "Gambar sangat tinggi (1:4).",
             ("dessert", "sweet", "cold")),
    MenuSpec("Bakwan Sayur", "Camilan", 9000, "edge-viewbox-only.svg",
             "SVG tanpa atribut width/height (hanya viewBox).",
             ("snack", "crispy", "savory")),
    MenuSpec("Tempe Mendoan", "Camilan", 8000, "",
             "Tanpa foto: kartu harus menampilkan placeholder.",
             ("snack", "tempeh", "savory", "crispy")),
    MenuSpec("Paket Nasi Liwet Komplit Ayam Goreng Kremes Sambal Terasi Lalapan dan Tahu Tempe", "Makanan",
             1250000, "nasi-goreng.svg",
             "Nama sangat panjang dan harga tujuh digit untuk menguji pemotongan teks. " * 3,
             ("rice", "chicken", "sharing", "filling", "heavy_meal"), (SPICE, PORTION),
             tuple(ADDONS)),
    MenuSpec("Martabak Manis", "Camilan", 35000, "pisang-goreng.svg",
             "Stok habis: tidak boleh muncul di menu pelanggan.",
             ("snack", "sweet", "sharing"), available=False),
)
