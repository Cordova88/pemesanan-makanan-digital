# Modul 2. Atribut dan method

[Kembali ke indeks OOP](README.md) · Acuan: **Modul 2 Atribut dan Method.pdf**, halaman PDF 2–11.

## Gambaran awal

Setelah mengenal object, pelajari siapa pemilik datanya dan bagaimana pekerjaannya dipanggil. Data per pelanggan cocok menjadi atribut instance. Aturan bersama dapat menjadi atribut kelas. Method dipilih menurut kebutuhannya terhadap object atau class.

## Istilah yang perlu dipahami

| Istilah | Arti dalam pembelajaran ini |
|---|---|
| Atribut instance | Biasanya diisi melalui self; nilainya milik masing-masing object. |
| Atribut kelas | Diletakkan di badan class; dapat menjadi konstanta bersama. |
| Instance method | Menerima self dan bekerja dengan keadaan object. |
| Class method | Memakai @classmethod dan menerima cls; sering menjadi pembuat object alternatif. |
| Static method | Memakai @staticmethod; tidak menerima self atau cls secara otomatis. |

## Lima kasus dari file proyek

### Kasus 1. Nama tempat penyimpanan bersama, isi keranjang berbeda

**File:** [`cart/services.py`](../../cart/services.py#L17)

**Class/method:** `CartService`.

**Situasi:** Semua keranjang memakai nama kunci cart, tetapi isinya tidak boleh dibagikan sebagai satu list kelas.

**Urutan membaca kode:**

1. Cari SESSION_KEY: ClassVar[str] = "cart".
2. Bandingkan dengan self.session dan self._lines di __init__.
3. Lihat pemakaian self.SESSION_KEY di _save.
4. Perhatikan deepcopy saat membaca dan menyimpan list.

**Hasil dan batasnya:** SESSION_KEY adalah aturan nama bersama. _lines adalah keadaan object. ClassVar membantu pembaca dan pemeriksa tipe; ia bukan pengunci nilai saat program berjalan.

**Hubungan dengan materi:** Ini contoh langsung perbedaan atribut kelas dengan atribut instance. List mutable sebagai atribut kelas bisa menyebabkan data tidak sengaja terbagi.

### Kasus 2. Mengosongkan satu keranjang melalui instance method

**File:** [`cart/services.py`](../../cart/services.py#L150)

**Class/method:** `CartService.clear`.

**Situasi:** Pelanggan ingin mengosongkan keranjangnya sendiri.

**Urutan membaca kode:**

1. Baca clear(self).
2. Temukan self._lines = [].
3. Ikuti self._save().
4. Lihat sesi mana yang menerima perubahan.

**Hasil dan batasnya:** clear mengubah keadaan object dan menyimpannya ke sesi terkait. Operasi ini mengubah data, jadi cukup telusuri kode ketika memakai data restoran bersama.

**Hubungan dengan materi:** clear memerlukan self karena harus mengetahui keranjang mana yang diubah. Ini bukan pekerjaan stateless yang cocok dijadikan static method.

### Kasus 3. Membuat object budget dari dictionary

**File:** [`recommendation/services/budget.py`](../../recommendation/services/budget.py#L82)

**Class/method:** `BudgetConstraint.from_dict`.

**Situasi:** Batas harga tersimpan sebagai data sederhana. Program perlu membacanya menjadi object yang mempunyai method allows.

**Urutan membaca kode:**

1. Cari @classmethod sebelum from_dict.
2. Perhatikan parameter cls dan pemeriksaan field.
3. Lihat konversi angka teks menjadi Decimal.
4. Ikuti return cls(...) menuju __init__.

**Hasil dan batasnya:** Data yang lolos pemeriksaan menjadi BudgetConstraint baru. Data dengan tipe atau batas tidak sah ditolak. Method ini tidak mengubah budget object lain.

**Hubungan dengan materi:** Class method berfungsi sebagai jalur pembuatan object alternatif. cls adalah class yang dipakai membuat object, bukan satu instance tertentu.

### Kasus 4. Menormalkan alias tanpa membuat object

**File:** [`menu/models.py`](../../menu/models.py#L107)

**Class/method:** `MenuItemAlias.normalize_phrase`.

**Situasi:** Alias dengan kapital dan spasi berbeda perlu dibaca sebagai bentuk yang konsisten.

**Urutan membaca kode:**

1. Cari @staticmethod sebelum normalize_phrase.
2. Baca parameter value.
3. Telusuri casefold, split, lalu join.
4. Lihat clean menggunakan hasil normalisasi tersebut.

**Hasil dan batasnya:** Misalnya teks dengan spasi berlebih dinormalkan dan huruf diseragamkan. Fungsi ini sendiri tidak mencari menu atau menyimpan alias ke database.

**Hubungan dengan materi:** Pekerjaan hanya membutuhkan input value sehingga tidak memerlukan self atau cls. Penempatannya di MenuItemAlias menunjukkan kaitan tanggung jawabnya.

### Kasus 5. Membaca property berbeda dari memanggil method

**File:** [`menu/selection.py`](../../menu/selection.py#L33)

**Class/method:** `MenuSelection`.

**Situasi:** Program memerlukan harga satuan dan total untuk jumlah porsi tertentu.

**Urutan membaca kode:**

1. Cari @property sebelum unit_price.
2. Baca total_price(self, quantity).
3. Bandingkan selection.unit_price dengan selection.total_price(2).
4. Lihat validasi jumlah pada total_price.

**Hasil dan batasnya:** Harga satuan menjumlahkan harga menu, opsi, dan tambahan. Total mengalikan harga satuan dengan jumlah valid 1–99.

**Hubungan dengan materi:** Property dipakai seperti atribut tanpa tanda kurung, tetapi dapat menjalankan perhitungan. Method biasa dapat menerima parameter tambahan seperti quantity.

## Pertanyaan untuk diskusi

Kapan from_dict lebih sesuai daripada static method? Mengapa unit_price tidak dibaca dengan unit_price()?

## Cara memakai contoh ini

Tautan menunjuk kode proyek, bukan class latihan yang dibuat seolah-olah sudah ada. Nomor baris membantu pencarian pada versi yang diperiksa dan dapat bergeser setelah perubahan. Untuk kasus yang melibatkan database, sesi, penyimpanan, atau Gemini, telusuri kode terlebih dahulu. Gunakan database latihan terpisah bila ingin menjalankan operasi yang mengubah data.
