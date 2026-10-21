# Modul 1. Pengantar OOP, class, dan object

[Kembali ke indeks OOP](README.md) · Acuan: **Modul 1 Pengantar OOP, Class, dan Object.pdf**, halaman PDF 2–13.

## Gambaran awal

Bayangkan daftar menu restoran. Nama, harga, dan ketersediaan suatu menu saling berkaitan. Class mengelompokkan data itu dengan perilaku yang relevan. Object adalah satu wujudnya, misalnya satu menu Ayam Geprek. Dua object dari class yang sama dapat memiliki data berbeda.

## Istilah yang perlu dipahami

| Istilah | Arti dalam pembelajaran ini |
|---|---|
| Class | Rancangan data dan perilaku, ditulis dengan class. |
| Object atau instance | Satu hasil pembuatan class. Variabel menyimpan referensi ke object itu. |
| Atribut | Data milik object, seperti nama atau harga. |
| Method | Pekerjaan yang disediakan class. |
| __init__ dan self | __init__ mengisi keadaan awal. self merujuk object yang sedang digunakan. |

## Lima kasus dari file proyek

### Kasus 1. Dua menu, satu rancangan

**File:** [`menu/models.py`](../../menu/models.py#L48)

**Class/method:** `MenuItem`.

**Situasi:** Restoran mempunyai Ayam Geprek dan Es Jeruk. Nama dan harganya berbeda, tetapi struktur datanya sama.

**Urutan membaca kode:**

1. Cari class MenuItem(models.Model).
2. Perhatikan name, price, category, dan is_available.
3. Bedakan class MenuItem dengan object hasil MenuItem(...) atau hasil pembacaan database.
4. Baca __str__: representasi teks object memakai nama menu.

**Hasil dan batasnya:** Perubahan pada satu object menu tidak otomatis mengubah object menu lain. Pembuatan MenuItem(...) saja belum menyimpan baris ke database.

**Hubungan dengan materi:** Class adalah pola bersama. Object menyimpan nilai masing-masing. Field Django di badan class dikelola oleh framework, bukan sekadar variabel kelas Python biasa.

### Kasus 2. Dua pelanggan mempunyai budget berbeda

**File:** [`recommendation/services/budget.py`](../../recommendation/services/budget.py#L14)

**Class/method:** `BudgetConstraint`.

**Situasi:** Pelanggan A membatasi harga Rp10.000, sedangkan pelanggan B Rp20.000.

**Urutan membaca kode:**

1. Baca __init__ dan parameter maximum.
2. Telusuri penyimpanan nilai ke __maximum.
3. Lihat property maximum, lalu method allows.
4. Bandingkan pemeriksaan harga Rp15.000 pada dua object budget.

**Hasil dan batasnya:** Dengan batas inklusif, object A menolak Rp15.000 dan object B menerima. Angka ini ilustrasi pembelajaran, bukan pembacaan harga katalog.

**Hubungan dengan materi:** Satu class menghasilkan object dengan keadaan berbeda. self.maximum pada allows merujuk batas milik object pemanggil.

### Kasus 3. Keranjang mengikuti sesi pelanggan

**File:** [`cart/services.py`](../../cart/services.py#L17)

**Class/method:** `CartService`.

**Situasi:** Dua pelanggan membuka web. Isi keranjang mereka harus mengikuti sesi masing-masing.

**Urutan membaca kode:**

1. Baca __init__(session).
2. Temukan self.session dan salinan data pada self._lines.
3. Ikuti add_item sampai _save.
4. Perhatikan bahwa _save menulis ke sesi yang dipegang object itu.

**Hasil dan batasnya:** Dua CartService dengan sesi berbeda bekerja pada data berbeda. Dua object yang sengaja diberi sesi sama tetap dapat mengacu ke penyimpanan yang sama.

**Hubungan dengan materi:** Object layanan juga termasuk OOP, walaupun bukan benda fisik. Identitas sesi yang diberikan memengaruhi keadaan object.

### Kasus 4. Satu tambahan menu menyimpan statusnya

**File:** [`menu/models.py`](../../menu/models.py#L168)

**Class/method:** `AddOn`.

**Situasi:** Tambahan susu tersedia hari ini, tetapi tambahan lain sedang kosong.

**Urutan membaca kode:**

1. Cari class AddOn.
2. Baca atribut is_available.
3. Baca dapatkan_status().
4. Hubungkan self.is_available dengan teks hasil method.

**Hasil dan batasnya:** dapatkan_status() menghasilkan Tersedia atau Sedang Kosong sesuai object. Method tersebut membaca status, bukan memeriksa atau mengurangi stok secara otomatis.

**Hubungan dengan materi:** Atribut menyatakan keadaan. Method menggunakan keadaan itu untuk menghasilkan perilaku yang bermakna bagi pemakai.

### Kasus 5. Keputusan akses melekat pada pengguna yang diperiksa

**File:** [`users/access.py`](../../users/access.py#L6)

**Class/method:** `StaffAccess`.

**Situasi:** Halaman staf dan kasir memerlukan keputusan akses yang berbeda.

**Urutan membaca kode:**

1. Baca __init__(user) dan self._user.
2. Baca can_manage_catalog dan is_cashier.
3. Lanjutkan ke can_use_cashier dan home_route.
4. Bedakan object StaffAccess dengan object user yang diperiksanya.

**Hasil dan batasnya:** Hasil pemeriksaan mengikuti autentikasi, status staf, dan grup Cashier. Membuat StaffAccess tidak mengubah pengguna menjadi staf.

**Hubungan dengan materi:** Object dapat membungkus pekerjaan pemeriksaan. Satu object memakai object lain tanpa menjadi turunan dari class object tersebut.

## Pertanyaan untuk diskusi

Coba jelaskan perbedaan MenuItem, sebuah object menu, dan variabel yang menunjuk object itu. Mengapa dua CartService belum tentu berarti dua keranjang berbeda?

## Cara memakai contoh ini

Tautan menunjuk kode proyek, bukan class latihan yang dibuat seolah-olah sudah ada. Nomor baris membantu pencarian pada versi yang diperiksa dan dapat bergeser setelah perubahan. Untuk kasus yang melibatkan database, sesi, penyimpanan, atau Gemini, telusuri kode terlebih dahulu. Gunakan database latihan terpisah bila ingin menjalankan operasi yang mengubah data.
