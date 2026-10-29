# Daftar Panduan RasaKita

Pilih panduan sesuai kebutuhanmu. Jika baru bergabung, mulai dari README proyek untuk
menjalankan web. Jika ingin belajar kodenya, mulai dari modul OOP pertama.

## Panduan proyek

| Kebutuhan | Panduan |
|---|---|
| Memasang atau memperbarui proyek di laptop | [README proyek](../README.md) |
| Memakai web sebagai pelanggan, staf, atau kasir | [Panduan penggunaan](PANDUAN_PENGGUNAAN.md) |
| Mengelola menu, foto, tag, meja, dan pesanan | [Panduan CMS dan Admin](PANDUAN_CMS_ADMIN.md) |
| Menemukan kode yang mengerjakan suatu fitur | [Panduan pengembangan](PANDUAN_PENGEMBANGAN.md) |
| Memahami cara chatbot mencari menu dan memakai Gemini | [Penjelasan chatbot](Chatbot.md) |
| Memeriksa fitur melalui browser atau tes otomatis | [Pemeriksaan lokal](PANDUAN_TESTING_LOKAL.md) |
| Menyiapkan web pada server bersama | [Persiapan hosting](PANDUAN_VERIFIKASI_HOSTING.md) |

## Belajar OOP lewat kode proyek

Mulai dari [indeks OOP](oop/README.md). Tujuh modul utama berisi 35 kasus, masing-masing
memakai lima berkas nyata berbeda. Setiap kasus dimulai dari masalah, lalu diikuti potongan
kode, langkah pembacaan, contoh hasil, dan latihan.

1. [1. Class dan Object.md](oop/1.%20Class%20dan%20Object.md): Mengenal rancangan class, object yang dibuat, dan data masing-masing.
2. [2. Atribut dan Method.md](oop/2.%20Atribut%20dan%20Method.md): Membedakan data dengan pekerjaan, serta cara memanggil method.
3. [3. Enkapsulasi.md](oop/3.%20Enkapsulasi.md): Mengatur perubahan data supaya aturan tetap dipenuhi.
4. [4. Relasi Kelas dan UML.md](oop/4.%20Relasi%20Kelas%20dan%20UML.md): Menggambar siapa berhubungan dengan siapa dan berapa jumlahnya.
5. [5. Inheritance.md](oop/5.%20Inheritance.md): Memakai kemampuan class induk dan menambahkan kebutuhan turunan.
6. [6. Polimorfisme dan Abstraksi.md](oop/6.%20Polimorfisme%20dan%20Abstraksi.md): Memahami pemanggilan yang sama dengan pekerjaan yang berbeda.
7. [7. Prinsip SOLID.md](oop/7.%20Prinsip%20SOLID.md): Membaca lima prinsip agar kode lebih mudah diubah.
8. [8. Pendalaman Abstraksi.md](oop/8.%20Pendalaman%20Abstraksi.md): Memisahkan kemampuan yang diperlukan dari cara mengerjakannya.
9. [9. Pendalaman Komposisi.md](oop/9.%20Pendalaman%20Komposisi.md): Melihat kerja sama object tanpa memaksakan hubungan induk dan turunan.
10. [10. Latihan dan Presentasi.md](oop/10.%20Latihan%20dan%20Presentasi.md): Mencoba contoh sederhana dan berlatih menjelaskan satu kasus.

## Memakai gambar pada panduan

Folder diagrams menyimpan gambar yang membantu menjelaskan alur dan hubungan class. Sebagian
dokumen juga menampilkan diagram Mermaid. Jika diagram tidak terlihat pada editor, gunakan
tautan gambar SVG yang tersedia.

Gambar hanya menunjukkan bagian penting agar mudah diikuti. Untuk mengetahui seluruh langkah,
buka berkas kode yang ditautkan. Diagram chatbot menggambarkan satu jalur: setiap pesan diproses
Gemini dengan bantuan fungsi katalog Django.
