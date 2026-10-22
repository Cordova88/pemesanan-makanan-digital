# Panduan Persiapan Hosting RasaKita

Diselaraskan pada **23 Oktober 2026** dengan kode proyek utama di branch `ahmad`.

Panduan untuk anggota tim yang mengelola server bersama. Pemasangan lokal mengikuti
[README](../README.md); profil lokal bukan konfigurasi hosting siap pakai. Dokumen ini
menjelaskan pekerjaan pengelola, bukan menyatakan aplikasi sudah diterapkan atau seluruh
kebutuhan penggunaan sebenarnya telah terpenuhi.

## Membaca panduan ini

Hosting berarti menyiapkan aplikasi pada komputer server agar dapat dipakai bersama. Ini
berbeda dengan menjalankan web hanya di laptop sendiri.

Beberapa nama pengaturan perlu tetap ditulis seperti kodenya:

- **DEBUG:** pengaturan yang menampilkan rincian kesalahan untuk pengembangan.
  Matikan pada server yang dipakai pengguna sebenarnya.
- **SECRET_KEY:** kunci rahasia Django untuk melindungi data yang ditandatangani
  aplikasi. Nilainya tidak ditulis di dokumentasi atau dibagikan ke tim.
- **Cache:** tempat penyimpanan sementara, antara lain untuk menghitung pemakaian.
- **WSGI/ASGI:** jalur penghubung Django dengan program server web. Pengelola
  memilih program server yang sesuai, bukan memakai runserver untuk layanan umum.

Jika hanya ingin mencoba web di laptop, mulai dari README. Bagian hosting dipakai ketika tim
memang menyiapkan server bersama.

## 1. Sepakati penanggung jawab

Tentukan anggota yang mengelola aplikasi, domain/server, database dan foto, backup, serta akun
Gemini bila digunakan. Catat revisi kode program yang akan dirilis. Simpan password dan kunci API
pada pengaturan rahasia server, bukan di folder proyek atau dokumen yang dibagikan ke tim.

Siapkan lingkungan percobaan terpisah sebelum menggunakan data restoran nyata. Gunakan
lingkungan itu untuk mencoba pembaruan, migrasi, pemulihan backup, dan gangguan layanan tanpa
mengganggu transaksi.

## 2. Pilih konfigurasi server secara jelas

`manage.py` memakai `v1_settings` secara bawaan untuk pengembangan lokal. Program server
bersama harus memilih profil pemasangan di server dengan jelas. `config.settings` merupakan
titik awal yang masih perlu ditinjau dan disesuaikan dengan layanan hosting.

Pada `config.settings`, DEBUG dimatikan jika tidak diatur. Nilai pengaturan lingkungan `DEBUG` hanya
menerima `true` atau `false`. Saat DEBUG dimatikan, aplikasi menolak berjalan jika `SECRET_KEY`
belum diisi, kurang dari 50 karakter, memiliki kurang dari 5 karakter berbeda, atau diawali
`django-insecure-`. Pesan penolakan tidak menampilkan nilai kunci rahasia. Pemeriksaan dasar ini tidak
menggantikan pembuatan kunci rahasia acak yang kuat dan penyimpanan rahasianya.

Sebelum menjalankan program server atau pemeriksaan pemasangan di server:

1. Siapkan kunci rahasia acak khusus server tersebut melalui pengaturan rahasia hosting.
   Jangan menulis nilai aslinya di kode program atau membagikannya dalam percakapan tim.
2. Isi pengaturan lingkungan **`SECRET_KEY`** dan tetapkan **`DEBUG=false`**. Nama kunci rahasia
   profil ini berbeda dengan `DJANGO_SECRET_KEY` pada profil lokal.
3. Isi `ALLOWED_HOSTS` dengan domain server serta `CHATBOT_REDIS_URL` dengan
   alamat cache privat yang disiapkan pengelola. URL berkredensial juga rahasia.
4. Pilih `config.settings` pada proses web, lalu jalankan pemeriksaan di bawah.

`config.settings` dan `v1_settings` saat ini memanggil `load_dotenv` jika python-dotenv
tersedia. Pengaturan yang diberikan pada proses yang sudah ada tetap didahulukan. Pada hosting, gunakan
pengelolaan rahasia dan pengaturan layanan dan pastikan `.env` lokal tidak ikut dibagikan. Profil
latihan `config.audit_test_settings` sengaja tidak mengimpor kedua profil tersebut. Jangan
mengatasi penolakan kunci rahasia dengan mengaktifkan DEBUG pada server penggunaan sebenarnya.

Untuk pekerjaan lokal anggota tim, tetap gunakan perintah pada README yang memakai
`v1_settings`; tidak perlu menyiapkan kunci rahasia server. Jika sengaja memakai
`config.settings` untuk pengembangan lokal, `DEBUG=true` harus diatur dengan jelas.

| Bagian | Yang disiapkan pengelola |
|---|---|
| Python dan paket pendukung | Versi yang sesuai `requirements.txt` dan kode program proyek. |
| Proses web | Server WSGI/ASGI sesuai hosting; `runserver` hanya untuk pengembangan. |
| Rahasia Django | Kunci rahasia yang kuat dan khusus lingkungan tersebut, tanpa jalur cadangan pengembangan lokal. |
| Debug dan domain | `DEBUG=False`, host yang diizinkan, dan domain yang benar. |
| Database | Penyimpanan yang tetap tersimpan dan migrasi yang sudah diperiksa. |
| Foto upload | Lokasi media yang bertahan setelah restart atau pembaruan aplikasi. |
| Static files | Pengumpulan serta penyajian CSS, JavaScript, dan gambar aplikasi. |
| Zona waktu | WITA (UTC+8), sesuai kegiatan tim di Samarinda. |
| Cache | Cache bersama untuk penghitung penggunaan saat aplikasi berjalan pada beberapa proses. |

Jalankan pemeriksaan dengan profil yang benar:

```powershell
python -B manage.py check --deploy --settings=config.settings
```

Jika tim membuat profil pemasangan di server lain, gunakan namanya pada perintah dan
konfigurasi proses web. Tinjau setiap error dan warning sebelum membuka layanan. Perintah ini
belum membuktikan domain, HTTPS, database, dan cache sudah bekerja bersama pada server.

## 3. Lindungi akses dan data

- Aktifkan HTTPS dan periksa sertifikat serta pengalihan alamat HTTP.
- Periksa pengaturan cookie sesi dan CSRF untuk HTTPS. Jangan mematikan CSRF
  untuk mengatasi kesalahan formulir atau permintaan.
- Pastikan pelanggan tidak bisa membuka tindakan staf/kasir tanpa izin.
- Bila ada reverse proxy, sesuaikan konfigurasi keterangan tambahan dengan perilaku hosting.
- Foto asli privat tidak boleh disajikan sebagai aset publik.
- Cadangkan database dan media sebagai satu kesatuan. Coba pulihkan ke
  lingkungan terpisah agar backup benar-benar dapat digunakan.

## 4. Siapkan cache dan sesi

Cache lokal per proses tidak cukup untuk berbagi penghitung pada beberapa program server.
Siapkan bagian program pada server bersama yang didukung, misalnya Redis, dengan akses terbatas. Periksa koneksi
dan perilakunya dari proses aplikasi yang sesungguhnya; jangan menonaktifkan pemeriksaan cache
agar pesan error hilang.

Percakapan chatbot memakai penyimpanan sesi Django dan pemeriksaan revisi. Proses aplikasi
perlu menggunakan database dan kunci rahasia yang konsisten. Bila muncul konflik percakapan, muat
keadaan terbaru; jangan menghapus seluruh sesi atau kuota untuk memperbaikinya.

Pengelola perlu menetapkan jadwal pembersihan sesi kedaluwarsa, lama penyimpanan log, dan
backup. Perintah pembersihan mengubah data, sehingga tujuan database dan jadwalnya harus
diperiksa dahulu.

## 5. Gemini bersifat opsional

Aplikasi dapat menggunakan mode lokal. Jika tim mengaktifkan Gemini:

1. Tetapkan pemilik akun, model yang tersedia, serta batas penggunaan yang ditentukan.
2. Simpan Kunci API hanya di bagian program pada server melalui konfigurasi server.
3. Jika Gemini aktif dan tersedia, jalur AI-first akan didahulukan. Batasi putaran
   fungsi melalui `GEMINI_MAX_TOOL_ITERATIONS`. Pengaturan ranking/wording lama tidak
   menonaktifkan percakapan AI-first. Memasang paket Python untuk Gemini saja tidak mengaktifkan Gemini.
4. Periksa jalur cadangan lokal ketika layanan tidak tersedia.
5. Pantau token, kuota, dan tagihan pada layanan penyedia. Jangan menganggap
   informasi pendukung token kosong atau biaya `null` berarti pemakaian gratis.

Jangan mengirim data pribadi dalam pemeriksaan. Log operasional cukup memuat informasi
pendukung yang diperlukan, seperti nomor permintaan, status, waktu, dan penggunaan; password, kunci API,
cookie, dan isi chat pribadi tidak perlu dicatat.

## 6. Periksa layanan sebelum digunakan bersama

Buka katalog, chatbot, login staf, CMS, kasir, dan struk. Buat satu transaksi latihan pada
lingkungan percobaan lalu cocokkan jumlah, harga, jenis pesanan, status, dan pembayaran.
Pastikan foto dan perubahan data tetap ada setelah proses aplikasi direstart.

Catat hasil pemeriksaan beserta revisi kode program. Jika ada masalah, selesaikan atau tunda
rilis berdasarkan keputusan tim. Panduan langkah penggunaan ada di
[PANDUAN_PENGGUNAAN.md](PANDUAN_PENGGUNAAN.md).

## 7. Pemantauan dan pemulihan

Pantau ketersediaan halaman, error aplikasi, kapasitas penyimpanan, keberhasilan backup, dan
pemakaian Gemini bila aktif. Tetapkan siapa yang menerima laporan serta melakukan tindakan saat
layanan terganggu.

Penghitung harian layanan AI pada aplikasi memakai **UTC**, sehingga pergantian harinya berbeda
dengan tengah malam WITA. Cuplikan penghitung bukan seluruh riwayat pemakaian atau bukti
tagihan. Pada cache lokal, perintah terpisah juga tidak membaca penghitung program server yang
lain.

Saat menangani gangguan, catat waktu WITA, revisi, nomor permintaan, dan gejala tanpa rahasia.
Jika masalah berasal dari layanan AI, Gemini dapat dinonaktifkan melalui konfigurasi layanan
lalu proses direstart. Tetap perbaiki kegagalan cache atau penyimpanan yang ditemukan.

Untuk kembali ke versi kode program sebelumnya, gunakan revisi rilis yang sudah dikenal tim.
Jangan memulihkan database lama tanpa perencanaan karena transaksi baru dapat hilang. Sebelum
rilis ulang, periksa alur yang terdampak dan catat hasil pemulihannya.

## 8. Hal terbaru yang perlu diuji saat pemasangan di server

Pastikan logout staf/kasir dikirim melalui POST dengan CSRF; bookmark atau link GET logout
tidak lagi merupakan alur yang sah. Uji unggahan JPEG/PNG/WebP latihan dan pastikan arsip asli
tetap privat. Periksa jumlah pada keranjang, pembatalan pesanan ketika ada kesalahan, serta
konsistensi running total audit pada data latihan.

Penghitung layanan AI kini mencakup setiap panggilan AI AI-first dan putaran fungsi bantuan. Membuka
halaman/reset juga dapat meminta sapaan AI. Karena itu perkiraan beban harus memperhitungkan
lebih dari pesan yang diketik. Batas penghitung aplikasi bukan jaminan sama dengan kuota
free/paid tier Google dan tidak menetapkan tarif. Periksa batas proyek/model pada akun penyedia
yang digunakan pengelola.

Log layanan AI mencatat token per respons paket Python untuk Gemini dan kategori kegagalan.
Waktu pencatatan JSON UTC perlu dikorelasikan dengan waktu WITA saat insiden.

Console logging belum berarti lama penyimpanan file, penghitungan token sesi, atau sistem alarm
sudah ada. Tes terfokus tidak menggantikan pemeriksaan konfigurasi dan alur pada lingkungan
pemasangan di server.

Catat hasil pemeriksaan server, akses operator, penyimpanan, dan layanan AI sebelum layanan
dipakai bersama.
