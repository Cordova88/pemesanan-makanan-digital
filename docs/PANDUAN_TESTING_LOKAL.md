# Panduan Pemeriksaan Lokal RasaKita

Diselaraskan pada **23 Oktober 2026** dengan kode proyek utama di branch `ahmad`.

Panduan ini dipakai anggota tim untuk memeriksa fitur melalui browser setelah menjalankan
proyek. Semua perintah dimulai dari folder proyek yang berisi `manage.py`. Pemasangan
pertama mengikuti [README](../README.md).

## Mulai dari pemeriksaan kecil

Pilih satu tindakan yang ingin diperiksa, misalnya menambah makanan ke keranjang. Tulis hasil
yang diharapkan, lakukan tindakan itu, lalu bandingkan hasilnya. Setelah contoh biasa berhasil,
coba satu masukan yang seharusnya ditolak, misalnya jumlah melebihi batas.

Panduan ini membedakan tes lewat browser dan tes otomatis. Tes otomatis adalah kode yang
menjalankan langkah latihan dan memeriksa hasilnya. Data tiruan pada tes dipakai agar
pemeriksaan tidak harus memakai pesanan atau akun asli.

## 1. Siapkan lingkungan kerja

Gunakan data latihan untuk mencoba pesanan, pembayaran, atau perubahan katalog. Tindakan
tersebut benar-benar menyimpan data pada database lokal. Jika laptop sudah mempunyai data
kerja, cadangkan database dan media sebelum mencoba perubahan yang memengaruhi data.

Aktifkan lingkungan Python dan periksa proyek:

```powershell
.\.venv\Scripts\Activate.ps1
python -B manage.py check
python -B manage.py showmigrations
```

Jika ada migrasi yang belum diterapkan, hentikan server, cadangkan data, lalu jalankan `python
-B manage.py migrate`. Tidak perlu menghapus database atau memuat ulang fixture. Setelah itu
jalankan:

```powershell
python -B manage.py runserver 127.0.0.1:8890 --noreload
```

Profil bawaan memakai mode lokal tanpa Gemini. Kunci API tidak diperlukan untuk memeriksa
katalog, keranjang, transaksi, atau percakapan lokal. Restart server setelah mengubah kode
Python karena perintah di atas memakai `--noreload`.

## 2. Periksa alur pelanggan

1. Buka `http://127.0.0.1:8890/` dan pastikan katalog serta foto terlihat.
2. Cari menu dan gunakan kategori untuk mempersempit hasil.
3. Buka detail menu. Pilih varian wajib jika tersedia, tambahan, jumlah, dan catatan.
4. Masukkan pilihan ke keranjang. Cocokkan harga dan jumlah dengan pilihan tadi.
5. Ganti jenis pesanan dari keranjang. Dialog harus terbuka di atas keranjang;
   setelah memilih atau membatalkan, pengguna tetap berada di keranjang.
6. Lanjut ke konfirmasi. Ringkasan bisa dibaca, sedangkan catatan dan jenis
   pesanan tidak bisa diedit di tahap ini. Kembali ke keranjang bila ingin mengubahnya.
7. Kirim satu pesanan latihan dan catat nomor pesanannya.

Untuk makan di tempat, siapkan meja/QR sesuai [panduan
penggunaan](PANDUAN_PENGGUNAAN.md#4-makan-di-tempat-dan-qr-meja).

## 3. Periksa alur staf dan kasir

Gunakan browser lain atau jendela privat agar sesi pelanggan dan operator terpisah.

1. Login melalui `/staff/login/` dengan akun yang sesuai.
2. Pada CMS, periksa apakah pesanan latihan muncul beserta jenis, jumlah,
   catatan, dan total yang benar.
3. Jalankan perubahan status sesuai pilihan yang tersedia pada aplikasi.
4. Pada `/kasir/`, pilih pesanan latihan dan catat pembayarannya satu kali.
5. Cocokkan status pembayaran dan struk dengan pesanan. Jangan membayar ulang
   pesanan yang sama untuk mengulangi percobaan.

Panduan setiap layar ada di [CMS/Admin](PANDUAN_CMS_ADMIN.md).

## 4. Periksa percakapan lokal

Buka `/chatbot/`. Cocokkan jawaban dengan menu yang tersedia pada katalog, bukan dengan daftar
menu milik anggota lain.

| Percakapan | Yang diperhatikan |
|---|---|
| `minuman maksimal 10 ribu` | Hasil sesuai kategori dan batas harga. |
| Lanjut `minimal 5 ribu` | Batas baru mengganti batas lokal lama. |
| `harga [nama menu] berapa?` | Harga sesuai katalog; pertanyaan tidak membuat pesanan. |
| `cari menu lain` | Alternatif mengikuti konteks yang masih berlaku. |
| Meminta varian atau tambahan | Bot mengarahkan pemilihan melalui detail menu/keranjang. |
| Pertanyaan alergi | Bot tidak menjamin keamanan bahan dari tag menu. |
| Menekan **Mulai Lagi** | Percakapan dimulai ulang dan keranjang tidak dikosongkan. |

Cara kerja budget dan konteks dijelaskan pada [Chatbot.md](Chatbot.md). Pemeriksaan lokal ini
tidak memerlukan pengaktifan Gemini.

## 5. Laporkan masalah agar bisa diulang

Sertakan branch/revisi, langkah yang dilakukan, hasil yang diharapkan, dan hasil yang muncul.
Untuk chatbot, urutan pesan sebelumnya dapat memengaruhi hasil. Sertakan tangkapan layar bila
membantu, dengan data pribadi disamarkan.

Contoh laporan: “Dari keranjang, saya membuka jenis pesanan lalu menekan batal. Seharusnya
tetap di keranjang, tetapi halaman berpindah ke katalog.”

Jangan membagikan Kunci API, password, cookie, atau isi sesi. Keberhasilan mencoba satu alur
belum membuktikan seluruh fitur benar; fokuskan pemeriksaan pada bagian yang berubah dan alur
yang bergantung padanya.

## 6. Pemeriksaan terfokus perubahan terbaru

| Area | Contoh pemeriksaan | Hasil yang diharapkan |
|---|---|---|
| Keranjang | 98 porsi + 1, lalu tambah 1 lagi pada pilihan/catatan sama | 99 berhasil; tambah berikutnya ditolak tanpa perubahan |
| Keranjang | Edit jumlah 100, bool, atau string melalui data yang dikirim uji | Ditolak pada jalur pemeriksaan; jangan menganggap input HTML satu-satunya kontrol |
| Checkout | Beberapa baris latihan; salah satu selection tidak sesuai aturan | Tidak meninggalkan order/baris/audit parsial |
| Logout | GET, POST tanpa CSRF, lalu tombol resmi | GET yang sudah login 405; POST tanpa token 403; tombol berhasil |
| Foto | JPEG/PNG/WebP, format lain, animasi, ukuran berlebih | Format sesuai diterima bila batas lain sah; kasus terlarang ditolak |
| Reset | Dialog lama, cart, dan penghitung yang diketahui | Teks lama hilang; cart/penghitung tetap; sapaan AI baru masih mungkin |
| Layanan AI | Respons pengganti jawaban Gemini pada tes dan beberapa putaran fungsi bantuan | Kuota serta log berlaku per panggilan AI; tidak perlu API asli |

Gunakan tes otomatis untuk data yang dikirim, pencatatan perintah ke database, dan kondisi gagal yang tidak mudah
dibuat melalui UI. Jangan mengirim permintaan pengubahan data ke pemasangan orang lain untuk
meniru tes.

## 7. Menjalankan profil latihan tanpa konfigurasi aplikasi

`config.audit_test_settings` adalah kumpulan pengaturan khusus latihan. Database SQLite
dibuat sementara di memori dan file latihan memakai folder sementara. Gemini dimatikan
secara bawaan. Saat tes memeriksa alur AI, panggilan ke Google diganti dengan jawaban tiruan.

Pengaturan ini tidak membaca v1_settings/config.settings, sehingga `.env` yang dimuat kedua
berkas tersebut juga tidak dipakai. Data dan pengaturan tes terpisah dari aplikasi biasa.
Namun ini bukan pembatas seluruh akses komputer atau jaringan.

Dari folder proyek dengan interpreter proyek:

```powershell
python -B -m django test --settings=config.audit_test_settings recommendation.tests.test_audit_regressions cart.tests.test_audit_regressions orders.tests.test_audit_regressions users.tests.test_logout_security menu.tests.test_image_processing --verbosity=1
```

Jika folder sementara bawaan Windows tidak dapat ditulis, arahkan TEMP/TMP **pada proses
terminal tes itu** ke folder kerja sementara yang dapat ditulis. Tidak perlu mengubah profil
penggunaan sebenarnya atau menghapus database aplikasi.

Periksa ringkasan hasil setiap kali menjalankan tes. `OK` menyatakan seluruh tes yang dipilih
selesai tanpa kegagalan; `FAILED` perlu ditelusuri dari nama tes dan rincian kesalahan. Bedakan
error konfigurasi, keterbatasan layanan AI tiruan pada tes, dan kegagalan aturan bisnis. Catat revisi,
perintah, serta hasil aktual agar anggota lain dapat mengulang pemeriksaan.

## 8. Memeriksa Gemini asli dan terminal

Pilih pengujian ini hanya bila ingin menilai jawaban layanan AI nyata. Gunakan konfigurasi akun
sendiri, pesan latihan, dan pantau kuota proyek/model. Membuka halaman mengirim POST awal untuk
sapaan; reset juga dapat memanggil layanan AI. API asli tidak dibutuhkan untuk menjalankan tes
latihan di atas.

Perhatikan tiga jenis log: akses GET/POST Django, JSON chat_request, dan JSON provider_attempt.
Satu pesan bisa mempunyai beberapa log layanan AI dengan request_id sama.

Waktu pencatatan JSON UTC berbeda delapan jam dari WITA. Pastikan hanya server yang dimaksud
melayani port browser; restart karena --noreload tidak memuat perubahan Python otomatis.

Jangan menyimpulkan layanan AI mati hanya dari bentuk kalimat, atau menyimpulkan biaya nol dari
estimated_cost=null.
