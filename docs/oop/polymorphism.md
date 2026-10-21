# Modul 6. Polimorfisme dan abstraksi

[Kembali ke indeks OOP](README.md) · Acuan: **Modul 6 Polimorfisme & Abstraksi-1.pdf**, halaman PDF 2–19.

## Gambaran awal

Polimorfisme berarti pemanggilan yang sama dapat menjalankan implementasi berbeda menurut object. Abstraksi menetapkan kemampuan yang perlu diketahui pemanggil. Di Python, ABC dapat menegakkan sebagian kontrak saat object dibuat; kesesuaian isi hasil tetap perlu diperiksa.

## Istilah yang perlu dipahami

| Istilah | Arti dalam pembelajaran ini |
|---|---|
| Dynamic dispatch | Python memilih implementasi method berdasarkan object saat program berjalan. |
| Duck typing | Pemanggil dapat memakai object yang memiliki kemampuan sesuai tanpa wajib satu hierarki; tetap ikuti kontrak pemakai. |
| ABC dan abstractmethod | Class abstrak menyatakan method yang wajib diimplementasikan turunan konkret. |
| Operator overloading | Method khusus seperti __eq__ menentukan perilaku operator. |
| Overloading parameter | Default argument bukan beberapa method bernama sama seperti overloading Java. Penulisan def dengan nama sama akan mengganti definisi sebelumnya. |

## Lima kasus dari file proyek

### Kasus 1. Kontrak pembuat teks dinyatakan dengan ABC

**File:** [`recommendation/services/text_generator.py`](../../recommendation/services/text_generator.py#L6)

**Class/method:** `TextGenerator`.

**Situasi:** Komponen pembuat penjelasan membutuhkan teks, tanpa mengetahui detail SDK atau jaringan.

**Urutan membaca kode:**

1. Baca class TextGenerator(ABC).
2. Temukan @abstractmethod pada generate.
3. Baca janji hasil str atau None.
4. Bandingkan generate_ranking yang mempunyai implementasi bawaan.

**Hasil dan batasnya:** TextGenerator tidak dapat dibuat langsung karena generate masih abstrak. ABC tidak otomatis membuktikan hasil turunan benar atau bebas kesalahan jaringan.

**Hubungan dengan materi:** Abstraksi menetapkan pekerjaan pokok. Tidak semua method pada ABC harus abstrak; generate_ranking dapat menggunakan generate sebagai perilaku bawaan.

### Kasus 2. Pemanggilan generate menjalankan implementasi berbeda

**File:** [`recommendation/services/ai/turn_generator.py`](../../recommendation/services/ai/turn_generator.py#L63)

**Class/method:** `TurnGenerator.generate`.

**Situasi:** Pemanggil umum menerima pembuat teks, sementara cara menghasilkannya dapat berbeda.

**Urutan membaca kode:**

1. Bandingkan generate pada GeminiClient dan TurnGenerator.
2. Pada GeminiClient, ikuti ke _generate miliknya.
3. Pada TurnGenerator, ikuti pemeriksaan reservasi sebelum provider dipanggil.
4. Baca pemakaian gemini_client.generate pada RecommendationExplanationService di ai/explanations.py.

**Hasil dan batasnya:** Nama pemanggilan generate tetap sama, tetapi object menentukan alurnya. Provider dapat menghasilkan teks atau None sesuai kontrak.

**Hubungan dengan materi:** Ini polimorfisme melalui inheritance. Pemanggil tidak perlu menyalin seluruh rincian kedua implementasi. Jalur AI-first dengan converse mempunyai kebutuhan yang lebih luas.

### Kasus 3. str memilih representasi tiap model

**File:** [`menu/models.py`](../../menu/models.py#L68)

**Class/method:** `MenuItem.__str__`.

**Situasi:** Tampilan pengelolaan perlu menampilkan object menu, tag, dan grup varian sebagai teks yang berguna.

**Urutan membaca kode:**

1. Baca __str__ pada MenuItem.
2. Bandingkan dengan MenuTag.__str__.
3. Bandingkan dengan VariantGroup.__str__.
4. Perhatikan str(object) memakai implementasi milik class object tersebut.

**Hasil dan batasnya:** Menu menampilkan nama, tag memilih display_name atau name, sedangkan grup varian menyertakan menu dan nama grup. Semuanya tetap menghasilkan str.

**Hubungan dengan materi:** Satu operasi bawaan bekerja pada beberapa jenis object melalui method khusus. Ini lebih konkret daripada hanya menyatakan bahwa semua model punya banyak method.

### Kasus 4. Kesamaan budget ditentukan dari isinya

**File:** [`recommendation/services/budget.py`](../../recommendation/services/budget.py#L107)

**Class/method:** `BudgetConstraint.__eq__`.

**Situasi:** Dua object budget dibuat terpisah, tetapi dapat mewakili batas yang sama.

**Urutan membaca kode:**

1. Baca __eq__.
2. Perhatikan pemeriksaan isinstance.
3. Lihat pembandingan minimum, maksimum, dan kedua flag inklusif.
4. Bedakan operator == dengan is.

**Hasil dan batasnya:** Dua object dengan isi batas dan flag sama dapat menghasilkan True pada ==, meskipun is bernilai False. Batas sama dengan flag inklusif berbeda tidak dianggap sama.

**Hubungan dengan materi:** Operator overloading pada __eq__ memberi makna kesamaan nilai. Object baru tidak otomatis identik hanya karena datanya setara.

### Kasus 5. Pemanggilan widget memakai implementasi khusus

**File:** [`menu/widgets.py`](../../menu/widgets.py#L12)

**Class/method:** `MenuPhotoWidget.get_context`.

**Situasi:** Django merender berbagai input form melalui kemampuan widget yang sama.

**Urutan membaca kode:**

1. Baca get_context pada MenuPhotoWidget.
2. Perhatikan parameter name, value, attrs.
3. Ikuti pemanggilan implementasi induk melalui super.
4. Lihat hasil dictionary yang ditambah photo_url dan dikembalikan.

**Hasil dan batasnya:** Ketika widget yang dipakai adalah MenuPhotoWidget, pemanggilan get_context menjalankan versi khusus itu sambil mempertahankan struktur dasar Django.

**Hubungan dengan materi:** Inheritance adalah hubungan class-nya. Polimorfisme adalah perilaku saat antarmuka yang sama dipanggil pada widget tertentu.

## Membaca perbedaan konsep

| Konsep | Pertanyaan yang dijawab | Contoh |
|---|---|---|
| Inheritance | Siapa induk class ini? | GeminiClient adalah TextGenerator. |
| Abstraksi | Kemampuan apa yang dijanjikan? | generate menghasilkan str atau None. |
| Polimorfisme | Implementasi mana yang berjalan? | generate milik object konkret yang diterima. |
| Duck typing | Apakah kemampuan yang diperlukan tersedia? | Object bantuan tetap harus memenuhi semua method yang dipanggil pemakai. |

Tidak semua class proyek mempunyai __add__, __len__, atau multiple inheritance
buatan sendiri. Contoh operator yang nyata di sini adalah __eq__. Jangan menulis
fitur baru hanya supaya semua ilustrasi di PDF terlihat ada dalam aplikasi.

Baca juga [catatan abstraksi](abstraction.md) untuk membedakan kontrak generate
dengan percakapan AI-first melalui converse.

## Pertanyaan untuk diskusi

Mengapa ABC tidak cukup untuk memastikan teks AI benar? Apa beda override get_context dengan polimorfisme saat Django memanggilnya?

## Cara memakai contoh ini

Tautan menunjuk kode proyek, bukan class latihan yang dibuat seolah-olah sudah ada. Nomor baris membantu pencarian pada versi yang diperiksa dan dapat bergeser setelah perubahan. Untuk kasus yang melibatkan database, sesi, penyimpanan, atau Gemini, telusuri kode terlebih dahulu. Gunakan database latihan terpisah bila ingin menjalankan operasi yang mengubah data.
