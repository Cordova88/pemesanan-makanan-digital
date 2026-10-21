# Daftar Dokumentasi RasaKita

Folder ini berisi panduan penggunaan, pengembangan, dan pembelajaran untuk
proyek bersama mahasiswa **Universitas Mulawarman, Samarinda, Kalimantan Timur**
pada branch **ahmad**. Klik nama file untuk membacanya. Semua path di bawah dihitung
dari folder `docs/`, kecuali README proyek yang berada satu tingkat di atas.

## Mulai dari kebutuhan Anda

- Ingin menjalankan web pertama kali: baca [README proyek](../README.md).
- Ingin memahami cara pelanggan, staf, dan kasir memakai web: baca
  [PANDUAN_PENGGUNAAN.md](PANDUAN_PENGGUNAAN.md).
- Ingin belajar OOP: mulai dari [oop/README.md](oop/README.md), lalu ikuti urutannya.
- Ingin memahami chatbot: baca [Chatbot.md](Chatbot.md).
- Ingin mengubah kode: baca [PANDUAN_PENGEMBANGAN.md](PANDUAN_PENGEMBANGAN.md).

## Modul pembelajaran OOP

Mulai dari [oop/README.md](oop/README.md). Indeks itu menjelaskan folder/file,
urutan belajar sesuai tujuh modul kuliah, dan lokasi **35 kasus nyata**, masing-masing
lima kasus per materi. Setiap kasus mempunyai situasi, tautan class/method,
urutan membaca, hasil, hubungan konsep, serta batas penerapannya.

1. [oop/class-dan-object.md](oop/class-dan-object.md): Modul 1, class, object,
   __init__, dan self melalui menu, budget, keranjang, tambahan, dan akses staf.
2. [oop/atribut-dan-method.md](oop/atribut-dan-method.md): Modul 2, atribut
   instance/kelas, instance method, classmethod, staticmethod, dan property.
3. [oop/encapsulation.md](oop/encapsulation.md): Modul 3, data internal,
   property, validasi, tuple, dan salinan data, beserta batas perlindungannya.
4. [oop/uml-class-relationships.md](oop/uml-class-relationships.md): Modul 4,
   asosiasi, agregasi, komposisi, dependency, multiplisitas, dan diagram relasi nyata.
5. [oop/inheritance.md](oop/inheritance.md): Modul 5, induk/turunan, override,
   super, MRO, dan pemisahan kode buatan tim dari kemampuan Django.
6. [oop/polymorphism.md](oop/polymorphism.md): Modul 6, polimorfisme dan
   abstraksi, ABC, generate, __str__, __eq__, dan widget.
7. [oop/solid.md](oop/solid.md): Modul 7, lima prinsip SOLID; satu kasus per
   prinsip dengan bukti dan keterbatasan desain yang terlihat.
8. [oop/abstraction.md](oop/abstraction.md): catatan pendamping untuk membedakan
   kontrak pembuat teks dari percakapan AI-first dengan tool.
9. [oop/composition.md](oop/composition.md): catatan pendamping untuk membedakan
   perangkaian object bantuan dari komposisi UML yang ketat.
10. [oop/latihan.md](oop/latihan.md): latihan penelusuran tiap modul, contoh
    budget tanpa database/API, dan alur presentasi satu kasus.

## Sistem chatbot

1. [Chatbot.md](Chatbot.md): penjelasan rinci perjalanan pesan dari browser
   sampai balasan dan kartu menu. Membahas pengenalan menu/tag, budget, konteks
   percakapan, penyaringan dan urutan menu, peran Gemini, kalimat lokal,
   keranjang, batas penggunaan, log/token, dan keterbatasan fitur.
   Cocok dibaca setelah memahami dasar class dan object.

## Panduan proyek dan penggunaan

1. [PANDUAN_PENGEMBANGAN.md](PANDUAN_PENGEMBANGAN.md): peta kerja frontend
   dan backend. Menjelaskan struktur folder, lokasi perubahan fitur, aliran
   request, relasi data, API, harga/checkout, chatbot hybrid, OOP, migrasi,
   serta alur kerja dan pembagian perubahan antaranggota tim.
2. [PANDUAN_PENGGUNAAN.md](PANDUAN_PENGGUNAAN.md): petunjuk menjalankan web
   yang sudah terpasang, menyiapkan akun, serta mengikuti alur pelanggan,
   staf, dan kasir. Termasuk QR meja, status pesanan, pembayaran, simulasi satu
   pesanan, dan kendala umum.
3. [PANDUAN_CMS_ADMIN.md](PANDUAN_CMS_ADMIN.md): petunjuk lebih rinci untuk
   layar dan form pengelolaan. Membahas kategori, menu/foto, tag, varian,
   tambahan, meja/QR, pesanan, log audit, dan pengelolaan akun melalui Django Admin.
4. [PANDUAN_TESTING_LOKAL.md](PANDUAN_TESTING_LOKAL.md): langkah anggota tim
   memeriksa katalog, keranjang, pesanan, staf/kasir, dan percakapan lokal melalui
   browser. Termasuk cara melaporkan masalah agar dapat diulang oleh anggota lain.
5. [PANDUAN_VERIFIKASI_HOSTING.md](PANDUAN_VERIFIKASI_HOSTING.md): persiapan
   server bersama, pembagian penanggung jawab, konfigurasi, HTTPS, cache,
   backup, pemantauan, serta pemulihan gangguan.
6. [README.md](README.md): indeks yang sedang dibaca; menjelaskan kegunaan
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
