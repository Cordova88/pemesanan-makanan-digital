# Pemesanan Makanan Digital

Aplikasi pemesanan makanan berbasis Django untuk katalog restoran, keranjang sesi, checkout, pemesanan meja melalui QR, pengelolaan kasir, dan rekomendasi menu melalui chatbot berbahasa Indonesia.

Panduan onboarding frontend/backend yang lebih rinci tersedia di [docs/PANDUAN_PENGEMBANGAN.md](docs/PANDUAN_PENGEMBANGAN.md).

## Prasyarat

- Python 3.12 atau lebih baru.
- `pip` untuk memasang dependensi dari `requirements.txt`.
- Git untuk mengambil kode sumber.
- Browser modern. Koneksi internet diperlukan agar Bootstrap dan pustaka pemindai QR yang dimuat dari CDN dapat digunakan.
- SQLite sudah menjadi basis data bawaan untuk pengembangan lokal. Tidak perlu memasang Laragon, MySQL, atau server basis data terpisah.

## Menjalankan secara lokal

Contoh berikut menggunakan PowerShell di Windows. Jalankan dari folder proyek:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Buka `http://127.0.0.1:8000/` untuk katalog dan `http://127.0.0.1:8000/chatbot/` untuk chatbot. Perintah pengelolaan staf tersedia di `/staff/`, sedangkan Django Admin tersedia di `/admin/`.

Untuk Linux atau macOS, buat dan aktifkan lingkungan virtual dengan:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Kemudian jalankan langkah pemasangan dependensi dan perintah `manage.py` yang sama.

Database SQLite `db.sqlite3` dibuat di folder proyek setelah migrasi. `seed_demo` mengisi data contoh menu, kategori, tag, varian, add-on, meja, dan akun staf development. Akun awal demo adalah `admin` / `admin12345` dan `cashier` / `cashier12345`; gunakan hanya untuk development dan ubah sebelum pemakaian yang lebih luas.

Pengaturan dibaca dari variabel lingkungan proses (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, dan `SQLITE_DATABASE_NAME`). Berkas `.env.example` hanya contoh nilai—proyek tidak memuat berkas `.env` secara otomatis. Nilai bawaan `SECRET_KEY` hanya untuk development. Untuk deployment, atur rahasia sendiri, set `DEBUG=false`, sesuaikan `ALLOWED_HOSTS`, lalu jalankan `python manage.py collectstatic` dan sajikan berkas statis melalui web server atau CDN.

Jalankan `python manage.py expire_orders` secara berkala, misalnya setiap menit menggunakan Task Scheduler atau cron, untuk memperbarui status pesanan kedaluwarsa.

## Ikhtisar sistem

Aplikasi adalah satu proyek Django dengan SQLite sebagai penyimpanan development:

- `menu`: kategori, item menu, tag, grup/opsi varian, add-on, katalog, dan perintah `seed_demo`.
- `cart`: keranjang sesi yang menyimpan ID pilihan; harga selalu dihitung dari data server.
- `orders`: checkout, snapshot item dan harga, status pesanan, QR meja, pembayaran, pembatalan, refund, dan pencatatan audit.
- `users`: login staf dan halaman pengelolaan untuk kasir/admin.
- `recommendation`: halaman chatbot, ekstraksi preferensi, suasana hati, pemeringkatan menu, dan integrasi ke keranjang yang sudah ada.
- `config`: konfigurasi Django, URL utama, middleware, sesi, dan database.

### Alur pemesanan

```text
Katalog atau chatbot
        ↓
MenuItem + varian + add-on
        ↓
CartService → keranjang berbasis sesi
        ↓
checkout → OrderService → Order dan snapshot harga
        ↓
konfirmasi pesanan / alur kasir
```

Chatbot tidak memiliki keranjang, pesanan, atau sesi percakapan persisten tersendiri. Preferensi sementara dan riwayat menu yang sudah ditampilkan disimpan di sesi Django, sedangkan pilihan menu tetap masuk melalui `CartService` yang dipakai storefront.

### Arsitektur rekomendasi chatbot

Chatbot sepenuhnya rule-based: tidak memakai LLM, layanan AI eksternal, machine learning, embeddings, atau pencarian vektor.

```text
Pesan pelanggan
  ├─ TagExtractor → preferensi menu langsung dan pantangan
  ├─ MoodExtractor → suasana atau situasi
  └─ MoodResolver → karakteristik menu yang sesuai suasana
                    ↓
              Preferences
                    ↓
         RecommendationService
                    ↓
           ChatbotService
                    ↓
      kartu rekomendasi → CartService
```

- `language.py` berisi normalisasi bahasa informal, parser nominal Rupiah, dan kamus terpusat label tag berbahasa Indonesia.
- `TagExtractor` mengenali selera, bahan, jenis makanan, kategori, batas harga, serta larangan atau ketidaksukaan.
- `MoodExtractor` mengenali situasi seperti lelah, suasana hati kurang baik, sangat lapar, gerah/haus, terburu-buru, dan kebingungan.
- `MoodResolver` memetakan suasana tersebut ke karakteristik menu, misalnya suasana lelah ke makanan mengenyangkan dan makanan yang terasa nyaman.
- `Preferences` menyimpan tag positif, tag hasil suasana, tag yang dikecualikan, harga maksimum, kategori, dan suasana sebagai data terstruktur di sesi.
- `RecommendationService` menyaring menu nonaktif/tidak tersedia, menerapkan batas harga dan pantangan, kemudian mengurutkan hasil secara deterministik.
- `ChatbotService` mengelola pertanyaan lanjutan, respons kontekstual, pilihan cepat, “Cari Menu Lain”, dan “Mulai Lagi”.

Pemeringkatan dapat dijelaskan melalui bobot: kecocokan tag langsung `+4`, karakteristik hasil suasana `+2`, kategori `+3`, dan kecocokan anggaran `+3`. Preferensi harga terjangkau tanpa nominal memakai batas relatif yang eksplisit sebesar Rp15.000. Pantangan tegas mengecualikan item; ketidaksukaan yang lebih lunak mengurangi skor. Skor hanya digunakan untuk pengurutan—pelanggan melihat alasan kecocokan dalam label Indonesia, bukan angka skor atau ID tag internal.

### Endpoint utama

- `GET /api/menu/`: katalog menu.
- `GET /api/cart/`: isi keranjang sesi.
- `POST /api/cart/add/`: menambahkan item; `PATCH` atau `DELETE /api/cart/<line_id>/`: mengubah/menghapus baris keranjang; `DELETE /api/cart/clear/`: mengosongkan keranjang.
- `POST /api/orders/checkout/`: membuat pesanan dari keranjang.
- `GET /orders/<public_id>/`: halaman konfirmasi pesanan.
- `POST /api/recommendation/chat/`: mengirim pesan dan menerima balasan/rekomendasi.
- `POST /api/recommendation/add/`: menambahkan rekomendasi beserta varian/add-on ke keranjang yang sama.
- Endpoint staf berada di bawah `/staff/`; Django Admin berada di `/admin/`.

## Frontend storefront

Template `menu/templates/menu/storefront.html` memuat markup halaman. Aset statisnya berada di `menu/static/menu/`:

- `css/storefront.css`: gaya storefront.
- `js/storefront.mjs`: inisialisasi dan penghubung fitur.
- `js/state.mjs`: state halaman dan konteks meja.
- `js/api.mjs`: request JSON, CSRF, format harga, dan notifikasi.
- `js/menu.mjs`: katalog, pencarian, kategori, dan pemilihan item.
- `js/cart.mjs`: keranjang sesi.
- `js/table-scanner.mjs`: pemindaian QR meja.
- `js/checkout.mjs`: validasi dan pengiriman checkout.

Template chatbot berada di `recommendation/templates/recommendation/chatbot.html`. UI merender teks dengan DOM API yang aman dan meneruskan konfigurasi item ke endpoint rekomendasi, tanpa membuat alur keranjang terpisah.

## Tes dan pemeriksaan

```bash
python manage.py check
python manage.py test
```

Django membuat database SQLite sementara untuk test. Pengujian mencakup aturan bahasa dan harga chatbot, rekomendasi dan pantangan, sesi percakapan, data demo, serta integrasi rekomendasi → varian/add-on → keranjang → checkout.

## Catatan deployment

Jangan gunakan `SECRET_KEY` bawaan atau akun demo pada deployment. Atur `SECRET_KEY`, `DEBUG=false`, dan `ALLOWED_HOSTS` melalui environment deployment. SQLite sesuai untuk development atau demonstrasi dengan beban rendah; gunakan PostgreSQL untuk deployment dengan beberapa kasir yang dapat membayar pesanan bersamaan karena SQLite tidak menyediakan row lock `SELECT ... FOR UPDATE` seperti PostgreSQL.

PHPMyAdmin tidak membuka SQLite. Untuk memeriksa `db.sqlite3`, gunakan Django Admin atau aplikasi seperti DB Browser for SQLite.
