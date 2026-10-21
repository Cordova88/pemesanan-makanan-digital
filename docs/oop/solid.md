# Modul 7. Lima prinsip SOLID

[Kembali ke indeks OOP](README.md) · Acuan: **Modul 7 - Prinsip SOLID.pdf**, halaman PDF 2–15.

## Gambaran awal

SOLID membantu menilai apakah perubahan dapat dikerjakan tanpa mengacaukan bagian lain. Lima kasus di bawah masing-masing membahas satu prinsip. Statusnya contoh penerapan dan batas yang terlihat dari kode, bukan pernyataan bahwa seluruh proyek sudah sempurna.

## Istilah yang perlu dipahami

| Istilah | Arti dalam pembelajaran ini |
|---|---|
| SRP | Satu class memiliki satu kelompok tanggung jawab atau alasan utama untuk berubah. |
| OCP | Kemampuan dapat diperluas tanpa terus membongkar pemanggil yang sudah sesuai kontrak. |
| LSP | Turunan dapat menggantikan induk sambil menepati janji perilakunya. |
| ISP | Pemakai tidak dipaksa bergantung pada kemampuan yang tidak diperlukannya. |
| DIP | Aturan tingkat tinggi bergantung pada abstraksi; alat konkret dapat diberikan dari luar. |

## Lima kasus dari file proyek

### Kasus 1. SRP: aturan pilihan menu mempunyai tempat tersendiri

**File:** [`menu/selection.py`](../../menu/selection.py#L33)

**Class/method:** `MenuSelection`.

**Situasi:** Keranjang dan pembuatan pesanan sama-sama perlu memeriksa opsi dan menghitung harga pilihan.

**Urutan membaca kode:**

1. Baca from_ids, unit_price, dan total_price pada MenuSelection.
2. Temukan pemakaiannya di cart/services.py.
3. Temukan pemakaiannya di orders/services.py.
4. Bedakan validasi pilihan dari penyimpanan sesi dan transaksi pesanan.

**Hasil dan batasnya:** Aturan pilihan dapat ditelusuri di satu class. orders/services.py berisi fungsi layanan transaksi, bukan class bernama OrderService.

**Hubungan dengan materi:** Alasan perubahan MenuSelection berkaitan dengan pilihan dan harga. Ini mendukung SRP, tetapi tidak berarti seluruh kode perhitungan proyek sudah bebas pengulangan.

### Kasus 2. OCP: pemakai kontrak generate dapat menerima implementasi lain

**File:** [`recommendation/services/text_generator.py`](../../recommendation/services/text_generator.py#L6)

**Class/method:** `TextGenerator`.

**Situasi:** Penjelasan rekomendasi perlu diuji atau menggunakan pembuat teks lain tanpa mengubah setiap pemanggilan generate.

**Urutan membaca kode:**

1. Baca kontrak generate.
2. Buka constructor RecommendationExplanationService di ai/explanations.py.
3. Lihat parameter gemini_client: TextGenerator | None.
4. Telusuri pemanggilan generate melalui object yang diterima.

**Hasil dan batasnya:** Pemakai kontrak sempit dapat menerima implementasi lain yang sesuai. Ini peluang perluasan yang sudah tersedia pada kode, bukan provider baru yang telah dipasang.

**Hubungan dengan materi:** OCP berlaku pada batas kontrak itu. AI-first memakai converse dan tool, sehingga tidak otomatis dapat diganti dengan sembarang implementasi generate saja.

### Kasus 3. LSP: None adalah hasil yang sah, bukan pelanggaran kontrak

**File:** [`recommendation/services/gemini.py`](../../recommendation/services/gemini.py#L63)

**Class/method:** `GeminiClient.generate`.

**Situasi:** Provider dapat tidak tersedia, tetapi pemanggil tidak seharusnya menerima tipe hasil yang sama sekali berbeda dari janji induk.

**Urutan membaca kode:**

1. Baca str | None pada TextGenerator.generate.
2. Bandingkan GeminiClient.generate.
3. Baca TurnGenerator.generate dan penanganan kegagalan di _generate.
4. Temukan pemeriksaan hasil pada pemakai pembuat penjelasan.

**Hasil dan batasnya:** Mengembalikan None ketika tidak tersedia sesuai kontrak. Mengembalikan dictionary tanpa mengubah kontrak pemakai akan berpotensi merusak penggantian object.

**Hubungan dengan materi:** LSP berbicara tentang perilaku yang dijanjikan, bukan sekadar nama method sama. Reservasi TurnGenerator juga harus dipahami oleh pemakai yang memilih wrapper tersebut.

### Kasus 4. ISP: kontrak dasar kecil, kemampuan AI-first terpisah

**File:** [`recommendation/services/text_generator.py`](../../recommendation/services/text_generator.py#L6)

**Class/method:** `TextGenerator`.

**Situasi:** Pembuat teks biasa tidak selalu mendukung percakapan dengan tool katalog.

**Urutan membaca kode:**

1. Baca generate dan generate_ranking pada TextGenerator.
2. Bandingkan dengan converse pada GeminiClient.
3. Buka GeminiAssistant.respond di ai/assistant.py.
4. Perhatikan assistant memanggil converse, yang bukan bagian kontrak TextGenerator.

**Hasil dan batasnya:** Kontrak dasar tidak memaksa semua turunan membuat converse palsu. Namun AI-first masih memiliki ketergantungan tambahan yang perlu diperhatikan ketika mengganti provider.

**Hubungan dengan materi:** Ini contoh manfaat antarmuka kecil sekaligus batas desain sekarang. Belum ada ABC khusus percakapan tool; jangan mengklaim pemisahan interface sudah lengkap.

### Kasus 5. DIP: alat pembuat penjelasan dapat diberikan dari luar

**File:** [`recommendation/services/ai/explanations.py`](../../recommendation/services/ai/explanations.py#L74)

**Class/method:** `RecommendationExplanationService.__init__`.

**Situasi:** Layanan penjelasan perlu memakai generator yang sesuai tanpa selalu terkunci pada pembuatan satu alat konkret di setiap pemanggil.

**Urutan membaca kode:**

1. Baca parameter gemini_client pada __init__.
2. Perhatikan pemakaian object dari parameter jika tersedia.
3. Lihat GeminiClient() hanya sebagai pilihan bawaan saat parameter None.
4. Bandingkan dengan ChatbotService yang juga menerima gemini_client.

**Hasil dan batasnya:** Pemberian dependency memungkinkan pemakai kontrak generate menerima object lain. Object uji dan provider baru tetap harus memenuhi kebutuhan nyata setiap pemanggil.

**Hubungan dengan materi:** Dependency injection terlihat dari parameter constructor. DIP didukung oleh kontrak TextGenerator, tetapi belum murni karena class masih mengimpor dan menyediakan GeminiClient sebagai default.

## Pertanyaan untuk diskusi

Mengapa menerima parameter generator belum membuktikan DIP sempurna? Mengapa kontrak generate tidak cukup untuk mengganti provider pada AI-first?

## Cara memakai contoh ini

Tautan menunjuk kode proyek, bukan class latihan yang dibuat seolah-olah sudah ada. Nomor baris membantu pencarian pada versi yang diperiksa dan dapat bergeser setelah perubahan. Untuk kasus yang melibatkan database, sesi, penyimpanan, atau Gemini, telusuri kode terlebih dahulu. Gunakan database latihan terpisah bila ingin menjalankan operasi yang mengubah data.
