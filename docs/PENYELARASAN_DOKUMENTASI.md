# Penyelarasan Dokumentasi dan Modul OOP

Tanggal: 23 Oktober 2026. Target: project utama `pemesanan-makanan-digital`,
branch `ahmad`, setelah perubahan aplikasi pada commit `ee4d1a8`.

## Tujuan dan batas perubahan

Panduan penggunaan/pengembangan disesuaikan dengan implementasi terkini, dan
modul OOP diperluas agar dapat dipakai belajar serta presentasi. Perubahan
hanya menyentuh Markdown: backend, konfigurasi runtime, dependency, database,
media, dan perilaku sapaan chatbot tidak diubah.

Materi sekarang terdiri atas tujuh modul utama dengan 35 kasus. Setiap modul
menggunakan lima berkas utama berbeda; satu berkas boleh dibahas kembali pada
modul lain dengan sudut konsep yang berbeda. Dua materi pendalaman dan satu
modul latihan tidak dihitung sebagai tambahan kasus utama.

## Pemetaan nama berkas

| Sebelumnya di docs/oop | Sekarang |
|---|---|
| class-dan-object.md | [1. Class dan Object.md](oop/1.%20Class%20dan%20Object.md) |
| atribut-dan-method.md | [2. Atribut dan Method.md](oop/2.%20Atribut%20dan%20Method.md) |
| encapsulation.md | [3. Enkapsulasi.md](oop/3.%20Enkapsulasi.md) |
| uml-class-relationships.md | [4. Relasi Kelas dan UML.md](oop/4.%20Relasi%20Kelas%20dan%20UML.md) |
| inheritance.md | [5. Inheritance.md](oop/5.%20Inheritance.md) |
| polymorphism.md | [6. Polimorfisme dan Abstraksi.md](oop/6.%20Polimorfisme%20dan%20Abstraksi.md) |
| solid.md | [7. Prinsip SOLID.md](oop/7.%20Prinsip%20SOLID.md) |
| abstraction.md | [8. Pendalaman Abstraksi.md](oop/8.%20Pendalaman%20Abstraksi.md) |
| composition.md | [9. Pendalaman Komposisi.md](oop/9.%20Pendalaman%20Komposisi.md) |
| latihan.md | [10. Latihan dan Presentasi.md](oop/10.%20Latihan%20dan%20Presentasi.md) |

README pada folder OOP tetap menjadi indeks. Tautan internal memakai nama baru
dengan spasi yang di-encode untuk Markdown. Tautan eksternal yang pernah
mengarah ke nama lama perlu diperbarui oleh pemiliknya; tidak dibuat duplikat
materi lama yang dapat berbeda isi.

## Bentuk pembahasan setiap kasus

Setiap kasus memuat masalah konkret, berkas dan simbol sumber, cuplikan kode
asli, urutan penelusuran, contoh input/hasil, konsep OOP, batas desain, dan
latihan. Cuplikan diambil dari source; cuplikan yang panjang ditampilkan bagian
awalnya dan diberi keterangan. Nama/harga contoh bukan pembacaan katalog nyata.

Contoh untuk enkapsulasi: baris cart berjumlah 98 ditambah 2 ditolak sebelum
assignment. Materi menjelaskan invariant, posisi validasi, state sesi, serta
defensive copy. Kasus tidak berhenti pada definisi "atribut memakai underscore"
dan tidak mengklaim batas 99 sebagai batas semua baris atau semua operasi kasir.

Materi juga membedakan inheritance framework, abstraksi layanan, kontrak ABC,
delegation, dan hubungan UML. Fungsi pada orders/services.py tetap dijelaskan
sebagai fungsi; tidak dibuat class OrderService fiktif.

## Panduan yang diselaraskan

- README proyek dan indeks docs: urutan baca serta perilaku perubahan terbaru.
- Panduan pengembangan: snapshot cart, total_for, checkout dengan agregasi akhir,
  logout POST, batas provider, serta peta OOP dan status regresi.
- Panduan penggunaan dan CMS: jumlah, tombol logout/CSRF, parser foto, reset,
  serta perbedaan log audit transaksi dan metadata provider.
- Panduan testing: skenario gagal, profil dummy, bukti tes terdahulu, dan
  langkah membedakan log akses/request/provider.
- Panduan hosting: pemuatan dotenv yang benar sesuai source, cache bersama,
  batas aplikasi dibanding kuota provider, dan cakupan verifikasi deployment.
- Chatbot.md: POST inisialisasi/sapaan, reset yang dapat meminta sapaan baru,
  kuota/log tiap dispatch, UTC dibanding WITA, serta batas TurnGenerator hybrid.
- Catatan audit dan transfer: konteks historis ditambahkan tanpa menaikkan
  status kandidat keamanan atau mengubah hasil pengujian yang dicatat saat itu.

## Pemeriksaan dan batas bukti

Pemeriksaan dokumentasi meliputi keberadaan file/anchor tautan lokal, keberadaan
simbol Python yang dirujuk, kecocokan 35 cuplikan dengan source, tepat lima
kasus dari lima file per modul, dan eksekusi contoh BudgetConstraint yang tidak
memakai database atau API. Hasil akhir: **22 berkas Markdown, 334 tautan lokal,
dan 35 cuplikan source diperiksa tanpa temuan gagal**. Ketujuh modul masing-masing
memenuhi lima kasus dari lima berkas berbeda. Contoh BudgetConstraint menghasilkan
keluaran sesuai prediksi, dan `git diff --check` lulus. Pemeriksaan status Git
memastikan perubahan di repository hanya README dan dokumentasi.

Tes Django, browser, dan provider tidak diulang hanya karena Markdown berubah.
Riwayat 45 tes terfokus dan kegagalan regresi lama tetap dijelaskan sebagai
hasil pekerjaan aplikasi sebelumnya, bukan hasil baru penyelarasan dokumen.
PDF kuliah asal tidak tersedia di repository dan tidak diverifikasi ulang;
rujukan nomor halaman lama dihilangkan agar tidak memberi kesan sudah diperiksa.

## Cara review dan mencoba materi

Buka [indeks OOP](oop/README.md), ikuti nomor modul, lalu buka simbol pada kasus
yang dipilih. Cocokkan penjelasan dengan source, prediksi hasil contoh, dan
gunakan latihan pada modul 10. Untuk penggunaan web, mulai dari
[indeks dokumentasi](README.md) sesuai peran pengguna.

Checklist review: urutan modul benar, tautan baru terbuka, lima berkas berbeda
terlihat pada setiap modul, contoh mempunyai kondisi gagal, dan batas OOP tidak
dibaca sebagai jaminan keamanan seluruh sistem. Usulan pesan commit:
`docs: selaraskan panduan proyek dan perluas 35 studi kasus OOP`.
