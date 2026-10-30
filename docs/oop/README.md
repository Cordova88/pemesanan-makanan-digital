# Panduan Belajar OOP dari Kode RasaKita

Materi ini ditujukan untuk anggota tim yang sedang belajar. Kita mulai dari masalah yang
terlihat pada web, lalu membuka kode yang mengerjakannya. Kamu tidak perlu menghafal semua
istilah sebelum mulai membaca.

OOP adalah singkatan dari pemrograman berorientasi object. Kita mengelompokkan data dan
pekerjaan yang berkaitan ke dalam class agar lebih mudah digunakan dan dipahami.

Ada **tujuh modul utama dengan 35 kasus**. Setiap modul memakai lima berkas utama berbeda.
Modul 8 dan 9 memperdalam pembahasan, sedangkan modul 10 berisi latihan. Contoh-contohnya
memakai class dan method yang benar-benar ada.

## Pegangan awal

- **Class** adalah rancangan data dan pekerjaan. Contohnya rancangan menu.
- **Object** adalah sesuatu yang dibuat dari class, misalnya satu menu nasi.
- **Atribut** adalah datanya, misalnya nama dan harga.
- **Method** adalah fungsi di dalam class, misalnya menghitung harga.
- **Parameter** adalah nilai yang diberikan ketika fungsi atau method dipanggil.
- **self** menunjuk object yang sedang dikerjakan oleh method.

- **None** berarti belum ada nilai atau hasil yang dapat dipakai.
- **True/False** berarti benar/salah.
- **List** adalah daftar data. **Dictionary** menyimpan pasangan nama dan nilai.
- **Tuple** adalah daftar yang anggotanya tidak ditambah atau dihapus seperti list.
- **Database** adalah tempat data aplikasi disimpan, misalnya katalog dan pesanan.

Jika bertemu istilah lain, lihat artinya pada awal modul. Nama kode tetap memakai penulisan
asli agar dapat dicari pada berkas proyek.

## Urutan membaca

| Modul | Yang dipelajari |
|---|---|
| [1. Class dan Object.md](1.%20Class%20dan%20Object.md) | Mengenal rancangan class, object yang dibuat, dan data masing-masing. |
| [2. Atribut dan Method.md](2.%20Atribut%20dan%20Method.md) | Membedakan data dengan pekerjaan, serta cara memanggil method. |
| [3. Enkapsulasi.md](3.%20Enkapsulasi.md) | Mengatur perubahan data supaya aturan tetap dipenuhi. |
| [4. Relasi Kelas dan UML.md](4.%20Relasi%20Kelas%20dan%20UML.md) | Menggambar siapa berhubungan dengan siapa dan berapa jumlahnya. |
| [5. Inheritance.md](5.%20Inheritance.md) | Memakai kemampuan class induk dan menambahkan kebutuhan turunan. |
| [6. Polimorfisme dan Abstraksi.md](6.%20Polimorfisme%20dan%20Abstraksi.md) | Memahami pemanggilan yang sama dengan pekerjaan yang berbeda. |
| [7. Prinsip SOLID.md](7.%20Prinsip%20SOLID.md) | Membaca lima prinsip agar kode lebih mudah diubah. |
| [8. Pendalaman Abstraksi.md](8.%20Pendalaman%20Abstraksi.md) | Memisahkan kemampuan yang diperlukan dari cara mengerjakannya. |
| [9. Pendalaman Komposisi.md](9.%20Pendalaman%20Komposisi.md) | Melihat kerja sama object tanpa memaksakan hubungan induk dan turunan. |
| [10. Latihan dan Presentasi.md](10.%20Latihan%20dan%20Presentasi.md) | Mencoba contoh sederhana dan berlatih menjelaskan satu kasus. |

Nama berkas diberi nomor 1 sampai 10. Jika pengelola file menampilkan nomor 10 setelah nomor 1,
tetap ikuti urutan tabel ini.

## Cara mengikuti satu kasus

1. Baca masalahnya. Bayangkan tindakan yang dilakukan pelanggan atau operator.
2. Buka tautan berkas dan cari class atau method yang disebutkan.
3. Ikuti langkah pembacaan di bawah potongan kode.
4. Cocokkan masukan dan hasil pada contohnya.
5. Baca alasan kasus itu menunjukkan konsep OOP yang dibahas.
6. Coba jawab pertanyaannya dengan kata sendiri.

Potongan kode panjang kadang hanya menampilkan bagian awal. Lanjutkan membaca berkas aslinya
jika ingin mengikuti seluruh method. Nama dan harga pada contoh adalah data latihan, bukan isi
katalog yang wajib ada di setiap laptop.

## Mulai mencari kode dari sini

| Berkas | Pekerjaannya |
|---|---|
| [menu/models.py](../../menu/models.py) | Menjelaskan data kategori, menu, tag, varian, dan tambahan. |
| [menu/selection.py](../../menu/selection.py) | Memeriksa pilihan dan menghitung harganya. |
| [cart/services.py](../../cart/services.py) | Mengubah dan menyimpan isi keranjang pada sesi browser. |
| [orders/models.py](../../orders/models.py) | Menjelaskan data pesanan dan baris makanan. |
| [orders/services.py](../../orders/services.py) | Menjalankan pembuatan pesanan, pembayaran, pembatalan, dan refund. |
| [users/access.py](../../users/access.py) | Memeriksa apakah pengguna boleh mengelola katalog atau memakai kasir. |
| [budget.py](../../recommendation/services/budget.py) | Menyimpan dan memeriksa batas harga. |
| [text_generator.py](../../recommendation/services/text_generator.py) | Menentukan kemampuan dasar pembuat teks. |
| [gemini.py](../../recommendation/services/gemini.py) | Menghubungi Gemini dan mencatat pemakaiannya. |
| [users/forms.py](../../users/forms.py) | Form manajemen CMS dan penataan styling Bootstrap otomatis. |
| [assistant.py](../../recommendation/services/ai/assistant.py) | Mengatur percakapan Gemini dan fungsi pencarian menu. |
| [chatbot.py](../../recommendation/services/chatbot.py) | Menghubungkan bagian-bagian percakapan. |
| [conversation_session.py](../../recommendation/services/conversation_session.py) | Mengelola data percakapan yang perlu diingat sementara. |
| [menu/forms.py](../../menu/forms.py) | Menyiapkan dan memeriksa form foto menu. |
| [menu/widgets.py](../../menu/widgets.py) | Menyiapkan tampilan input foto dan pratinjau. |

## Daftar 35 kasus beserta simbol sumber

### Modul 1: Class dan Object

1. [`MenuItem`](../../menu/models.py#L68) — `menu/models.py`.
2. [`BudgetConstraint`](../../recommendation/services/budget.py#L53) — `recommendation/services/budget.py`.
3. [`CartService`](../../cart/services.py#L25) — `cart/services.py`.
4. [`StaffAccess`](../../users/access.py#L18) — `users/access.py`.
5. [`MenuSelection`](../../menu/selection.py#L34) — `menu/selection.py`.

### Modul 2: Atribut dan Method

1. [`CartService`](../../cart/services.py#L20) — `cart/services.py`.
2. [`BudgetConstraint.from_dict`](../../recommendation/services/budget.py#L81) — `recommendation/services/budget.py`.
3. [`MenuItemAlias.normalize_phrase`](../../menu/models.py#L106) — `menu/models.py`.
4. [`MenuSelection.unit_price`](../../menu/selection.py#L101) — `menu/selection.py`.
5. [`GeminiClient.available`](../../recommendation/services/gemini.py#L29) — `recommendation/services/gemini.py`.

### Modul 3: Enkapsulasi

1. [`BudgetConstraint`](../../recommendation/services/budget.py#L17) — `recommendation/services/budget.py`.
2. [`MenuSelection`](../../menu/selection.py#L97) — `menu/selection.py`.
3. [`CartService.add_item`](../../cart/services.py#L36) — `cart/services.py`.
4. [`StaffAccess`](../../users/access.py#L10) — `users/access.py`.
5. [`ConversationSession.reset`](../../recommendation/services/conversation_session.py#L123) — `recommendation/services/conversation_session.py`.

### Modul 4: Relasi Kelas dan UML

1. [`MenuItem`](../../menu/models.py#L68) — `menu/models.py`.
2. [`OrderItem`](../../orders/models.py#L135) — `orders/models.py`.
3. [`MenuSelection.__init__`](../../menu/selection.py#L34) — `menu/selection.py`.
4. [`ChatbotService.__init__`](../../recommendation/services/chatbot.py#L45) — `recommendation/services/chatbot.py`.
5. [`TextGenerator`](../../recommendation/services/text_generator.py#L6) — `recommendation/services/text_generator.py`.

### Modul 5: Inheritance

1. [`GeminiClient.generate`](../../recommendation/services/gemini.py#L61) — `recommendation/services/gemini.py`.
2. [`BootstrapModelForm.__init__`](../../users/forms.py#L11) — `users/forms.py`.
3. [`MenuItem.save`](../../menu/models.py#L71) — `menu/models.py`.
4. [`MenuPhotoForm.__init__`](../../menu/forms.py#L34) — `menu/forms.py`.
5. [`MenuPhotoWidget.get_context`](../../menu/widgets.py#L12) — `menu/widgets.py`.

### Modul 6: Polimorfisme dan Abstraksi

1. [`TextGenerator`](../../recommendation/services/text_generator.py#L6) — `recommendation/services/text_generator.py`.
2. [`FakeProvider.generate`](../../recommendation/tests/test_ai_only.py#L31) — `recommendation/tests/test_ai_only.py`.
3. [`VariantGroup.__str__`](../../menu/models.py#L142) — `menu/models.py`.
4. [`BudgetConstraint.__eq__`](../../recommendation/services/budget.py#L107) — `recommendation/services/budget.py`.
5. [`MenuPhotoWidget.get_context`](../../menu/widgets.py#L12) — `menu/widgets.py`.

### Modul 7: Prinsip SOLID

1. [`MenuSelection.from_ids`](../../menu/selection.py#L44) — `menu/selection.py`.
2. [`TextGenerator`](../../recommendation/services/text_generator.py#L6) — `recommendation/services/text_generator.py`.
3. [`GeminiClient._generate`](../../recommendation/services/gemini.py#L65) — `recommendation/services/gemini.py`.
4. [`StaffAccess`](../../users/access.py#L18) — `users/access.py`.
5. [`ChatbotService.__init__`](../../recommendation/services/chatbot.py#L45) — `recommendation/services/chatbot.py`.


## Menghubungkan konsep dengan tindakan pengguna

Pelanggan memilih makanan, varian, tambahan, dan jumlah. CartService menerima pilihan tersebut.
MenuSelection memeriksa apakah pilihannya sesuai katalog dan membantu menghitung harga. Ketika
checkout, fungsi pesanan memeriksa lagi lalu menyimpan pesanan beserta harga saat itu.

Dari alur ini kita dapat melihat class, object, data, method, dan kerja sama antarbagian. Tidak
semua langkah perlu memakai inheritance. Fungsi biasa juga dapat tepat untuk pekerjaan
tertentu; orders/services.py tidak mempunyai class OrderService yang perlu dihafal.

## Menyiapkan penjelasan sendiri

Pilih satu kasus dan ceritakan masalah, data awal, pemeriksaan, serta hasilnya. Tunjukkan kode
yang mendukung penjelasanmu. Sebutkan juga satu hal yang belum dijamin oleh contoh itu.
Misalnya, tuple menjaga daftar anggota tetapi tidak membuat seluruh object di dalamnya tidak
bisa berubah.

Latihan ada di [Modul 10](10.%20Latihan%20dan%20Presentasi.md). Untuk memahami web lebih
lengkap, baca [panduan pengembangan](../PANDUAN_PENGEMBANGAN.md) atau [penjelasan
chatbot](../Chatbot.md). Cara menjalankan tes ada di [pemeriksaan
lokal](../PANDUAN_TESTING_LOKAL.md).
