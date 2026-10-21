# Panduan CMS dan Admin RasaKita

Panduan operator dan administrator untuk proyek bersama pada branch `ahmad`.
Nama tombol mengikuti UI yang tersedia. Alamat contoh memakai port 8890;
jika server memakai port lain, sesuaikan bagian alamatnya.

## Daftar isi

1. [Memulai dan memilih panel](#1-memulai-dan-memilih-panel)
2. [Dashboard dan navigasi](#2-dashboard-dan-navigasi)
3. [Kategori](#3-kategori)
4. [Item Menu dan foto](#4-item-menu-dan-foto)
5. [Tag Menu](#5-tag-menu)
6. [Varian](#6-varian)
7. [Tambahan](#7-tambahan)
8. [Meja dan QR](#8-meja-dan-qr)
9. [Pesanan](#9-pesanan)
10. [Log Audit](#10-log-audit)
11. [Django Admin dan akun](#11-django-admin-dan-akun)
12. [Contoh latihan](#12-contoh-latihan)
13. [Rutinitas dan pemecahan masalah](#13-rutinitas-dan-pemecahan-masalah)

## 1. Memulai dan memilih panel

Dari terminal folder repository `pemesanan-makanan-digital` dengan lingkungan
Python proyek aktif:

```powershell
.\start.ps1
```

Alternatif:

```powershell
python -B manage.py runserver 127.0.0.1:8890 --noreload
```

Biarkan terminal server tetap berjalan. Buka panel yang sesuai:

| Panel | Alamat | Kegunaan |
|---|---|---|
| Pelanggan | http://127.0.0.1:8890/ | Memeriksa katalog, foto, dan pilihan pesanan |
| CMS | http://127.0.0.1:8890/staff/ | Pengelolaan restoran sehari-hari |
| Django Admin | http://127.0.0.1:8890/admin/ | Pengelolaan akun dan model data secara langsung |
| Kasir | http://127.0.0.1:8890/kasir/ | Operasi transaksi melalui alur kasir |

### Membuat akun pertama

Akun admin dibuat sendiri pada setiap instalasi baru. Buka terminal kedua
pada folder repository yang berisi `manage.py`, lalu jalankan:

```powershell
python -B manage.py createsuperuser
```

Isi username, email, dan password saat diminta terminal. Password diketik
secara tersembunyi di terminal. Gunakan akun tersebut untuk login ke CMS dan Django Admin.
Panduan ini tidak menetapkan atau menyimpan password pengguna.

### Login dan keluar

1. Buka `/staff/`; bila belum login, halaman Masuk Staf tampil.
2. Isi Username dan Password, lalu klik **Masuk**.
3. Akun staf menuju Dashboard CMS. Akun khusus kelompok Cashier menuju kasir.
4. Gunakan **Keluar** ketika selesai.

CMS memerlukan akun aktif dengan status staf. Pada aplikasi ini, akses CMS
ditentukan oleh status staf dan mencakup seluruh halaman CMS; pembatasan per
model di Django Admin tidak otomatis menjadi pembatasan per fitur CMS.

## 2. Dashboard dan navigasi

Dashboard menampilkan Menu aktif, Kategori, Pesanan pending, Pesanan hari ini,
pesanan terbaru, serta menu dengan perkiraan stok rendah jika datanya diisi.

- **Menu aktif** menghitung item yang aktif dan tersedia. Angka ini belum
  menyaring kategori nonaktif, sehingga dapat berbeda dari jumlah di katalog.
- **Kategori** menghitung kategori yang tersimpan, termasuk kategori nonaktif.
- **Pesanan pending** menunjukkan status PENDING yang tersimpan.
- **Pesanan hari ini** menghitung pesanan yang dibuat pada tanggal lokal hari ini.
- Gunakan **Lihat semua** untuk membuka daftar pesanan dan filter lebih lengkap.
- Gunakan **Kelola Meja** untuk menuju pengelolaan meja.
- Tautan **Lihat menu pelanggan** membuka sisi pelanggan untuk memeriksa hasil.

Di layar kecil, tekan **Menu** untuk membuka navigasi. Tabel yang lebar dapat
digeser ke samping. Setelah mengubah form, tekan Simpan; sekadar mengubah input
atau melihat pratinjau belum menyimpan perubahan. **Batal** meninggalkan form
tanpa menyimpan perubahan baru.

Urutan penyiapan yang disarankan: Kategori → Tag → Item Menu → Varian/Tambahan
→ Meja/QR → pemeriksaan pelanggan → pemantauan Pesanan/Log Audit.

## 3. Kategori

Alamat: `/staff/categories/`.

### Menambah

1. Buka **Kategori**.
2. Isi **Nama kategori**, misalnya Makanan atau Minuman.
3. Centang **Aktif** agar menu dalam kategori dapat tampil bagi pelanggan.
4. Klik **Tambah**. Kategori muncul di daftar setelah berhasil disimpan.

Nama kategori harus unik. Jika nama sudah ada, perbaiki kolom yang ditandai.

### Mengedit dan menonaktifkan

1. Klik **Edit** pada kategori.
2. Ubah nama atau status Aktif.
3. Klik **Simpan perubahan**, atau **Batal** untuk kembali.

Kategori nonaktif menyembunyikan seluruh menu terkait dari katalog pelanggan,
meskipun masing-masing menu masih aktif dan tersedia. Menonaktifkan kategori
tidak menghapus menu. CMS tidak menyediakan tombol hapus kategori.

## 4. Item Menu dan foto

Alamat: `/staff/menu-items/`.

### Menambah menu

1. Klik **Tambah menu** untuk membuka form.
2. Isi Nama menu, Kategori, Deskripsi, Harga (Rp), dan Perkiraan stok bila perlu.
3. Centang tag yang sesuai. Gunakan pencarian tag jika pilihannya banyak.
4. Pilih foto pada **Gambar menu** dan periksa pratinjau.
5. Atur **Tampilkan di katalog** dan **Tersedia untuk dipesan**.
6. Klik **Simpan menu**, lalu periksa hasil pada daftar dan sisi pelanggan.

Masukkan harga sebagai angka, misalnya `18000` untuk Rp18.000. Harga dan stok
tidak boleh negatif. Perkiraan stok merupakan kolom pemantauan; untuk menutup
pemesanan sebuah menu, ubah **Tersedia untuk dipesan** secara eksplisit.

### Arti status

| Kondisi | Tampilan/hasil |
|---|---|
| Menu aktif, tersedia, kategori aktif | Dapat tampil di katalog pelanggan |
| Tersedia untuk dipesan dimatikan | Daftar CMS menampilkan Habis; menu tidak tampil pada katalog |
| Tampilkan di katalog dimatikan | Menu nonaktif dan tidak tampil pada katalog |
| Kategori nonaktif | Semua menu kategori itu tidak tampil pada katalog |

### Menyiapkan foto menu

Gunakan foto makanan/minuman terpisah, sebaiknya PNG/WebP transparan. Kartu,
background, dan blob/liquid shape dibentuk oleh UI; tidak perlu menyatukannya
ke dalam file foto. Hindari foto landscape besar sebagai foto utama.

- Format yang diterima: JPEG, PNG, WebP.
- Batas: 10 MB dan 20 juta piksel per foto.
- Foto berlatar tetap dapat diunggah, tetapi latarnya tidak otomatis dihapus.
- **Gambar menu** dipakai untuk kartu, beranda, dan pilihan menu pelanggan.
- **Foto lama (arsip opsional)** menyimpan foto arsip; tidak menjadi foto utama
  pada halaman pelanggan.
- Pratinjau menunjukkan tampilan yang akan digunakan, tetapi perubahan baru
  tersimpan setelah menekan tombol simpan.

### Mengedit atau mengganti foto

1. Cari menu berdasarkan nama atau kategori, lalu klik **Edit**.
2. Ubah informasi, harga, tag, atau status yang diperlukan.
3. Untuk mempertahankan foto, biarkan input foto tanpa memilih file baru.
4. Untuk mengganti foto, pilih file baru dan periksa pratinjau.
5. Untuk melepas foto, gunakan checkbox **Hapus** pada foto tersimpan, kemudian
   simpan. Jangan sekaligus memilih file pengganti dan mencentang Hapus.
6. Klik **Simpan perubahan**.

Jika validasi gagal setelah memilih foto baru, pilih kembali file sebelum
menyimpan. Browser tidak mengisi ulang input file secara otomatis. **Reset** pada
pencarian mengembalikan daftar semua menu. CMS tidak menyediakan hapus item menu;
gunakan status aktif/tersedia untuk mengatur penayangannya.

## 5. Tag Menu

Alamat: `/staff/tags/`. Tag menggambarkan ciri menu, misalnya Pedas, Ayam, atau
Minuman. Tag tidak menambah harga dan tidak menjadi pilihan ukuran pelanggan.

### Membuat dan memasang tag

1. Isi **Kode tag** yang unik tanpa spasi, misalnya `pedas_ringan`.
2. Isi **Nama tampilan**, misalnya Pedas Ringan. Jika kosong, kode ditampilkan.
3. Klik **Simpan tag**.
4. Buka **Item Menu → Edit**, centang tag tersebut, lalu simpan menu.

Pencarian daftar tag menerima kode atau nama tampilan. Jumlah menu pada daftar
termasuk menu nonaktif yang masih memakai tag.

### Mengedit dan melepas tag

1. Klik **Edit** pada tag untuk mengubah kode/nama tampilan.
2. Bagian **Menu yang tetap memakai tag** hanya memuat menu yang sudah terkait.
3. Hilangkan centang sebuah menu untuk melepas tag dari menu itu.
4. Klik **Simpan perubahan**.

Untuk memasang tag ke menu lain, gunakan Item Menu. Melepas tag tidak menghapus
menu maupun tag itu sendiri.

### Menghapus tag

1. Klik **Hapus** pada tag.
2. Periksa daftar menu dan jumlah alias yang terdampak.
3. Jika tag masih dipakai, centang persetujuan pelepasan dari semua menu.
4. Tekan tombol konfirmasi hapus, atau **Batal** bila tidak jadi.

Penghapusan bersifat permanen: tag dan aliasnya dihapus, menu tetap ada, tag lain
tetap tersimpan. Membuat kode tag yang sama kemudian tidak memulihkan relasinya.
Alias dapat dikelola melalui Django Admin, bukan halaman Tag Menu CMS.

## 6. Varian

Alamat: `/staff/variants/`. Varian merupakan pilihan satu opsi per grup, misalnya
Ukuran: Normal/Besar atau Level pedas: Tidak pedas/Sedang/Pedas.

### Membuat grup dan opsi

1. Pada **Tambah grup varian**, pilih Menu dan isi Nama grup.
2. Atur **Wajib dipilih**, **Aktif**, dan **Urutan tampilan**.
3. Klik **Simpan grup**.
4. Pada **Tambah opsi varian**, pilih grup yang baru dibuat.
5. Isi Nama opsi, Tambahan harga (Rp), status Aktif, dan Urutan tampilan.
6. Klik **Simpan opsi**. Ulangi untuk opsi lain.

Tambahan harga `0` berarti opsi tidak menambah harga menu. Angka urutan lebih
kecil ditampilkan lebih dahulu. Nama grup unik pada menu yang sama; nama opsi
unik dalam grup yang sama.

Isi opsi aktif terlebih dahulu sebelum memakai grup aktif yang wajib dipilih.
Grup wajib tanpa opsi aktif membuat pelanggan tidak dapat memenuhi pilihan
wajib ketika memesan.

### Mengedit dan menonaktifkan

- Klik **Edit** pada baris grup untuk mengubah grup/menu/status/urutannya.
- Klik **nama opsi** pada daftar untuk mengedit opsi, harga, status, atau urutan.
- Opsi nonaktif tidak ditawarkan kepada pelanggan.
- Grup nonaktif tidak ditawarkan, termasuk ketika Wajib dipilih dicentang.
- Simpan perubahan atau gunakan Batal. CMS tidak menyediakan hapus varian.

## 7. Tambahan

Alamat: `/staff/addons/`. Tambahan merupakan pelengkap seperti Telur atau Keju,
dengan harga sendiri. Pelanggan dapat memilih beberapa tambahan yang tersedia.

1. Isi **Nama tambahan** dan **Harga (Rp)**.
2. Centang **Menu terkait** yang boleh memakai tambahan tersebut.
3. Gunakan pencarian pilihan menu bila perlu; pilihan tercentang tetap terlihat.
4. Atur **Tersedia untuk dipesan** dan **Aktif**.
5. Klik **Simpan tambahan**.

Tambahan hanya ditawarkan pada menu yang dipilih, ketika tambahan aktif dan
tersedia. Tanpa menu terkait, tambahan tidak berlaku untuk semua menu; daftar
menampilkan **Belum terhubung ke menu**.

Klik **Edit** untuk mengubah harga, relasi atau status. Hilangkan centang menu
untuk melepas relasi. Tersedia dimatikan menghasilkan status Habis; Aktif
dimatikan menghasilkan Nonaktif. Nama tambahan unik dan harga tidak negatif.
CMS tidak menyediakan hapus tambahan.

## 8. Meja dan QR

Alamat: `/staff/tables/`.

1. Isi **Nomor / nama meja**, misalnya A1 atau Teras 2.
2. Centang **Aktif**, lalu klik **Simpan meja**.
3. Klik **Lihat QR** pada meja.
4. Periksa identitas meja, status, dan tautan dalam QR.
5. Klik **Unduh QR PNG** untuk menyimpan gambar; nama file menggunakan ID meja.
6. Gunakan **Buka menu meja ini** untuk memeriksa konteks meja pada pelanggan.

QR hanya memilih konteks meja; memindainya tidak otomatis membuat pesanan.
Pesanan dibuat melalui alur pemesanan pelanggan.

Nama/status dapat diubah melalui **Edit** tanpa mengganti token QR. Meja
nonaktif tetap dapat ditampilkan/diunduh QR-nya, tetapi tidak diterima untuk
konteks pemesanan meja sampai diaktifkan kembali. CMS tidak menyediakan hapus meja.

QR memuat alamat server yang sedang dibuka. `127.0.0.1`/`localhost` pada ponsel
mengarah ke ponsel itu sendiri, bukan komputer server. Untuk penggunaan ponsel,
server perlu dikonfigurasi agar dapat dijangkau melalui jaringan/domain yang
sesuai; buka CMS melalui alamat tersebut, kemudian unduh ulang QR. Panduan
start lokal di atas hanya membuka server untuk komputer ini.

## 9. Pesanan

Alamat: `/staff/orders/`. Halaman ini untuk pemantauan.

1. Isi **Cari pesanan** dengan ID, nama pelanggan, atau nama/nomor meja.
2. Pilih Status, Jenis pesanan, dan Periode bila diperlukan.
3. Klik **Terapkan filter**; semua pilihan dikirim bersama.
4. Gunakan **Berikutnya/Sebelumnya** bila hasil lebih dari 25 pesanan.
5. Gunakan **Reset** untuk menghapus filter.
6. Klik **Log Audit** pada baris pesanan untuk melihat riwayatnya.

| Label | Arti status tersimpan |
|---|---|
| Pending | Menunggu penyelesaian |
| Paid | Sudah dibayar |
| Cancelled | Dibatalkan |
| Expired | Kedaluwarsa |
| Refunded | Dikembalikan dananya |

Waktu ditampilkan dalam WITA. Daftar tidak menjalankan pembayaran, refund,
pembatalan, atau perubahan status. Membuka daftar juga tidak otomatis mengubah
Pending menjadi Expired. Operasi transaksi dilakukan melalui alur kasir dan
layanan aplikasi yang sesuai.

## 10. Log Audit

Alamat: `/staff/audit-log/`.

1. Cari ID pesanan, nama pelanggan, atau username pelaku.
2. Pilih **Aksi** dan **Periode**, kemudian **Terapkan filter**.
3. Periksa waktu, ID pesanan, aksi, pengguna, serta peran saat tindakan.
4. **Sistem** berarti tidak ada akun pelaku pada catatan tersebut.
5. Klik ID pesanan untuk menemukannya pada daftar Pesanan.
6. Gunakan pagination untuk catatan lama, atau Reset untuk menghapus filter.

Peran saat tindakan merupakan nilai yang tersimpan pada catatan, bukan peran
akun yang dihitung ulang sekarang. Pencarian nama pelanggan menggunakan nama
yang sekarang tersimpan pada pesanan.

Log ini mencatat tindakan pesanan seperti pembuatan, perubahan, pembayaran,
pembatalan, dan refund. Jangan menganggap setiap edit kategori/menu di CMS pasti
muncul di Log Audit pesanan. CMS tidak menyediakan edit/hapus log.

## 11. Django Admin dan akun

Alamat: `/admin/`. Gunakan CMS untuk pekerjaan restoran rutin. Django Admin
menampilkan model data dan pengaturan akun; menu yang terlihat mengikuti izin
akun. Superuser memiliki akses seluruh model yang terdaftar.

### Menambah akun CMS

Dengan akun superuser yang sudah login:

1. Buka **Users/Pengguna**, lalu **Add/Tambah**.
2. Isi username dan password melalui form yang disediakan, kemudian simpan.
3. Pada detail pengguna, pastikan **Active/Aktif** aktif.
4. Centang **Staff status/Status staf** untuk memberi akses CMS.
5. Simpan dan minta pengguna login melalui `/staff/` dengan akunnya sendiri.

Status **Superuser** diperlukan untuk administrator penuh, bukan setiap operator
CMS. Status staf sendiri sudah memberi akses seluruh fitur CMS.
Untuk akses Django Admin selain superuser, berikan izin model yang diperlukan
melalui user/group; status staf saja tidak memberi seluruh izin model di Admin.

### Akun kasir

Kelompok yang dikenali aplikasi bernama tepat **Cashier**. Untuk akun kasir
khusus, gunakan akun aktif, masukkan ke grup Cashier, dan biarkan status staf
tidak dicentang jika tidak ingin memberi akses CMS. Bila grup belum ada, buat
melalui **Groups/Grup**. Login melalui `/staff/login/`; akun kasir khusus akan
diarahkan ke `/kasir/`. Akun staf diarahkan ke CMS walaupun juga berada di grup
Cashier. Panduan ini tidak menguraikan seluruh langkah transaksi kasir.

### Mengelola alias tag

1. Buka **Menu tag aliases** atau model alias tag yang tersedia di Admin.
2. Pilih tag tujuan, isi **Phrase** sebagai ungkapan alternatif, dan atur Aktif.
3. Simpan. Contoh: phrase `pedes` untuk tag Pedas.

Alias yang sama untuk tag yang sama tidak boleh diduplikasi. Alias membantu
pengenalan istilah; pengaturan rekomendasi lebih lanjut berada di modul chatbot.

### Mengelola data model lain

Admin juga mendaftarkan kategori, menu, varian, tambahan, meja, pesanan, item
pesanan, pembayaran dan audit. Pada form menu Admin, Gambar menu tetap memakai
widget pratinjau foto. Label beberapa field dapat berbeda dari CMS.

Jangan menggunakan edit langsung Order/Payment di Admin sebagai cara menerima
pembayaran atau refund. Form model langsung tidak menggantikan alur transaksi
kasir yang memvalidasi dan mencatat tindakan. Field audit utama dibuat read-only
di Admin, tetapi itu bukan jaminan audit tidak bisa dihapus oleh akun berizin;
gunakan CMS Log Audit untuk membaca riwayat. Penghapusan model tertentu dapat
ditolak ketika masih menjadi referensi data lain.

## 12. Contoh latihan

Lakukan latihan pada database percobaan, bukan katalog yang sedang dipakai.

Contoh penyiapan Nasi Goreng Rp20.000:

1. Pastikan kategori Makanan aktif dan menu aktif/tersedia.
2. Buat grup Ukuran, lalu opsi Normal +Rp0 dan Besar +Rp3.000.
3. Jika grup wajib, pastikan opsi aktif sudah ada sebelum mengaktifkan kewajiban.
4. Buat tambahan Telur Rp5.000 dan hubungkan ke Nasi Goreng.
5. Pada sisi pelanggan, pilih Besar dan Telur, dua porsi.
6. Hitungan contoh: `(20.000 + 3.000 + 5.000) × 2 = Rp56.000`.
7. Buat meja percobaan aktif, lalu periksa QR dan konteks meja pelanggan.
8. Setelah pesanan dibuat melalui alur pelanggan, cari ID-nya pada Pesanan dan
   periksa Log Audit. Jangan membuat status Paid secara manual untuk latihan bayar.

Contoh ini menjelaskan cara memakai fitur; menulis panduan tidak menjalankan
latihan atau membuat data baru pada database lokal Anda.

## 13. Rutinitas dan pemecahan masalah

### Sebelum operasional

- Periksa kategori aktif, menu tersedia, harga, dan foto.
- Pastikan setiap grup wajib memiliki opsi aktif.
- Periksa menu terkait serta status tambahan.
- Periksa meja aktif dan alamat QR yang akan digunakan pelanggan.
- Buka sisi pelanggan untuk memastikan konfigurasi terlihat sesuai.

### Saat dan setelah operasional

- Tandai menu/tambahan habis melalui status tersedia.
- Pantau Pesanan dan baca Log Audit ketika menelusuri perubahan transaksi.
- Keluar dari akun pada komputer bersama.
- Backup database `db.sqlite3` dan folder `media/` bersama; arsip upload berada
  di `private/menu-originals/` bila sudah ada. Hentikan server sebelum menyalin
  SQLite secara manual agar tidak menyalin database yang sedang ditulis.

### Masalah umum

| Gejala | Yang diperiksa |
|---|---|
| Situs tidak terbuka | Terminal server masih berjalan, alamat/port benar, berada di folder repository |
| Login gagal | Akun sudah dibuat, password benar, akun aktif dan memiliki status staf atau grup Cashier |
| Bisa login tetapi diarahkan ke kasir | Akun berada di grup Cashier tanpa status staf |
| Menu tidak tampil | Kategori aktif, Tampilkan di katalog aktif, Tersedia untuk dipesan aktif |
| Tambahan tidak tampil | Menu terkait dicentang, tambahan aktif dan tersedia |
| Pesanan ditolak karena varian | Satu opsi per grup wajib; opsi dan grup aktif serta milik menu yang dipilih |
| Nama duplikat ditolak | Pakai Edit pada data existing atau gunakan nama/kode lain |
| Foto tidak tersimpan | Format/ukuran valid; pilih ulang file setelah validasi gagal, lalu simpan |
| Foto tetap berlatar kotak | File tidak transparan; gunakan cutout PNG/WebP transparan |
| QR tidak bekerja di ponsel | Alamat QR bukan localhost ponsel; server/jaringan/domain sudah dapat dijangkau |
| QR meja ditolak | Meja masih aktif dan tautan tidak diubah |
| Daftar terlihat kosong | Hapus filter dengan Reset; instalasi baru belum berisi meja/transaksi/log |
| Tombol tambah/menu navigasi tidak terbuka | Pastikan aset UI/CDN termuat; koneksi diperlukan untuk library yang memakai CDN |

### Catatan penggunaan

Menu CMS tersedia sesuai panduan di atas; sejumlah halaman menyediakan nonaktif,
bukan hapus. Tidak ada tombol ekspor transaksi atau detail transaksi baru pada
CMS Pesanan. Perubahan akun/transaksi langsung di Admin memerlukan pemahaman
relasi data. Untuk proses harian, ikuti alur CMS/kasir yang telah tersedia.

Nama menu Admin dapat mengikuti pengaturan bahasa dan izin akun yang digunakan.

Referensi teknis untuk pengembang: users/urls.py, users/views.py, users/forms.py,
users/templates/users/, menu/forms.py, menu/admin.py, orders/admin.py, dan
orders/services.py. Panduan menjalankan: [README](../README.md).

Pertanyaan latihan:
1. Apa perbedaan menonaktifkan kategori dengan menandai satu menu habis?
2. Mengapa tambahan harus dihubungkan ke menu dan grup wajib harus punya opsi aktif?
