# Daftar Dokumentasi RasaKita

Folder ini berisi panduan penggunaan, pengembangan, dan pembelajaran untuk
branch **ahmad**. Klik nama file untuk membacanya. Semua path di bawah dihitung
dari folder `docs/`, kecuali README proyek yang berada satu tingkat di atas.

## Mulai dari kebutuhan Anda

- Ingin menjalankan web pertama kali: baca [README proyek](../README.md).
- Ingin memahami cara pelanggan, staf, dan kasir memakai web: baca
  [PANDUAN_PENGGUNAAN.md](PANDUAN_PENGGUNAAN.md).
- Ingin belajar OOP: mulai dari [oop/README.md](oop/README.md), lalu ikuti urutannya.
- Ingin memahami chatbot: baca [Chatbot.md](Chatbot.md).
- Ingin mengubah kode: baca [PANDUAN_PENGEMBANGAN.md](PANDUAN_PENGEMBANGAN.md).

## Modul pembelajaran OOP

Urutan daftar berikut juga merupakan urutan belajar yang disarankan.

1. [oop/README.md](oop/README.md): pengantar modul OOP, cara belajar, urutan
   materi, dan peta contoh class yang benar-benar ada pada proyek.
2. [oop/class-dan-object.md](oop/class-dan-object.md): menjelaskan class,
   object, atribut, method, `__init__`, dan `self` melalui contoh batas harga
   dua pelanggan yang berbeda.
3. [oop/encapsulation.md](oop/encapsulation.md): menjelaskan enkapsulasi,
   property, serta alasan data dibaca atau diubah melalui jalur tertentu.
   Contohnya memakai batas harga dan pilihan menu yang harus divalidasi.
4. [oop/abstraction.md](oop/abstraction.md): menjelaskan abstraksi sebagai
   kesepakatan pekerjaan tanpa perlu mengetahui seluruh detail pelaksanaannya.
   Mengenalkan `ABC` dan abstract method melalui pembuat teks.
5. [oop/inheritance.md](oop/inheritance.md): menjelaskan hubungan class induk
   dan turunan, override, serta contoh pewarisan `TextGenerator`, `GeminiClient`,
   dan `TurnGenerator`.
6. [oop/polymorphism.md](oop/polymorphism.md): menjelaskan pemanggilan method
   yang sama pada object berbeda. Contoh generator latihan menunjukkan bagaimana
   hasil berhasil atau tidak tersedia ditangani tanpa memanggil Gemini.
7. [oop/composition.md](oop/composition.md): menjelaskan perbedaan “memakai
   object bantuan” dengan “mewarisi class”. Mengenalkan pemberian alat bantuan
   dari luar melalui contoh pelayan dan generator teks.
8. [oop/solid.md](oop/solid.md): menjelaskan lima prinsip SOLID dengan
   pertanyaan sederhana, contoh penerapan pada proyek, dan keterbatasan yang
   masih perlu diperhatikan.
9. [oop/latihan.md](oop/latihan.md): latihan budget, generator palsu,
   penelusuran pilihan menu, perjalanan pesan chatbot, dan bahan diskusi atau
   presentasi anggota tim.

## Sistem chatbot

1. [Chatbot.md](Chatbot.md): penjelasan rinci perjalanan pesan dari browser
   sampai balasan dan kartu menu. Membahas pengenalan menu/tag, budget, konteks
   percakapan, penyaringan dan urutan menu, peran Gemini, kalimat lokal,
   keranjang, batas penggunaan, log/token, pengujian, dan keterbatasan fitur.
   Cocok dibaca setelah memahami dasar class dan object.

## Panduan proyek dan penggunaan

1. [PANDUAN_PENGEMBANGAN.md](PANDUAN_PENGEMBANGAN.md): peta kerja frontend
   dan backend. Menjelaskan struktur folder, lokasi perubahan fitur, aliran
   request, relasi data, API, harga/checkout, chatbot hybrid, OOP, migrasi,
   pengujian, serta urutan mengembangkan fitur.
2. [PANDUAN_PENGGUNAAN.md](PANDUAN_PENGGUNAAN.md): petunjuk menjalankan web
   yang sudah terpasang, menyiapkan akun, serta mengikuti alur pelanggan,
   staf, dan kasir. Termasuk QR meja, status pesanan, pembayaran, simulasi satu
   pesanan, dan kendala umum.
3. [PANDUAN_CMS_ADMIN.md](PANDUAN_CMS_ADMIN.md): petunjuk lebih rinci untuk
   layar dan form pengelolaan. Membahas kategori, menu/foto, tag, varian,
   tambahan, meja/QR, pesanan, log audit, dan pengelolaan akun melalui Django Admin.
4. [PANDUAN_TESTING_LOKAL.md](PANDUAN_TESTING_LOKAL.md): panduan memeriksa
   fitur lokal, membedakan pengujian tanpa API dengan percobaan Gemini nyata,
   menyiapkan konfigurasi opsional, dan membaca bukti pemanggilan provider.
   Sebagian runner merujuk alat workspace penulis yang tidak ikut clone GitHub.
5. [PANDUAN_VERIFIKASI_HOSTING.md](PANDUAN_VERIFIKASI_HOSTING.md): daftar
   pemeriksaan sebelum dan sesudah hosting, termasuk konfigurasi, HTTPS,
   sesi, cache bersama, batas penggunaan, privasi, pemantauan, dan penanganan
   gangguan. Ini panduan verifikasi, bukan bukti deployment sudah dilakukan.
6. [V1_BASELINE.md](V1_BASELINE.md): ringkasan acuan proyek, profil lokal
   `v1_settings.py`, lokasi database/foto, penggunaan fixture, dan hal yang
   harus dijaga saat menyiapkan atau memperbarui data.
7. [README.md](README.md): indeks yang sedang dibaca; menjelaskan kegunaan
   setiap modul dan file Markdown dalam folder dokumentasi.

## Panduan di luar folder docs

1. [../README.md](../README.md): petunjuk utama untuk anggota yang baru clone.
   Berisi prasyarat, lima langkah instalasi, pemasangan dependency, pembuatan
   database/akun, penyalinan foto awal, menjalankan server, alamat web, cara
   memperbarui proyek, serta solusi kendala awal.

## Folder diagram

`diagrams/` menyimpan versi SVG diagram yang ditautkan dari panduan. Folder
ini berisi gambar pendamping, bukan modul Python atau langkah instalasi.

Diagram Mermaid tampil pada dokumen GitHub. Tautan SVG di bawah diagram dapat
dipakai jika editor Markdown tidak merender Mermaid. Diagram memuat bagian inti
agar tetap terbaca, bukan seluruh detail model.

Riwayat audit/fase disimpan terpisah pada workspace penulis di
`UTS/output/pengembangan/`. Folder itu tidak ikut clone dan tidak diperlukan
untuk menjalankan web. Panduan instalasi utama adalah README, bukan perintah
penyiapan lama di catatan fase.
