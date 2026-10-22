# RasaKita — Pemesanan Makanan Digital

Diselaraskan pada **23 Oktober 2026** dengan source project utama di branch `ahmad`.

Aplikasi restoran berbasis Django: pelanggan memilih menu dan membuat pesanan,
staf mengelola katalog, dan kasir mencatat pembayaran. Chatbot membantu mencari
menu; pemesanan tetap dilanjutkan melalui pilihan menu dan keranjang.

Proyek bersama mahasiswa **Universitas Mulawarman, Samarinda, Kalimantan Timur**.
Waktu operasional mengikuti **WITA (UTC+8)**.

Panduan ini mengikuti **branch `ahmad`**. Pembaruan source tidak otomatis mengubah
database, akun, foto upload, atau konfigurasi di laptop anggota lain.

## Sebelum mulai

- Siapkan Git, Python, dan browser. Proyek diverifikasi menggunakan **Python 3.14**.
- SQLite sudah tersedia bersama Python; tidak perlu memasang MySQL atau Laragon.
- Internet diperlukan saat clone, instalasi dependency, serta memuat Bootstrap
  dan pemindai QR dari CDN. Chatbot lokal tidak membutuhkan API key Gemini.
- Contoh memakai PowerShell Windows. Jalankan semua perintah dari folder
  `pemesanan-makanan-digital` yang berisi `manage.py`; lokasi penyimpanannya bebas
  pada laptop masing-masing anggota.

## Instalasi pertama — lima langkah

Gunakan bagian ini untuk **clone baru yang belum memiliki database sendiri**.
Jika sudah mempunyai proyek/data, ikuti [cara memperbarui proyek](#memperbarui-proyek-yang-sudah-ada).

### 1. Ambil branch ahmad

```powershell
git clone --branch ahmad https://github.com/Cordova88/pemesanan-makanan-digital.git
cd pemesanan-makanan-digital
git branch --show-current
```

Hasil terakhir harus `ahmad`. Jika folder bernama sama sudah ada, jangan ditimpa;
gunakan folder baru atau ikuti langkah pembaruan.

### 2. Siapkan Python dan dependency

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Lingkungan virtual menyimpan dependency proyek secara terpisah. Jika aktivasi
PowerShell diblokir, gunakan `.\.venv\Scripts\python.exe` sebagai pengganti
`python` pada perintah berikutnya. Tidak perlu mengubah kebijakan keamanan Windows.

`requirements.txt` berisi daftar paket beserta versi yang dibutuhkan. Perintah
instalasi membaca daftar itu dan memasang paket ke `.venv`; tidak mengisi file
requirements secara otomatis. Gunakan file yang sama agar anggota tim memasang
versi SDK Gemini dan pemuat konfigurasi yang sesuai proyek. SDK terpasang tetap
tidak berarti Gemini aktif.

### 3. Buat database dan akun admin

```powershell
python -B manage.py migrate
python -B manage.py loaddata v1_catalog
python -B manage.py createsuperuser
```

- `migrate`: membuat tabel aplikasi.
- `loaddata v1_catalog`: mengisi empat menu awal, kategori, tag, varian, dan
  tambahan. Tidak membuat akun atau meja.
- `createsuperuser`: isi username/password pilihan sendiri secara interaktif.
  Password tidak ditampilkan saat diketik; itu normal.

**Jangan menjalankan `seed_demo` untuk instalasi branch ini.** Jangan mengulang
`loaddata` pada database yang katalognya sudah diedit karena ID yang sama dapat tertimpa.

### 4. Siapkan foto katalog awal

Folder `media/` tidak ikut GitHub. Foto awal tersedia di
`menu/assets/recovered-menu/`; salin ke lokasi yang dirujuk fixture:

```powershell
New-Item -ItemType Directory -Path media/menu/detail -Force | Out-Null

"ayam-geprek", "nasi-goreng", "kentang-goreng", "es-jeruk" | ForEach-Object {
    Copy-Item "menu/assets/recovered-menu/$_.webp" "media/menu/"
}

Copy-Item "menu/assets/recovered-menu/ayam-detail.webp" "media/menu/detail/"
```

Langkah ini untuk instalasi baru. Foto upload/menu tambahan milik anggota lain
tidak otomatis tersedia; pindahkan backup database dan media bersama.

### 5. Periksa dan jalankan web

```powershell
python -B manage.py check
python -B manage.py runserver 127.0.0.1:8890 --noreload
```

Berhasil jika pemeriksaan tidak menemukan masalah dan terminal menampilkan
alamat server `http://127.0.0.1:8890/`.
Biarkan terminal tetap berjalan. Untuk berhenti, tekan `Ctrl+C`.

Alternatif setelah lingkungan Python aktif: `.\start.ps1`.
Untuk port lain: `.\start.ps1 -Port 8892`. Karena memakai `--noreload`, restart
server setelah mengubah kode Python.

## Alamat yang dibuka

| Pengguna | Alamat | Login? |
|---|---|---|
| Pelanggan | http://127.0.0.1:8890/ | Tidak |
| Chatbot | http://127.0.0.1:8890/chatbot/ | Tidak |
| Login staf/kasir | http://127.0.0.1:8890/staff/login/ | Ya |
| CMS staf | http://127.0.0.1:8890/staff/ | Akun staf |
| Kasir | http://127.0.0.1:8890/kasir/ | Akun staf atau grup `Cashier` |
| Django Admin | http://127.0.0.1:8890/admin/ | Akun admin yang sesuai |

Gunakan akun yang dibuat pada langkah 3 untuk penyiapan pertama. Cara membuat
akun staf/kasir dan menguji satu pesanan ada di [panduan penggunaan](docs/PANDUAN_PENGGUNAAN.md).

## Menjalankan lagi di hari berikutnya

```powershell
cd pemesanan-makanan-digital
.\.venv\Scripts\Activate.ps1
.\start.ps1
```

Tidak perlu mengulang clone, membuat database, memuat fixture, atau membuat akun.
Setiap laptop memakai database sendiri. Pesanan di laptop A tidak otomatis
muncul di laptop B walaupun memakai repository yang sama.

## Memperbarui proyek yang sudah ada

1. Hentikan server. Cadangkan `db.sqlite3` dan `media/` ke folder lain.
2. Jalankan `git status`. Simpan atau selesaikan perubahan lokal sebelum
   berpindah branch atau menarik perubahan; jangan memakai reset/clean untuk memaksanya.
3. Jika folder kerja sudah bersih, jalankan:

   ```powershell
   git switch ahmad
   git pull --ff-only origin ahmad
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   python -B manage.py showmigrations
   python -B manage.py migrate
   python -B manage.py check
   .\start.ps1
   ```

4. Jika pull gagal karena riwayat bercabang atau konflik, selesaikan bersama
   pemilik perubahan. Jangan menggunakan force-push.

Pada pembaruan, **jangan menjalankan `loaddata`, `seed_demo`, atau menyalin foto
awal di atas foto yang sudah diedit**. Migrasi mengubah struktur tabel; fixture
mengisi data katalog. Keduanya berbeda.

## Konfigurasi yang perlu diketahui

| File/folder | Kegunaan |
|---|---|
| `v1_settings.py` | Konfigurasi bawaan untuk menjalankan `manage.py` secara lokal. |
| `config/settings.py` | Profil terpisah, misalnya untuk persiapan deployment; bukan default `manage.py` lokal. |
| `db.sqlite3` | Katalog, akun, pesanan, dan sesi lokal. Tidak masuk Git. |
| `media/`, `private/menu-originals/` | Foto upload dan arsip foto asli. Tidak masuk Git. |
| `.local-secret-key` | Rahasia development lokal yang dibuat otomatis. Jangan dibagikan. |
| `.env`, `local_gemini_settings.py` | Konfigurasi Gemini opsional per laptop. Tidak diperlukan untuk mode lokal dan tidak masuk Git. |

Mode lokal memakai `GEMINI_ENABLED=False`. Pemasangan SDK `google-genai` tidak
otomatis mengirim pesan ke Gemini. Jika konfigurasi Gemini aktif dan tersedia,
chatbot memakai alur **AI-first** dari `main`: Gemini menangani percakapan dan
meminta fakta menu melalui fungsi Django. Mode lokal menjadi fallback.
Alurnya dijelaskan di
[panduan pengembangan](docs/PANDUAN_PENGEMBANGAN.md#8-chatbot-lokal-dan-hybrid).

Contoh nama variabel tanpa rahasia tersedia di [.env.example](.env.example).
File tersebut bukan konfigurasi siap pakai: secret, URL cache, model, dan key
masih kosong. Mode lokal default tidak perlu menyalinnya. Profil
settings dapat memuat `.env` melalui `python-dotenv`, dengan environment proses
yang sudah ada tetap didahulukan;
ikuti [panduan hosting](docs/PANDUAN_VERIFIKASI_HOSTING.md) bila menyiapkan server.

## Membagikan source ke anggota tim

Utamakan clone atau pembaruan melalui Git sesuai langkah di atas. Jika perlu
mengirim ZIP, gunakan snapshot commit yang sudah diperiksa:

```powershell
git archive --format=zip --output=../rasakita-source.zip HEAD
```

Perintah tersebut hanya memasukkan file pada commit terakhir; perubahan yang
belum dicommit tidak ikut. Jangan mengirim ZIP seluruh folder kerja karena
database, foto privat, `.env`, dan lingkungan Python bukan bagian source tim.
Data restoran yang memang perlu dipindahkan ditangani terpisah oleh pemiliknya.

## Jika mengalami kendala

| Gejala | Langkah awal |
|---|---|
| `No module named django` | Aktifkan `.venv` dan pasang requirements melalui Python yang sama. |
| Migrasi belum diterapkan atau tabel alias tidak ditemukan | Cadangkan data, lalu jalankan `showmigrations` dan `migrate`. |
| Menu kosong pada instalasi baru | Periksa apakah fixture berhasil dimuat pada database baru yang sama. |
| Menu tampil tetapi fotonya hilang | Periksa langkah 4 dan file di `media/menu/`. |
| Tidak bisa login | Gunakan akun sendiri; tidak ada akun/password demo otomatis. |
| Port sudah dipakai | Gunakan port lain dan sesuaikan alamat browser. |
| Kamera QR tidak tersedia | Baca [catatan QR](docs/PANDUAN_PENGGUNAAN.md#4-makan-di-tempat-dan-qr-meja). |

## Dokumentasi lanjutan

- [Modul belajar OOP](docs/oop/README.md): konsep dasar, contoh proyek, dan latihan tim.
- [Penjelasan sistem chatbot](docs/Chatbot.md): perjalanan pesan, konteks, budget, dan peran AI.
- [Pengembangan](docs/PANDUAN_PENGEMBANGAN.md): struktur kode, model, endpoint,
  OOP, chatbot, dan cara mengubah fitur.
- [Penggunaan](docs/PANDUAN_PENGGUNAAN.md): pelanggan, staf, kasir, akun, dan simulasi.
- [CMS/Admin](docs/PANDUAN_CMS_ADMIN.md): rincian layar dan form pengelolaan.
- [Pemeriksaan lokal](docs/PANDUAN_TESTING_LOKAL.md) dan
  [verifikasi hosting](docs/PANDUAN_VERIFIKASI_HOSTING.md).
- [Indeks seluruh panduan](docs/README.md).

## Perilaku terbaru dan bahan pembelajaran

Jumlah keranjang pelanggan divalidasi 1–99 per baris, termasuk penggabungan.
Logout operator melalui tombol POST + CSRF. Parser unggahan hanya JPEG/PNG/WebP.
Checkout mempertahankan transaksi atomic serta audit sambil mengurangi agregasi
total berulang. Perubahan ini tidak membutuhkan migrasi schema baru.

Jika Gemini aktif, membuka halaman chatbot atau menekan Mulai Lagi dapat
memanggil API untuk sapaan. Kuota dan log token mencakup setiap dispatch serta
putaran tool. Log JSON muncul di terminal server, dengan timestamp UTC; log
akses lokal memakai WITA. Sapaan lokal tanpa API belum diterapkan.

[Modul OOP](docs/oop/README.md) sekarang memakai nama berkas `1. ...` sampai
`10. ...`. Tujuh modul utama berisi 35 pembahasan, lima berkas nyata berbeda
pada setiap modul. Panduan menjalankan tes dummy dan batas hasil regresi ada di
[pemeriksaan lokal](docs/PANDUAN_TESTING_LOKAL.md); riwayat security ada di
[SECURITY-TRANSFER.md](docs/SECURITY-TRANSFER.md).
