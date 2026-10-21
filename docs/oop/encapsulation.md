# Modul 3. Enkapsulasi

[Kembali ke indeks OOP](README.md) · Acuan: **Modul 3 Encapsulation.pdf**, halaman PDF 2–7.

## Gambaran awal

Enkapsulasi mengarahkan pembacaan dan perubahan data melalui jalur yang jelas. Tujuannya membantu menjaga aturan object, bukan menjadikan atribut sebagai tempat penyimpanan rahasia.

## Istilah yang perlu dipahami

| Istilah | Arti dalam pembelajaran ini |
|---|---|
| Public | Nama tanpa awalan underscore menjadi bagian yang biasa dipakai pemanggil. |
| _internal | Satu underscore menyatakan penggunaan internal secara konvensi; akses tidak diblokir Python. |
| __private | Dua underscore memicu name mangling; tetap bukan perlindungan keamanan mutlak. |
| Property | Menyediakan cara membaca nilai dan, bila disediakan, setter untuk mengubahnya. |
| Validasi dan salinan | Pembatasan perubahan juga memerlukan pemeriksaan nilai dan pengelolaan referensi mutable. |

## Lima kasus dari file proyek

### Kasus 1. Batas harga tidak diganti sembarangan

**File:** [`recommendation/services/budget.py`](../../recommendation/services/budget.py#L14)

**Class/method:** `BudgetConstraint`.

**Situasi:** Budget minimum tidak boleh lebih besar dari maksimum.

**Urutan membaca kode:**

1. Baca validasi __init__.
2. Temukan penyimpanan __minimum dan __maximum.
3. Baca property minimum dan maximum.
4. Perhatikan tidak ada setter untuk kedua property itu.

**Hasil dan batasnya:** Pembuatan budget dengan minimum Rp20.000 dan maksimum Rp10.000 memunculkan ValueError. Untuk batas baru, buat object baru melalui jalur validasi.

**Hubungan dengan materi:** Data internal disimpan di atribut dengan name mangling dan dibaca melalui property. __slots__ membatasi atribut biasa yang tersedia, tetapi bukan mekanisme otorisasi.

### Kasus 2. Daftar pilihan dikembalikan sebagai tuple

**File:** [`menu/selection.py`](../../menu/selection.py#L33)

**Class/method:** `MenuSelection`.

**Situasi:** Daftar opsi dan tambahan perlu tetap sesuai pilihan yang sedang dihitung.

**Urutan membaca kode:**

1. Baca __init__ yang mengubah options dan addons menjadi tuple.
2. Temukan __options dan __addons.
3. Baca property options dan addons.
4. Lanjutkan ke from_ids untuk melihat jalur validasi ID.

**Hasil dan batasnya:** Pemanggil tidak dapat menambah anggota tuple dengan append. Namun object VariantOption atau AddOn di dalam tuple tetap object Django yang bisa berubah.

**Hubungan dengan materi:** Enkapsulasi koleksi bukan berarti seluruh isinya otomatis immutable. Memanggil constructor langsung juga tidak sama dengan melewati validasi database pada from_ids.

### Kasus 3. Keranjang mengembalikan salinan baris

**File:** [`cart/services.py`](../../cart/services.py#L35)

**Class/method:** `CartService.add_item`.

**Situasi:** Pemanggil menerima informasi baris keranjang, tetapi sebaiknya tidak mengubah list internal melalui referensi hasil.

**Urutan membaca kode:**

1. Baca atribut _lines.
2. Cari return deepcopy(line) pada add_item.
3. Baca checkout_items yang juga membuat salinan.
4. Untuk perubahan resmi, telusuri update_selection dan _save.

**Hasil dan batasnya:** Perubahan dictionary hasil salinan tidak langsung mengubah baris internal object keranjang. Update melalui method tetap memerlukan validasi dan penyimpanan.

**Hubungan dengan materi:** Enkapsulasi di sini menggunakan konvensi _ dan defensive copy. Perlindungannya tidak hanya berasal dari nama atribut.

### Kasus 4. Keputusan hak akses dibaca melalui property

**File:** [`users/access.py`](../../users/access.py#L6)

**Class/method:** `StaffAccess`.

**Situasi:** Tampilan perlu mengetahui boleh tidaknya pengguna membuka pengelolaan katalog.

**Urutan membaca kode:**

1. Cari _user di constructor.
2. Baca can_manage_catalog.
3. Baca is_cashier dan can_use_cashier.
4. Lihat bahwa property tidak menyediakan setter untuk memberikan hak baru.

**Hasil dan batasnya:** Keputusan selalu dihitung dari pengguna terkait. StaffAccess tidak menyembunyikan atau membekukan seluruh object pengguna, dan pemeriksaan server tetap diperlukan.

**Hubungan dengan materi:** Detail keputusan dibungkus dalam class dengan antarmuka baca yang jelas. _user tetap dapat diakses secara teknis karena underscore adalah konvensi.

### Kasus 5. Hasil perkiraan minimum mempunyai antarmuka baca

**File:** [`menu/selection.py`](../../menu/selection.py#L12)

**Class/method:** `MinimumQuote`.

**Situasi:** Program perlu membawa harga dasar, harga minimum, dan bukti kondisi katalog saat perkiraan dibuat.

**Urutan membaca kode:**

1. Baca __init__(base_price, minimum_payable, signature).
2. Temukan tiga atribut berawalan __.
3. Baca property base_price, minimum_payable, dan signature.
4. Lihat MenuSelection.minimum_quote sebagai pembuat object ini.

**Hasil dan batasnya:** Pemanggil dapat membaca ketiga informasi melalui property. Perkiraan minimum belum merupakan pilihan final pelanggan atau jaminan harga checkout tidak berubah.

**Hubungan dengan materi:** Class membungkus satu kelompok informasi yang berkaitan dan membatasi cara pembaca berinteraksi dengannya.

## Pertanyaan untuk diskusi

Mengapa _lines masih perlu deepcopy? Apakah tuple yang berisi object menu berarti semua data menu di dalamnya tidak bisa berubah?

## Cara memakai contoh ini

Tautan menunjuk kode proyek, bukan class latihan yang dibuat seolah-olah sudah ada. Nomor baris membantu pencarian pada versi yang diperiksa dan dapat bergeser setelah perubahan. Untuk kasus yang melibatkan database, sesi, penyimpanan, atau Gemini, telusuri kode terlebih dahulu. Gunakan database latihan terpisah bila ingin menjalankan operasi yang mengubah data.
