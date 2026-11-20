# Mode Showcase (testing/)

Menjalankan aplikasi lengkap seperti sudah beroperasi: menu berfoto, varian, add-on, meja,
akun staf, dan pesanan di semua status. Semua data disimpan di `testing/.data/`
(diabaikan git), sehingga `db.sqlite3` dan `media/` asli tidak pernah tersentuh.

## Menjalankan

```powershell
.\testing\run.ps1            # bangun ulang dari nol, lalu jalankan di port 8894
.\testing\run.ps1 -Keep      # pakai data showcase yang sudah ada
.\testing\run.ps1 -NoOrders  # katalog saja, tanpa contoh pesanan
.\testing\run.ps1 -Port 8895
```

| Halaman | URL | Akun |
|---|---|---|
| Pelanggan | http://127.0.0.1:8894/ | – |
| CMS staf | http://127.0.0.1:8894/staff/ | `admin` / `admin12345` |
| Kasir | http://127.0.0.1:8894/kasir/ | `cashier` / `cashier12345` |

Chatbot memakai pengaturan Gemini dari `.env` seperti mode lokal biasa.

## Isi data

- 4 kategori (Makanan, Minuman, Camilan, Penutup), 19 menu, 7 add-on, 8 meja.
- Pesanan contoh lewat `orders/services.py`: 3 menunggu bayar, 2 lunas (tunai, QRIS),
  1 dibatalkan, 1 refund, 1 kedaluwarsa.
- Kasus uji tampilan kartu menu:

| Menu | Yang diuji |
|---|---|
| Nasi Campur Bali | foto buram (tanpa transparansi), lanskap |
| Rawon Daging | foto buram, potret |
| Tahu Tempe Penyet | gambar panorama 4:1 |
| Es Teler Jumbo | gambar sangat tinggi 1:4 |
| Bakwan Sayur | SVG hanya dengan `viewBox` |
| Tempe Mendoan | tanpa foto (placeholder) |
| Paket Nasi Liwet … | nama sangat panjang, harga 7 digit, semua add-on |
| Martabak Manis | stok habis (tidak boleh tampil di menu pelanggan) |

## Struktur

- `settings.py` – mewarisi `v1_settings`, mengganti database, media, dan nama cookie.
- `catalog.py` – data menu (ubah di sini untuk menambah menu uji).
- `seeding.py` – kelas penulis data; `ShowcaseGuard` menolak berjalan di luar `testing/.data/`.
- `management/commands/seed_showcase.py` – perintah seeder, hanya terdaftar di
  `--settings=testing.settings`.
- `svg/` – gambar uji sederhana. SVG disalin langsung ke media karena pipeline unggah
  foto (Pillow) tidak membaca SVG; aplikasi hanya memakai URL-nya.
