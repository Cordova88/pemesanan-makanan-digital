# Belajar OOP lewat RasaKita

Modul ini untuk anggota tim yang ingin memahami **mengapa kode disusun seperti
sekarang**, bukan sekadar menghafal definisi. OOP adalah cara mengelompokkan data
dan pekerjaan yang berkaitan ke dalam object.

Bayangkan restoran: ada pilihan menu, keranjang, dan petugas yang memeriksa
pesanan. Pada program, masing-masing dapat mempunyai data serta pekerjaan
sendiri. Tidak semua bagian harus dijadikan class; fungsi biasa juga dipakai
ketika lebih jelas.

## Mulai dari mana?

| Urutan | Modul | Setelah belajar, Anda bisa… |
|---|---|---|
| 1 | [Class dan object](class-dan-object.md) | Membedakan cetakan, object, atribut, dan method. |
| 2 | [Enkapsulasi](encapsulation.md) | Memahami alasan data dibaca/diubah melalui jalur tertentu. |
| 3 | [Abstraksi](abstraction.md) | Membaca aturan dasar tanpa perlu mengetahui seluruh detailnya. |
| 4 | [Inheritance](inheritance.md) | Mengenali hubungan class induk dan turunannya. |
| 5 | [Polymorphism](polymorphism.md) | Memakai pemanggilan yang sama untuk object berbeda. |
| 6 | [Composition dan bantuan dari luar](composition.md) | Membedakan “mempunyai” dengan “merupakan”. |
| 7 | [SOLID dengan bahasa sederhana](solid.md) | Menilai pembagian tanggung jawab tanpa memaksakan teori. |
| 8 | [Latihan dan bahan diskusi](latihan.md) | Menelusuri alur serta menjelaskan pilihan desain tim. |

## Cara menggunakan modul

1. Baca cerita/contoh sederhananya terlebih dahulu.
2. Tebak hasil contoh sebelum menjalankannya.
3. Buka tautan kode proyek untuk melihat penerapannya.
4. Jawab pertanyaan di bagian akhir dengan kalimat sendiri.
5. Lanjut ke modul berikutnya setelah bisa menjelaskan contoh sebelumnya.

Contoh Python kecil pada modul merupakan **program latihan**, kecuali ditandai
sebagai cuplikan kode proyek. Class latihan tidak otomatis ada pada aplikasi.
Jangan menyalin class latihan ke backend hanya untuk menambah jumlah class.

Untuk menjalankan contoh, buat file latihan di luar paket aplikasi, misalnya
`latihan_oop.py` pada folder proyek, gunakan lingkungan Python proyek, lalu:

```powershell
python -B latihan_oop.py
```

Gabungkan blok pada satu modul secara berurutan jika tertulis “lanjutkan”.
Contoh modul tidak memerlukan API key, tidak mengakses Gemini, dan tidak
menulis data restoran. Jangan memasukkan file latihan atau rahasia ke commit
fitur tanpa diperiksa dahulu.

## Peta contoh nyata

| Konsep | Contoh pada proyek |
|---|---|
| Object yang menyimpan batas harga | [`BudgetConstraint`](../../recommendation/services/budget.py) |
| Pilihan menu yang sudah diperiksa | [`MenuSelection`](../../menu/selection.py) |
| Aturan dasar pembuat teks | [`TextGenerator`](../../recommendation/services/text_generator.py) |
| Turunan pembuat teks | [`GeminiClient`](../../recommendation/services/gemini.py), [`TurnGenerator`](../../recommendation/services/ai/turn_generator.py) |
| Layanan yang memakai beberapa object bantuan | [`ChatbotService`](../../recommendation/services/chatbot.py) |
| Keputusan akses akun | [`StaffAccess`](../../users/access.py) |

Tautan kode dari folder modul berada dua tingkat di atas `docs/oop/`.
Pada GitHub, klik nama file untuk membacanya; di editor, cari nama class/method
karena nomor baris dapat berubah setelah perapian.

Sesudah modul dasar, baca [penjelasan chatbot](../Chatbot.md) untuk melihat
bagaimana beberapa konsep bekerja bersama. Untuk peta seluruh backend, buka
[panduan pengembangan](../PANDUAN_PENGEMBANGAN.md).
