# Daftar Dokumentasi RasaKita

Indeks project utama branch `ahmad`, diselaraskan pada **23 Oktober 2026**.
Dokumentasi penggunaan mengikuti source saat ini; konfigurasi lokal, katalog,
akun, dan hasil provider dapat berbeda antarinstalasi.

## Pilih kebutuhan membaca

| Kebutuhan | Mulai dari |
|---|---|
| Instalasi baru atau memperbarui source | [README proyek](../README.md) |
| Menjalankan alur pelanggan/staf/kasir | [Panduan penggunaan](PANDUAN_PENGGUNAAN.md) |
| Mengelola katalog, foto, tag, meja, dan pesanan | [CMS dan Admin](PANDUAN_CMS_ADMIN.md) |
| Memahami struktur, API, harga, dan dependency | [Panduan pengembangan](PANDUAN_PENGEMBANGAN.md) |
| Memahami AI-first, fallback, kuota, dan token | [Sistem chatbot](Chatbot.md) |
| Memeriksa perubahan di lingkungan lokal/dummy | [Pemeriksaan lokal](PANDUAN_TESTING_LOKAL.md) |
| Menyiapkan konfigurasi server bersama | [Verifikasi hosting](PANDUAN_VERIFIKASI_HOSTING.md) |
| Belajar OOP dari kode | [Indeks OOP](oop/README.md) |

## Modul OOP bernomor

Tujuh modul utama berisi **35 kasus**, tepat lima kasus dari lima berkas utama
berbeda pada setiap modul. Setiap kasus membahas masalah, cuplikan source,
penelusuran, contoh input/hasil, konsep OOP, batas, dan latihan.

1. [1. Class dan Object.md](oop/1.%20Class%20dan%20Object.md): Class, instans, constructor, dan self.
2. [2. Atribut dan Method.md](oop/2.%20Atribut%20dan%20Method.md): Atribut kelas/instans, method, factory, property.
3. [3. Enkapsulasi.md](oop/3.%20Enkapsulasi.md): Invariant, salinan, tuple, dan kepemilikan state.
4. [4. Relasi Kelas dan UML.md](oop/4.%20Relasi%20Kelas%20dan%20UML.md): Asosiasi, agregasi, dependency, dan inheritance.
5. [5. Inheritance.md](oop/5.%20Inheritance.md): Superclass, override, super, dan batas framework.
6. [6. Polimorfisme dan Abstraksi.md](oop/6.%20Polimorfisme%20dan%20Abstraksi.md): ABC, dispatch, protokol string, dan kesamaan nilai.
7. [7. Prinsip SOLID.md](oop/7.%20Prinsip%20SOLID.md): Satu kasus per prinsip dengan batas desain.
8. [8. Pendalaman Abstraksi.md](oop/8.%20Pendalaman%20Abstraksi.md): Kontrak teks dan kontrak percakapan AI-first.
9. [9. Pendalaman Komposisi.md](oop/9.%20Pendalaman%20Komposisi.md): Perangkaian object dan siklus hidup UML.
10. [10. Latihan dan Presentasi.md](oop/10.%20Latihan%20dan%20Presentasi.md): Latihan, contoh tanpa API, dan rubrik penjelasan.

## Perubahan yang dicerminkan panduan terkini

Cart membatasi jumlah per baris melalui jalur tambah/gabung/edit yang relevan,
respons memakai satu snapshot, dan checkout mengurangi agregasi total berulang.
Logout staf/kasir memakai POST + CSRF. Pemroses foto memilih parser yang
diizinkan sejak pembukaan file. Reset menghapus teks dialog lama tetapi tetap
menjaga cart, login, dan counter penggunaan.

Chatbot memakai AI-first bila Gemini tersedia. Membuka halaman mengirim pesan
awal sehingga sapaan dapat memakai API walaupun pengguna belum mengetik.
Setiap putaran SDK diperiksa kuota dan dicatat penggunaan tokennya. Pembatas
TurnGenerator berlaku pada komponen hybrid, bukan seluruh putaran AI-first.
Perilaku ini dijelaskan bersama batas pengujiannya, bukan dianggap jaminan
seluruh jawaban AI atau deployment selalu benar.

## Catatan historis dan hasil verifikasi

- [AUDIT-FOLLOWUP.md](AUDIT-FOLLOWUP.md): catatan asal dari project security,
  termasuk status kandidat audit. Bagian "belum dijalankan" adalah riwayat saat itu.
- [SECURITY-TRANSFER.md](SECURITY-TRANSFER.md): pemindahan perubahan ke project
  utama dan hasil 45 tes terfokus serta perbandingan regresi baseline.
- [PENYELARASAN_DOKUMENTASI.md](PENYELARASAN_DOKUMENTASI.md): cakupan penyelarasan
  panduan, pemetaan rename modul, dan hasil pemeriksaan dokumentasi.

## Diagram

Folder `diagrams/` memuat SVG pendamping panduan, bukan source Python. Mermaid
di dokumen menjelaskan bagian inti. Diagram hybrid/ranking hanya menggambarkan
jalur yang disebut; jangan membacanya sebagai semua request selalu melewati jalur
tersebut. Diagram relasi UML dan perangkaian provider yang diperluas ada di modul
4, 8, dan 9. Selalu cocokkan simbol class/method dengan source yang ditautkan.
