# Panduan Pengembangan RasaKita

Dokumen ini adalah peta kerja untuk pengembang frontend dan backend. Tujuannya menjelaskan lokasi kode, batas tanggung jawab, aliran data, endpoint, struktur model, dan tempat yang perlu diubah ketika menambahkan fitur.

> Dokumen ini menjelaskan implementasi yang ada saat ini, bukan rancangan ideal. Untuk kontrak endpoint terbaru, periksa URL dan view yang disebut pada tiap bagian. Bila dokumentasi dan kode berbeda, kode yang berjalan adalah sumber kebenaran.

## Daftar isi

1. [Ringkasan sistem](#1-ringkasan-sistem)
2. [Menjalankan proyek](#2-menjalankan-proyek)
3. [Peta repositori](#3-peta-repositori)
4. [Arsitektur request Django](#4-arsitektur-request-django)
5. [Model dan relasi data](#5-model-dan-relasi-data)
6. [Storefront dan frontend](#6-storefront-dan-frontend)
7. [Kontrak API](#7-kontrak-api)
8. [Alur keranjang dan checkout](#8-alur-keranjang-dan-checkout)
9. [QR meja](#9-qr-meja)
10. [CMS, admin, dan akses staf](#10-cms-admin-dan-akses-staf)
11. [Chatbot rekomendasi](#11-chatbot-rekomendasi)
12. [Order dan aturan transaksi](#12-order-dan-aturan-transaksi)
13. [Seed, migrasi, dan data demo](#13-seed-migrasi-dan-data-demo)
14. [Tes dan panduan perubahan](#14-tes-dan-panduan-perubahan)
15. [Batasan implementasi yang perlu diketahui](#15-batasan-implementasi-yang-perlu-diketahui)

## 1. Ringkasan sistem

RasaKita adalah satu proyek Django modular (monolith), bukan sistem microservice.

```text
Browser
  ├─ Storefront ──────────────┐
  ├─ Chatbot rekomendasi ─────┼── HTTP/JSON + HTML ──> Django
  ├─ CMS staf ────────────────┤                         ├─ Views
  └─ Konfirmasi pesanan ──────┘                         ├─ Services
                                                        ├─ Models/ORM
                                                        ├─ Django session
                                                        └─ SQLite (lokal)
```

Peran lapisan:

| Lapisan | Lokasi umum | Tanggung jawab |
|---|---|---|
| URL routing | `config/urls.py`, `<app>/urls.py` | Mengarahkan alamat dan metode HTTP ke view. |
| Template / frontend | `<app>/templates/`, `menu/static/menu/` | Menampilkan UI dan mengirim request. |
| View | `<app>/views.py` | Membaca request, memvalidasi format dasar, memanggil layanan, membentuk respons. |
| Service/domain logic | `cart/services.py`, `orders/services.py`, `recommendation/services/` | Aturan bisnis yang dapat dipakai lintas view. |
| Model/ORM | `<app>/models.py` | Skema data, relasi, constraint, dan query database. |
| Migrasi | `<app>/migrations/` | Riwayat perubahan skema database. |

Konfigurasi utama ada di `config/settings.py`: aplikasi, middleware sesi dan CSRF, template, bahasa `id`, zona waktu `Asia/Makassar`, static files, serta SQLite lokal. URL akar proyek berada di `config/urls.py`.

## 2. Menjalankan proyek

Prasyarat dan langkah setup rinci juga tersedia di `README.md`. Untuk Windows PowerShell dari folder proyek:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Alamat lokal:

- `http://127.0.0.1:8000/` — storefront pelanggan.
- `http://127.0.0.1:8000/chatbot/` — chatbot.
- `http://127.0.0.1:8000/staff/login/` — login staf/CMS admin.
- `http://127.0.0.1:8000/admin/` — Django Admin.

Database lokal default adalah `db.sqlite3` di root proyek. Pengaturan dibaca dari environment proses, bukan `.env` otomatis. Nama variabel yang digunakan: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `SQLITE_DATABASE_NAME`. SQLite tidak perlu server terpisah.

`seed_demo` dapat membuat admin `admin` dan kasir `cashier` untuk development. Password awal hanya dipasang saat user belum punya password yang dapat digunakan; command tidak mereset password user yang sudah ada.

## 3. Peta repositori

```text
config/                         konfigurasi proyek Django dan URL root
menu/                           katalog, menu, tag, varian, add-on, seed demo
  models.py                     Category, MenuItem, MenuTag, Variant*, AddOn
  views.py                      shell storefront dan API katalog
  urls.py                       GET /api/menu/
  templates/menu/               HTML storefront
  static/menu/css/              CSS storefront
  static/menu/js/               modul JavaScript storefront
  management/commands/seed_demo.py
cart/                           endpoint dan service keranjang sesi
orders/                         model, view, service, aturan transaksi pesanan
  management/commands/expire_orders.py
  templates/orders/             halaman konfirmasi
recommendation/                 API dan UI chatbot rekomendasi
  services/                     aturan bahasa, suasana hati, ranking, percakapan
  templates/recommendation/     halaman chatbot
users/                          login staf dan CMS custom
  forms.py                      ModelForm CMS
  templates/users/              layout, navigasi, dan halaman CMS
manage.py                       CLI Django
requirements.txt                dependensi Python
README.md                       setup ringkas dan overview
docs/PANDUAN_PENGEMBANGAN.md    panduan detail ini
```

### File paling sering dicari

| Ingin mengubah... | Mulai dari... |
|---|---|
| Konten/layout katalog | `menu/templates/menu/storefront.html` |
| Gaya storefront | `menu/static/menu/css/storefront.css` |
| Perilaku pencarian/kategori/pilih menu | `menu/static/menu/js/menu.mjs` |
| Tampilan dan request keranjang | `menu/static/menu/js/cart.mjs` |
| Checkout dan validasi jenis order | `menu/static/menu/js/checkout.mjs` |
| QR meja dan kamera | `menu/static/menu/js/table-scanner.mjs` |
| Request JSON/CSRF/harga | `menu/static/menu/js/api.mjs` |
| API data katalog | `menu/views.py`, `menu/urls.py` |
| Aturan keranjang | `cart/services.py`; HTTP adapter: `cart/views.py` |
| Aturan membuat/mengubah order | `orders/services.py`; HTTP adapter: `orders/views.py` |
| Tampilan konfirmasi | `orders/templates/orders/confirmation.html` |
| Bahasa/tag chatbot | `recommendation/services/language.py`, `tag_extractor.py` |
| Deteksi suasana chatbot | `recommendation/services/mood_extractor.py`, `mood_resolver.py` |
| Ranking rekomendasi | `recommendation/services/recommendation.py` |
| State/dialog chatbot | `recommendation/services/chatbot.py` |
| Kartu dan interaksi chatbot | `recommendation/templates/recommendation/chatbot.html` |
| Desain dasar CMS | `users/templates/users/base.html` |
| Menu navigasi CMS | `users/templates/users/nav.html` |
| Dashboard CMS | `users/templates/users/dashboard.html`, `users/views.py` |
| Form CMS | `users/forms.py`, lalu template terkait |
| Skema database | `<app>/models.py`, kemudian migrasi |

## 4. Arsitektur request Django

`config/urls.py` memetakan URL tingkat proyek:

| Prefix/alamat | Tujuan |
|---|---|
| `/` | `menu.views.storefront` |
| `/orders/<public_id>/` | shell halaman konfirmasi dari `orders.views.confirmation` |
| `/admin/` | Django Admin |
| `/staff/` | `users.urls` |
| `/api/menu/` | `menu.urls` |
| `/api/cart/` | `cart.urls` |
| `/api/orders/` | `orders.urls` |
| `/api/recommendation/` | `recommendation.urls` |
| `/chatbot/` | `recommendation.urls_page` |

Alur tipikal request:

```text
Browser fetch/form
  → config/urls.py
  → app urls.py
  → view menerima HttpRequest
  → service menjalankan aturan bisnis / ORM
  → view membentuk JsonResponse atau render(template)
  → Browser merender hasil
```

Untuk request JSON dari browser, frontend storefront memakai `api()` di `menu/static/menu/js/api.mjs`, yang mengirim `Content-Type: application/json` dan header `X-CSRFToken`. Chatbot memiliki helper request sendiri di template chatbot dan juga mengirim CSRF. Jangan menghapus middleware CSRF atau mengandalkan validasi harga dari browser.

## 5. Model dan relasi data

### Katalog (`menu/models.py`)

```text
Category 1 ───── * MenuItem * ───── * MenuTag
                         │
                         ├── 1 ── * VariantGroup 1 ── * VariantOption
                         │
                         └──────── * AddOn (many-to-many menu_items)
```

- `Category`: nama unik dan status aktif.
- `MenuItem`: kategori, nama, deskripsi, harga, gambar, `is_active`, `is_available`, `stock_estimate`; dapat memiliki banyak tag.
- `MenuTag`: slug internal unik (`name`) dan label tampilan opsional (`display_name`).
- `VariantGroup`: milik satu menu; memiliki nama, status aktif, urutan, dan apakah pilihannya wajib.
- `VariantOption`: milik satu grup; nama dan penyesuaian harga.
- `AddOn`: nama, harga, status aktif/tersedia; relasi many-to-many ke menu yang mengizinkan add-on.

API katalog hanya mengeluarkan item yang aktif, tersedia, dan kategorinya aktif.

### Transaksi (`orders/models.py`)

```text
Table 1 ───── * Order 1 ───── * OrderItem
                                ├── * OrderItemVariant
                                └── * OrderItemAddOn
Order 1 ───── 0..1 Payment
Order 1 ───── * AuditLog
```

- `Table` mempunyai nomor dan token QR unik.
- `Order` memiliki `public_id`, status, pelanggan, jenis dine-in/takeaway, meja opsional, total, expiry, serta aktor pembayaran/pembatalan/refund.
- `OrderItem`, `OrderItemVariant`, dan `OrderItemAddOn` menyimpan snapshot nama/harga transaksi agar perubahan menu tidak mengubah transaksi lama.
- `Payment` mencatat satu pembayaran per order.
- `AuditLog` menyimpan aksi serta nilai before/after/metadata.

Constraint database dan `clean()` menjaga konsistensi jenis order-meja, nilai harga/kuantitas nonnegatif/positif, serta relasi unik tertentu. Detail final constraint ada di `orders/models.py`.

### Data sesi

Database menyimpan data katalog dan pesanan. Sesi Django menyimpan data sementara per browser:

- `cart`: baris keranjang berupa ID menu, jumlah, ID varian, ID add-on.
- `recommendation_state`: state percakapan chatbot dan preferensi terstruktur.
- `recommendation_shown`: ID menu rekomendasi yang sudah diperlihatkan.

Storefront juga menyimpan konteks QR meja sementara di `sessionStorage` browser (key `restaurant_table_context`, maksimal umur dua jam). Ini bukan pengganti validasi token oleh server.

## 6. Storefront dan frontend

### Halaman dan inisialisasi

`menu/views.py` merender `menu/templates/menu/storefront.html`; halaman memuat CSS dan entry module `storefront.mjs`. `storefront.mjs` memasang event handler untuk menu, cart, checkout, dan QR, lalu:

1. Memastikan konteks meja jika URL berisi `?table=<token>`.
2. Mengambil katalog dari `/api/menu/`.
3. Merender katalog.
4. Mengambil keranjang dari `/api/cart/`.

### Pembagian JavaScript

| Modul | Fungsi |
|---|---|
| `state.mjs` | State halaman: katalog, keranjang, menu terpilih, kategori, meja, scanner. |
| `api.mjs` | JSON fetch, CSRF, pemformatan Rupiah, toast. |
| `menu.mjs` | Kategori dan pencarian di sisi browser; modal detail menu; pilihan varian/add-on/jumlah. |
| `cart.mjs` | Render cart, ubah jumlah, hapus baris, tambah pilihan. |
| `checkout.mjs` | Mengirim checkout dan mengarahkan ke halaman konfirmasi. |
| `table-scanner.mjs` | Baca QR meja, validasi token ke server, simpan konteks, atur dine-in/takeaway. |
| `storefront.mjs` | Menghubungkan modul dan inisialisasi data halaman. |

Pencarian saat ini dilakukan di browser atas nama menu yang sudah dimuat—bukan query parameter pada API. DOM katalog dan keranjang dibangun menggunakan DOM API dan `textContent`.

## 7. Kontrak API

Semua URL di bawah relatif terhadap host aplikasi. JSON request mesti dikirim dengan `Content-Type: application/json`; untuk request yang mengubah data gunakan mekanisme CSRF Django saat dikirim dari browser.

### Katalog

`GET /api/menu/`

Contoh bentuk respons:

```json
{
  "items": [{
    "id": 12,
    "name": "Nasi Goreng",
    "description": "Nasi goreng spesial",
    "price": "15000.00",
    "category": "Makanan",
    "image_url": "",
    "variants": [{
      "id": 4,
      "name": "Ukuran",
      "required": true,
      "options": [{"id": 8, "name": "Regular", "price_adjustment": "0.00"}]
    }],
    "addons": [{"id": 3, "name": "Extra Sambal", "price": "3000.00"}]
  }]
}
```

ID dalam contoh bersifat ilustrasi. Kontrak sebenarnya dibuat di `menu/views.py`.

### Keranjang sesi

| Method | URL | Tujuan |
|---|---|---|
| `GET` | `/api/cart/` | Baca item dan total sesi. |
| `POST` | `/api/cart/add/` | Tambah menu dan konfigurasi. |
| `PATCH` | `/api/cart/<line_id>/` | Ubah jumlah satu baris. |
| `DELETE` | `/api/cart/<line_id>/` | Hapus satu baris. |
| `DELETE` | `/api/cart/clear/` | Kosongkan sesi cart. |

Payload tambah item:

```json
{
  "menu_item_id": 12,
  "quantity": 1,
  "variant_ids": [8],
  "addon_ids": [3]
}
```

`variant_ids` dan `addon_ids` harus berupa array integer. GET dan operasi sukses mengembalikan `{ "items": [...], "total": "..." }`; kesalahan validasi umumnya berstatus `400` dengan field `error`.

### QR meja dan order

| Method | URL | Akses/fungsi |
|---|---|---|
| `GET` | `/api/orders/tables/<token>/` | Validasi token meja aktif; publik; tidak membuat order. |
| `POST` | `/api/orders/checkout/` | Membuat order dari cart sesi pelanggan. |
| `GET` | `/api/orders/<public_id>/` | Ambil detail order untuk konfirmasi; publik lewat ID order. |
| `POST` | `/api/orders/<public_id>/items/` | Tambah item pada order; login dan peran kasir/admin. |
| `POST` | `/api/orders/<public_id>/items/<line_id>/` | Ubah jumlah baris; login dan peran kasir/admin. |
| `POST` | `/api/orders/<public_id>/customer/` | Perbarui data pelanggan; login dan peran kasir/admin. |
| `POST` | `/api/orders/<public_id>/table/` | Ubah meja; login dan peran kasir/admin. |
| `POST` | `/api/orders/<public_id>/pay/` | Bayar order; login dan peran kasir/admin. |
| `POST` | `/api/orders/<public_id>/cancel/` | Batalkan order; login dan peran kasir/admin. |
| `POST` | `/api/orders/<public_id>/refund/` | Refund; admin (`is_staff`) saja. |

Contoh checkout:

```json
{
  "customer_name": "Pelanggan",
  "phone": "",
  "order_type": "TAKEAWAY",
  "note": ""
}
```

Daftar `items` tidak diambil dari body browser; view checkout mengambilnya dari cart sesi. Untuk dine-in, tambahkan `order_type: "DINE_IN"` dan `table_token` valid. Respons sukses `201` memuat `public_id`, status, total, expiry, jenis order/meja, serta baris order. Detail persis respons ada di serializer/helper `_order()` di `orders/views.py`.

### Chatbot

| Method | URL | Fungsi |
|---|---|---|
| `POST` | `/api/recommendation/chat/` | Pesan, balasan, preferensi publik, dan rekomendasi. |
| `POST` | `/api/recommendation/add/` | Tambahkan menu chatbot melalui `CartService`. |

Request percakapan:

```json
{"message": "Aku lapar, mau ayam pedas", "action": ""}
```

`action` mendukung aksi UI seperti `more` dan `reset`; pesan biasa dapat dikirim sebagai string kosong untuk inisialisasi halaman. Respons chatbot memuat `message`, `state`, `preferences`, `recommendations`, dan `quick_replies`. Data kartu rekomendasi memuat ID/nama/deskripsi/harga, label Indonesia, alasan kecocokan, varian beserta opsi aktif, dan add-on yang tersedia.

Request tambah menu menggunakan `menu_item_id`, `quantity`, `variant_ids`, dan `addon_ids` seperti endpoint cart. Endpoint ini menggunakan keranjang sesi yang sama. View akan meneruskan validasi kustomisasi ke `CartService`.

## 8. Alur keranjang dan checkout

```text
MenuItem/API katalog
   → browser memilih varian/add-on/jumlah
   → POST CartService.add_item()
   → session["cart"] menyimpan ID saja
   → GET cart menghitung harga dengan data database saat ini
   → checkout view membaca CartService.checkout_items()
   → create_order(payload) dalam transaction.atomic()
   → validasi menu/varian/add-on/meja
   → Order + snapshot detail + AuditLog
   → cart.clear() setelah order sukses
   → browser membuka /orders/<public_id>/
```

Aturan penting:

- Cart **bukan** tempat menyimpan harga sumber kebenaran.
- `CartService.get_items()` menghitung harga dari menu, varian, dan add-on database.
- `create_order()` menolak cart kosong dan memvalidasi tiap pilihan lagi.
- Varian wajib harus memilih tepat satu opsi untuk setiap grup wajib aktif; opsi dari menu/grup lain ditolak.
- Add-on harus aktif, tersedia, dan terhubung dengan item.
- Cart baru dibersihkan setelah pembuatan order sukses; kegagalan checkout mempertahankan cart.

## 9. QR meja

1. Admin membuat atau mengaktifkan meja di `/staff/tables/`.
2. CMS membuat QR melalui `/staff/tables/<id>/qr/` atau mengunduhnya melalui `/staff/tables/<id>/qr/download/`.
3. QR menunjuk ke storefront dengan query `?table=<token>`.
4. Browser memanggil `GET /api/orders/tables/<token>/` untuk memastikan meja aktif.
5. Browser menyimpan konteks meja sementara dan menghapus parameter token dari address bar.
6. Checkout dine-in mengirim token. Backend memvalidasinya ulang sebelum membuat order.

Pemindaian kamera di browser memerlukan izin kamera dan umumnya secure context (HTTPS atau localhost). Library pemindai QR saat ini dimuat dari CDN.

## 10. CMS, admin, dan akses staf

### Dua panel yang berbeda

- **CMS custom:** `/staff/`; layout dan desain utamanya di `users/templates/users/base.html`, navigasi di `nav.html`, halaman individual di direktori yang sama.
- **Django Admin:** `/admin/`; panel bawaan Django, bukan template CMS custom.

### Halaman CMS

| URL | Template | Kemampuan yang tersedia |
|---|---|---|
| `/staff/login/` | `users/login.html` | Login staf. |
| `/staff/` | `users/dashboard.html` | Ringkasan menu aktif, kategori, order, stok rendah. |
| `/staff/categories/` | `users/categories.html` | Tambah/lihat kategori; edit melalui route edit. |
| `/staff/menu-items/` | `users/menu_items.html` | Tambah, cari, lihat, edit menu. |
| `/staff/variants/` | `users/variants.html` | Tambah grup/opsi varian, lihat/edit. |
| `/staff/addons/` | `users/addons.html` | Tambah/lihat/edit add-on. |
| `/staff/tables/` | `users/tables.html` | Tambah/lihat/edit meja dan buka/download QR. |
| `/staff/orders/` | `users/orders.html` | Daftar order. |
| `/staff/audit-log/` | `users/audit_log.html` | Riwayat aksi order. |

Form `ModelForm` dan widget Bootstrap berada di `users/forms.py`. Template edit yang dipakai bersama adalah `users/form.html`. CMS custom yang ada sekarang **tidak** menyediakan CRUD untuk user staf atau tag; untuk itu gunakan Django Admin atau tambahkan fitur terpisah.

### Role

- Akses halaman CMS custom dibatasi oleh `cms_required` di `users/views.py`, yang mensyaratkan `user.is_staff`.
- Login di `/staff/login/` menerima user `is_staff` atau anggota grup `Cashier`. Kasir saat ini diarahkan ke storefront karena halaman kasir khusus belum dibuat.
- Endpoint operasional order memeriksa login dan grup Cashier/admin melalui `orders/permissions.py`.
- Refund diperiksa terpisah di `orders/services.py` dan hanya diberikan kepada `is_staff`.

## 11. Chatbot rekomendasi

Implementasinya berada di `recommendation/`; chatbot sepenuhnya rule-based dan tidak menggunakan model AI atau layanan eksternal untuk memahami teks.

```text
POST /api/recommendation/chat/
  → recommendation/views.py
  → ChatbotService.reply()
      ├─ normalize_text()
      ├─ TagExtractor.extract()
      ├─ MoodExtractor.extract()
      ├─ MoodResolver.resolve()
      ├─ Preferences digabung dengan state sesi
      └─ RecommendationService.rank()
  → view menerjemahkan tag ke label Indonesia + serialize pilihan item
  → chatbot.html menampilkan respons dan kartu
  → pilih item → POST /api/recommendation/add/
  → CartService (cart sesi biasa)
```

### Tanggung jawab file

| File | Tanggung jawab |
|---|---|
| `services/language.py` | Normalisasi slang/ejaan umum, parser Rupiah, kamus `TAG_LABELS`. |
| `services/tag_extractor.py` | `Preferences` dan deteksi tag langsung, kategori, budget, pantangan kuat/lunak. |
| `services/mood_extractor.py` | Deteksi situasi lelah, low mood, sangat lapar, gerah/haus, buru-buru, bingung. |
| `services/mood_resolver.py` | Menerjemahkan mood ke tag karakteristik dengan bobot tidak langsung. |
| `services/recommendation.py` | Filter item, hitung skor, alasan cocok, ranking deterministik. |
| `services/chatbot.py` | State dialog, follow-up, pesan kontekstual, reset, rekomendasi berikutnya. |
| `views.py` | Adaptasi HTTP/JSON, serializer kartu, endpoint tambah ke cart. |
| `templates/recommendation/chatbot.html` | UI chat, quick replies, kartu, form pilihan varian/add-on. |

### Mood yang dikenali

`MoodExtractor.PHRASES` adalah daftar frase literal setelah normalisasi. `MoodResolver.RESOLUTIONS` menentukan karakteristik tidak langsung. Ini sengaja berupa aturan yang dapat dibaca dan dites, bukan klasifikasi AI.

| ID mood | Contoh frase yang terdeteksi | Tag hasil resolusi |
|---|---|---|
| `tired` | capek/cape, lelah, kecapekan, habis kerja, baru pulang kerja, hari ini berat, energi habis, butuh tenaga | `filling`, `heavy_meal`, `comfort_food` |
| `low_mood` | bad mood, bete, sedih, lagi down, hari ini jelek, pengen dimanjain, butuh comfort food, lagi tidak mood, makanan yang bikin happy, sesuatu yang enak | `comfort_food`, `sweet`, `crispy`, `rich` |
| `very_hungry` | lapar banget/parah/gila, kelaparan, perut kosong, belum makan seharian/dari tadi | `filling`, `heavy_meal`, `rice`, `noodle` |
| `hot_thirsty` | haus, gerah, kepanasan, panas banget, tenggorokan kering, lagi panas | `cold`, `refreshing`, `drink` |
| `quick` | buru-buru, waktunya mepet, mau yang cepat, butuh makan cepat, jangan lama, lagi sibuk | `quick_meal` |
| `confused` | gak/nggak tahu, ga tau, gatau, bingung, terserah, bebas, pilihin, apa saja/apa aja | Tidak otomatis menambahkan tag; memicu pesan bantuan dan quick replies jika tidak ada preferensi lain. |

Deteksi mood dapat menyertakan tag langsung dari kalimat yang sama. Contoh “capek dan mau nasi” menghasilkan mood `tired`, tag langsung `rice`, dan tag resolusi mood `filling`, `heavy_meal`, `comfort_food`.

### Katalog tag dan sumber frasa

Semua ID stabil dan label publik terpusat ada di `language.TAG_LABELS`; frase pemicunya didefinisikan di `TagExtractor.ALIASES`. Daftar per kategori saat ini:

| Kelompok | Tag internal |
|---|---|
| Rasa | `spicy`, `very_spicy`, `savory`, `sweet`, `sour`, `salty`, `umami`, `rich`, `mild` |
| Tekstur | `crispy`, `crunchy`, `soft`, `tender`, `chewy`, `creamy`, `juicy` |
| Saus/kuah | `saucy`, `dry`, `brothy` |
| Bahan | `chicken`, `beef`, `seafood`, `shrimp`, `fish`, `egg`, `tofu`, `tempeh`, `cheese` |
| Jenis makanan/dasar | `rice`, `noodle`, `fried_rice`, `fried_noodle`, `soup`, `bread` |
| Kategori dan porsi | `heavy_meal`, `light_meal`, `snack`, `dessert`, `drink` |
| Pengalaman makan | `filling`, `light`, `comfort_food`, `refreshing`, `warming`, `satisfying` |
| Temperatur | `hot`, `warm`, `cold` |
| Waktu/konteks | `quick_meal`, `late_night`, `breakfast`, `lunch`, `dinner`, `sharing`, `solo` |

Contoh pemetaan frase langsung:

- `spicy`: pedas/pedes (normalisasi), sambal/sambalnya, cabai/cabe, nampol, nendang, bikin melek.
- `chicken`: ayam, daging ayam, olahan ayam.
- `heavy_meal`/`filling`: makanan berat, porsi besar, kenyang/mengenyangkan, lapar, perut kosong, belum makan.
- `snack`: camilan/cemilan, snack, ngemil/nyemil, makan dikit.
- `cold`/`refreshing`/`drink`: dingin/es/sejuk, segar/seger/nyegerin, minuman/minum/haus.
- `rice`/`noodle`: nasi, mie/mi, bakmi; frase “nasi goreng” juga membentuk `fried_rice`, sedangkan “mie goreng” membentuk `fried_noodle`.

Sebagian tag diturunkan dari tag yang lebih spesifik: `very_spicy` juga menambahkan `spicy`; `fried_rice` menambahkan `rice`, `savory`, `filling`; `fried_noodle` menambahkan `noodle`, `savory`, `filling`; `heavy_meal` menambahkan `filling`; `light_meal` menambahkan `light`. Periksa `TagExtractor.extract()` sebelum mengubah aturan turunan karena ia memengaruhi skor rekomendasi.

Tag merupakan kosakata/kemampuan ekstraksi, bukan klaim bahwa setiap item memiliki seluruh karakteristik. Item aktual hanya memperoleh tag melalui pengelolaan data/seed yang sesuai dengan menu tersebut.

### Data preferensi dan state percakapan

`Preferences` menyimpan:

- `tags`: keinginan langsung dari pesan.
- `mood_tags`: ciri menu hasil resolusi mood.
- `excluded_tags`: pantangan tegas; item yang mempunyai tag terkait dikeluarkan.
- `soft_excluded_tags`: ketidaksukaan lunak; skor item berkurang.
- `max_price`, `category`, `prefer_affordable`, `moods`.
- state dialog dan `follow_up` diserialisasi bersama preferensi di sesi.

State yang dipakai mencakup `COLLECTING_PREFERENCES`, `ASKING_FOLLOWUP`, dan `RECOMMENDING`. Untuk permintaan pedas yang hanya berisi satu preferensi, bot dapat menanyakan jenis makanan lalu nasi/mie. Jika ada informasi yang cukup, bot langsung merekomendasikan. `Cari Menu Lain` mempertahankan preferensi dan mengecualikan item yang sudah tampil; `Mulai Lagi` menghapus state rekomendasi, bukan cart.

Alur follow-up yang sudah dibuat:

```text
Pengen pedas
  → ASKING_FOLLOWUP (meal_type: makanan berat atau camilan?)
Makanan berat
  → ASKING_FOLLOWUP (base: nasi atau mie?)
Pengen nasi / bebas
  → RECOMMENDING
```

Jika pesan awal sudah menyertakan cukup detail (contoh ayam, pedas, nasi, budget), bot melewati follow-up agar tidak mengulang pertanyaan. Browser memuat sambutan awal lewat request chat kosong; pesan pengguna berikutnya dikirim ke endpoint yang sama.

### Ranking

Bobot kode saat ini:

- Tag langsung cocok: `+4` per tag.
- Tag hasil mood: `+2` per tag yang tidak dihitung sebagai tag langsung.
- Kategori: `+3`.
- Batas harga yang dipenuhi: `+3`.
- Preferensi “murah/hemat” memberi `+3` jika harga item `<= Rp15.000`.
- Tag yang tidak disukai secara lunak: `-2`.
- Pantangan tegas: item dikeluarkan sebelum ranking.

Item juga harus aktif, tersedia, dan kategorinya aktif. `exclude_ids` menghindari item yang telah ditampilkan. Urutan seri dipecahkan oleh harga lalu nama sehingga hasil stabil. Skor tidak dikirim sebagai angka ke pelanggan; API mengirim label dan `match_reasons`.

`TAG_LABELS` mencegah identifier internal seperti `spicy` menjadi teks UI/API publik. Bila menambah tag baru, sinkronkan aturan ekstraksi, label terjemahan, data menu yang benar-benar sesuai, dan tes.

Catatan kontrak: field `tags`, `mood_tags`, dan daftar pantangan pada `preferences` response diterjemahkan ke label Indonesia oleh view. Field metadata seperti `moods`, `state`, dan `follow_up` adalah identifier alur internal; frontend jangan menampilkannya langsung sebagai copy pelanggan.

## 12. Order dan aturan transaksi

Aturan utama berada di `orders/services.py`; views mengatur protokol HTTP dan JSON.

- `create_order()` berjalan dalam `transaction.atomic()` dan menggunakan harga database.
- `add_item()` memeriksa status menu/kategori, pilihan varian, add-on, menghitung total, membuat snapshot, lalu mencatat audit.
- Perubahan order mengunci order dengan `select_for_update()` dan hanya mengizinkan perubahan pada status `PENDING`.
- Pembayaran merekam metode, nilai, kasir, waktu bayar, dan audit; pembayaran ulang ditolak setelah status berubah.
- Refund hanya untuk order berstatus `PAID`; refund tidak mengubah detail snapshot.
- Order baru memiliki masa berlaku satu jam.
- `expire_order_if_due()` dapat memperbarui expiry saat order dibaca; command `expire_orders` memproses seluruh pending yang jatuh tempo secara berkala.

Status order: `PENDING → PAID`, `CANCELLED`, atau `EXPIRED`; order `PAID` dapat menjadi `REFUNDED`. Ikuti transisi yang divalidasi service, bukan mengubah status langsung dari frontend.

## 13. Seed, migrasi, dan data demo

- Skema awal dan perubahan skema tiap app disimpan di `<app>/migrations/`.
- Setelah mengubah model, buat migrasi dengan `python manage.py makemigrations`, tinjau file hasilnya, lalu jalankan `python manage.py migrate`.
- Jangan mengedit history migrasi yang sudah diterapkan untuk menyembunyikan perubahan.
- `python manage.py seed_demo` mengisi kategori, tag, kombinasi tag per menu, item demo, contoh varian/add-on, meja, grup Cashier, serta akun awal.
- Command seed mengatur password awal hanya bila password user belum usable. Untuk reset password, gunakan `python manage.py changepassword <username>`.
- Seed dijalankan terhadap database yang ditunjuk `SQLITE_DATABASE_NAME` atau default `db.sqlite3`. Server dan command harus memakai konfigurasi database yang sama.

## 14. Tes dan panduan perubahan

Perintah pemeriksaan:

```powershell
python manage.py check
python manage.py test
```

Peta tes:

| File tes | Area |
|---|---|
| `menu/tests.py` | Shell storefront dan response API katalog. |
| `cart/tests.py` | Keranjang sesi dan integrasi checkout/cart. |
| `orders/tests.py` | Aturan order, snapshot, expiry, QR, role/transisi. |
| `users/tests.py` | Login dan CMS staf. |
| `recommendation/tests.py` | Parser bahasa, tag/mood, ranking, state, cart→checkout. |

### Checklist jika menambah fitur UI/API

1. Tentukan pemilik domain (`menu`, `cart`, `orders`, `users`, atau `recommendation`).
2. Perbarui model hanya jika memang ada kebutuhan data persisten; bila model berubah, tambahkan migrasi.
3. Tambah aturan domain di service, bukan menyembunyikannya dalam manipulasi DOM.
4. Tambah URL dan view sebagai adapter HTTP dengan validasi dan respons error yang jelas.
5. Perbarui template/JS pemanggil API; pertahankan CSRF, gunakan server sebagai sumber harga dan status.
6. Perbarui tes service/API/UI yang sesuai.
7. Jalankan `manage.py check` dan tes app terkait; kemudian full suite untuk perubahan lintas app.
8. Perbarui dokumen ini jika lokasi file, endpoint, payload, role, atau alur berubah.

### Checklist jika menambah rekomendasi/tag

1. Tambahkan ID stabil dan alias/negasi pada `TagExtractor` bila dapat diminta pengguna.
2. Tambahkan label Indonesia di `TAG_LABELS`; jangan render raw tag ID.
3. Tentukan apakah ciri berasal dari pesan langsung atau mood.
4. Hanya tetapkan tag pada item demo jika karakteristiknya benar; jangan memberi semua tag ke semua menu.
5. Perbarui tes untuk variasi kalimat, filter, alasan hasil, dan kasus pantangan.

## 15. Batasan implementasi yang perlu diketahui

- SQLite dipakai untuk development/demo. Untuk banyak kasir dengan transaksi serentak, gunakan database yang mendukung row-level locking seperti PostgreSQL.
- Tidak ada integrasi payment gateway eksternal; API pembayaran saat ini adalah aksi internal terautentikasi untuk workflow staf.
- Halaman CMS order menampilkan daftar; belum ada dashboard kasir terpisah untuk cashier. User grup `Cashier` dapat mengakses endpoint operasional yang diizinkan, tetapi login mereka diarahkan ke storefront.
- CMS custom saat ini tidak mengelola akun staf atau tag.
- Bootstrap dan beberapa library browser (QR/kamera) dimuat dari CDN; operasi UI terkait membutuhkan akses jaringan. Kamera juga membutuhkan izin browser.
- `DEBUG` default lokal aktif supaya Django menyajikan static files saat `runserver`; deployment harus memakai `DEBUG=false`, secret key sendiri, host yang benar, dan strategi static files production.
- `seed_demo` adalah data/akun development, bukan mekanisme provisioning akun production.
- Harga ditampilkan/dikirim sebagai string desimal, tetapi harus dihitung dan divalidasi ulang di server pada cart/order.
- Template chatbot menggunakan DOM API yang aman untuk pesan/kartu. Hindari memasukkan teks pelanggan langsung sebagai HTML saat mengubah UI.
