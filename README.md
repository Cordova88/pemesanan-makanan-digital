# Pemesanan Makanan Digital

Backend Django/SQLite untuk pemesanan tanpa akun pelanggan. Harga dan pilihan menu selalu divalidasi server-side; keranjang browser bukan sumber data final.

## Jalankan

1. Buat virtual environment dan aktifkan, lalu `pip install -r requirements.txt`.
2. Salin `.env.example` menjadi `.env` bila belum ada. SQLite otomatis membuat file `db.sqlite3`; tidak perlu membuat database atau menjalankan server database di Laragon.
3. Jalankan `python manage.py migrate`, `python manage.py seed_demo`, dan `python manage.py runserver`.
4. Jalankan `python manage.py expire_orders` secara periodik (mis. setiap menit melalui Task Scheduler/cron) untuk mematerialkan status EXPIRED. Pembayaran juga memeriksa expiry secara atomik.

Endpoint publik: `GET /api/menu/`, `POST /api/orders/checkout/`, `GET /api/orders/<public_id>/`.
Endpoint kasir memerlukan login Django serta group `Cashier` (atau admin): tambah item, ubah kuantitas, data pelanggan, bayar, dan batalkan. Refund hanya `is_staff` admin.

## Siklus dan aturan penting

`PENDING → PAID/CANCELLED/EXPIRED`, lalu `PAID → REFUNDED`. Payment/refund/edit menggunakan `transaction.atomic()` dan `select_for_update()`. `OrderItem`, variant, dan add-on menyimpan snapshot harga/nama sehingga perubahan menu tidak mengubah transaksi lama. Referensi publik non-sekuensial dipakai untuk QR lookup (QR dapat mengenkode `public_id`).

SQLite cocok untuk development atau demonstrasi satu-kasir. Karena SQLite tidak mendukung row lock `SELECT ... FOR UPDATE` seperti PostgreSQL, gunakan PostgreSQL sebelum deployment dengan banyak kasir yang membayar pesanan secara bersamaan.

## Tes

Jalankan `python manage.py test`. Django akan membuat database SQLite test sementara secara otomatis.

> phpMyAdmin tidak dapat membuka SQLite. Gunakan Django Admin di `/admin/`, atau aplikasi SQLite browser seperti DB Browser for SQLite, untuk melihat file database.
