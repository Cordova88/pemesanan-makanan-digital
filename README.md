# Pemesanan Makanan Digital V1

V1 adalah acuan pengembangan berikutnya, berdasarkan hasil fase 1–15 hingga
17 Oktober 2026. Folder `pemesanan-makanan-digital-figma` menjadi arsip pekerjaan
sebelumnya. Kerjakan perubahan baru dari folder v1 ini.

Panduan penggunaan fitur CMS dan Django Admin:
[docs/PANDUAN_CMS_ADMIN.md](docs/PANDUAN_CMS_ADMIN.md).

Panduan pengujian dan persiapan hosting:

- [Pengujian lokal, mode tanpa API, serta konfigurasi Gemini/.env opsional](docs/PANDUAN_TESTING_LOKAL.md).
- [Verifikasi staging/hosting dan rencana pemantauan](docs/PANDUAN_VERIFIKASI_HOSTING.md).

## Menjalankan

Dari folder ini, dengan Python dan dependency requirements.txt yang tersedia:

```powershell
python -B manage.py runserver 127.0.0.1:8890 --noreload
```

Atau:

```powershell
.\start.ps1
```

- Pelanggan: http://127.0.0.1:8890/
- CMS: http://127.0.0.1:8890/staff/
- Django Admin: http://127.0.0.1:8890/admin/
- Kasir: http://127.0.0.1:8890/kasir/

Database awal hanya memuat katalog asli: 4 menu, kategori, tag, varian, dan
tambahan beserta fotonya. Akun, meja, pesanan, pembayaran, log, dan data uji fase
tidak dibawa. Buat akun admin sendiri melalui terminal interaktif:

```powershell
python -B manage.py createsuperuser
```

Masukkan username/password pilihan Anda pada prompt terminal. Akun staf yang
dibuat melalui createsuperuser dapat masuk ke CMS dan Django Admin.

## Instalasi pada lingkungan baru

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -B manage.py migrate
python -B manage.py loaddata v1_catalog
python -B manage.py createsuperuser
.\start.ps1
```

Fixture `menu/fixtures/v1_catalog.json` adalah katalog awal, bukan akun demo.
Jalankan loaddata saat menyiapkan database baru; mengulangnya dapat menimpa
perubahan katalog pada ID yang sama. Server tidak memuat ulang fixture otomatis.
Foto katalog tersedia di `media/menu/`. Backup database dan media bersama.

## Konfigurasi

manage.py secara default memakai `v1_settings.py`, profil pengembangan lokal
yang mandiri. Database: db.sqlite3; foto: media/; arsip upload:
private/menu-originals/. Cookie sesi khusus v1.

Secret development dibuat lokal secara otomatis dalam `.local-secret-key` yang
diabaikan Git, sehingga sesi login bertahan saat server direstart. Berkas tersebut
dan `.env` tidak perlu dibuka/dibagikan. Tidak ada kredensial lama yang dibawa.
Integrasi Gemini dinonaktifkan pada profil lokal. Host lokal yang diizinkan:
127.0.0.1, localhost, testserver. QR mengikuti alamat server yang sedang dibuka.

`config/settings.py`, ASGI dan WSGI tetap tersedia untuk konfigurasi deployment
terpisah; profil v1 lokal ini bukan konfigurasi production. Untuk profil lain,
pilih `--settings` secara eksplisit. Hindari menjalankan dari folder arsip.

## Pemeriksaan

```powershell
python -B manage.py check
python -B manage.py test --noinput
```

Struktur: menu (katalog), cart (keranjang), orders (pesanan/QR/transaksi), users
(CMS/kasir), recommendation (chatbot), config (URL/profil deployment).
Tests dan migrations dipertahankan sebagai bagian source pengembangan.
Konfigurasi dan data lokal tidak termasuk dokumentasi yang dipindahkan.

Ringkasan penyiapan dan hasil verifikasi: [docs/V1_BASELINE.md](docs/V1_BASELINE.md).


## Struktur pengujian

Seluruh pengujian berada di paket `tests/` masing-masing aplikasi: `menu`,
`cart`, `orders`, `users`, dan `recommendation`. File `tests.py` sebelumnya
menjadi `tests/test_core.py`; pengujian fitur tetap memakai nama `test_*.py`.
Django menemukan semua modul tersebut secara otomatis. Contoh dari folder v1:

```powershell
python -B manage.py test menu cart orders users recommendation --noinput
python -B manage.py test menu.tests.test_selection --noinput
```

Pengujian otomatis menggunakan database test. Untuk verifikasi tanpa membaca
kredensial lokal dan dengan media sementara, dari folder workspace jalankan:

```powershell
python -B output/ai-v2-phase7/run_tests.py menu cart orders users recommendation
```

Catatan penataan pengujian dan riwayat pengembangan tersedia di
[arsip pengembangan](../output/pengembangan/README.md).
Panduan aktif dirangkum di [docs/README.md](docs/README.md).
