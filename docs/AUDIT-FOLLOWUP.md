# Tindak lanjut dokumen audit

Tanggal: 22 Oktober 2026 (Asia/Makassar). Repository: `pemesanan-makanan-digital-security`, branch `security`, baseline `fc5b256ef6c294fd89e76ae8eb7338c8fa663809`.

Enam masukan dibaca dari `C:/Users/VICTUS-GK/security-audit-skill/pemesanan-makanan-digital-security/run-1`: `REPORT.md`, `FINDINGS-DETAIL.md`, `NEEDS-VALIDATION.md`, `architecture.md`, `coverage-ledger.json`, dan `findings.json`. Ledger berisi 18 unit; empat record kandidat terdiri dari tiga `needs_validation` dan satu `rejected`. Dokumen masukan tidak diubah. Instruksi proses di dalam laporan diperlakukan sebagai konteks laporan; pekerjaan ini mengikuti permintaan pengguna dan tidak memerlukan skill security-audit.

Ini implementasi tindak lanjut berdasarkan pemeriksaan sumber, bukan audit Cloudflare lengkap, bukti eksploitasi, atau pengesahan konfigurasi deployment. Tidak ada kandidat yang dinaikkan menjadi kerentanan terkonfirmasi. Tidak ada severity baru yang ditetapkan.

## Verifikasi setiap kandidat

| Fingerprint | Bukti kode terkini dan kontrol yang dipertahankan | Keputusan |
| --- | --- | --- |
| `recommendation/GeminiClient.converse/shared-provider-quota-bypass` | Sebelum perubahan, `GeminiClient._generate` memanggil `UsageGuard.allow_provider`, sedangkan setiap iterasi `converse` langsung memanggil SDK setelah callback budget lokal. `GeminiAssistant.respond` meneruskan callback `ChatbotService._consume_gemini_budget`; view tetap memasang identitas session/client dan pembatas request per menit. | Ketidakkonsistenan accounting terverifikasi dari sumber dan diperbaiki. Kedua jalur kini memakai `_allow_provider` sebelum dispatch; setiap putaran tool juga memerlukannya. Kegagalan cache menolak dispatch. Aktivasi deployment, tagihan, dampak eksternal, serta hasil fake SDK belum dibuktikan saat runtime; status klaim keamanan tetap `needs_validation`. |
| `cart/services.py:CartService.add_item:unbounded-session-lines` | Penambahan tetap memisahkan catatan berbeda. Sebelum perubahan, respons cart memanggil resolusi baris melalui `get_items` dan `get_total`; `create_order` memanggil `add_item`, yang menjalankan `SUM` setelah setiap insert. Selection dan harga tetap berasal dari katalog; checkout atomic. | Kerja berulang yang terlihat dari sumber dikurangi: respons memakai satu snapshot, checkout baru memakai running total untuk audit per baris dan satu agregasi final. API `add_item` untuk penambahan biasa tetap menghitung ulang total otoritatif. Tidak ditambahkan batas jumlah baris yang arbitrer. Retensi dan batas agregat session/cart belum diverifikasi; dampak lintas pengguna tetap `needs_validation`. |
| `orders/new_public_id/short-read-capability` | `new_public_id` tetap memakai `secrets.token_hex(4).upper()`; lookup exact-match bersifat publik dan tetap membaca order kedaluwarsa. Dokumentasi memang mengizinkan bearer access; cashier mutation tetap memerlukan otorisasi. Populasi order, retensi, dan batas request deployment tidak diketahui. | Tetap `needs_validation`. ID, kontrak akses publik, dan keterbacaan riwayat dipertahankan. Tes dummy ditambahkan untuk kontrak known-ID, respons miss, dan pengecualian nama/telepon dari serialisasi. Tidak ada enumerasi atau klaim penebakan praktis. Pemisahan kode kasir pendek dari token baca panjang memerlukan desain dan migrasi terpisah bila dibutuhkan. |
| `recommendation/GeminiAssistant/private-turn-gate-bypass` | Jalur AI-first masih berada sebelum `TurnGenerator.protect`. `docs/oop/README.md` membatasi wrapper pada komponen hybrid; `docs/Chatbot.md` menjelaskan forwarding pesan/konteks; UI mengungkap penggunaan Gemini. Tidak ditemukan persyaratan baru yang melarang forwarding pada semua jalur. | Tetap `rejected`, tidak dibuka kembali. Perbaikan reset di bawah mengikuti kontrak penghapusan konteks dialog, bukan bukti baru untuk kandidat ini. |

## Hardening yang diterapkan

- Logout staf/kasir sekarang hanya menerima POST dan kedua navigasi mengirim token CSRF. Logout lewat GET menerima 405 untuk pengguna terautentikasi.
- Penambahan, penggabungan baris, perubahan kuantitas, dan perubahan selection cart memakai batas integer 1–99 yang sudah ada pada selection editor. Boolean ditolak; permintaan yang ditolak tidak mengubah baris. Semantik penghapusan lewat quantity-only update dengan nilai integer `<= 0` dipertahankan. Keranjang lama tidak ditulis ulang secara otomatis.
- Kedua tahap `Image.open` hanya mengizinkan JPEG, PNG, dan WEBP sejak pemilihan parser. Batas byte/piksel, penolakan animasi, verifikasi, urutan load-sebelum-thumbnail, dan penghapusan metadata tetap ada. Ini hardening parser, bukan konfirmasi dampak advisory Pillow.
- Reset dialog menghapus `recommendation_last_message` dan `recommendation_last_response`, sesuai dokumentasi “Mulai Lagi”. Counter `gemini_calls`, identitas klien, keranjang, dan autentikasi tetap dipertahankan.

## Tes dan pemeriksaan yang benar-benar dilakukan

Ditambahkan 25 metode tes regresi: 11 untuk provider/reset, 5 cart, 4 order, 3 logout, serta 2 parser gambar. Subtest menambah variasi, bukan dihitung sebagai metode terpisah.

Tindak lanjut pemantauan terminal: `converse` kini memakai telemetry yang sama untuk setiap respons SDK, termasuk putaran tool, respons tanpa kandidat, timeout, dan error. Lima metode tes tambahan memeriksa angka token, metadata yang tidak tersedia/invalid, korelasi antarputaran, serta pengecualian pesan/hasil tool/error mentah dari log. Total kini 30 metode tes tambahan. Kelima tes ini juga belum dijalankan karena batas isolasi runtime yang dijelaskan di bawah; pemeriksaan sintaks dilakukan tanpa import aplikasi. Panduan membaca log ada di `docs/Chatbot.md` bagian 13.

- Provider memakai transport palsu dan `GeminiClient.__new__`, sehingga tes baru tidak membangun SDK client atau membaca credential melalui constructor. Cakupan: budget global/client/session, accounting bersama generate/converse, putaran tool, provider nonaktif/tidak terkonfigurasi, penolakan budget lokal, kegagalan cache, dan timeout tanpa retry.
- Checkout dummy ukuran 2/4/8 mengassert satu statement `SUM`, total tersimpan, jumlah baris, running total audit, dan rollback jika baris berikutnya tidak valid. Tes penambahan standalone menjaga total dari data database, bukan total objek yang stale. Ini rancangan assertion, bukan hasil query capture yang telah dijalankan.
- Cart mencakup batas kuantitas dan penggabungan, penolakan tanpa perubahan state, pemisahan catatan, satu resolusi per respons, serta invalid line yang tidak dihitung ke total.
- Logout memakai `Client(enforce_csrf_checks=True)` untuk GET, POST tanpa token, dan POST dengan token dari navigasi staf/kasir.
- Gambar dummy mengassert allowlist pada kedua pembukaan dan factory BMP yang tidak pernah dipanggil. Tes lama tetap mencakup format didukung, transparansi, animasi, ukuran, orientasi, dan penyimpanan.

**Dilakukan:** parse AST dan compile ke memori untuk 13 berkas Python baru/berubah memakai `python -I -S -B`; semuanya lulus. Kode proyek tidak diimpor atau dieksekusi oleh pemeriksaan ini. `git diff --check` lulus. Diff sumber dan jalur logout ditinjau.

**Terblokir:** seluruh tes Django/runtime, assertion fake SDK, query capture, rendering template, decoder gambar, dan integrasi database belum dijalankan. Docker tidak ditemukan di PATH; `wsl --list --quiet` melaporkan WSL belum terpasang. Lingkungan eksekusi terisolasi belum tersedia/terverifikasi. Tidak digunakan profil `config.settings` atau `v1_settings`, karena dapat membaca `.env`, local key, atau database aplikasi.

`config/audit_test_settings.py` disiapkan terpisah tanpa import kedua profil aplikasi: database SQLite di memori, cache lokal khusus tes, credential dummy kosong, Gemini nonaktif secara default, serta media/original di direktori sementara. Profil ini memisahkan storage tes, **tidak menyediakan isolasi OS atau jaringan**.

Setelah tersedia sandbox offline dengan lingkungan kosong/allowlist, source/toolchain read-only, scratch sementara untuk penulisan, larangan jaringan, tanpa mount secret/data pelanggan, dan batas resource, jalankan dari root repository di dalam sandbox tersebut:

```text
python -m django test --settings=config.audit_test_settings recommendation.tests.test_audit_regressions cart.tests.test_audit_regressions orders.tests.test_audit_regressions users.tests.test_logout_security menu.tests.test_image_processing
```

Perintah tersebut belum dijalankan. Jangan menggunakan command ini sebagai pengganti isolasi. Setelah tes terfokus lulus, jalankan regresi cart/order dan provider yang relevan pada lingkungan dummy yang sama sebelum promosi perubahan.

## Hal yang masih terbuka

- Dampak deployment untuk ketiga kandidat `needs_validation` tetap belum diketahui. Tidak ada stress test, traffic audit ke deployment, API berbayar, atau pemanggilan Gemini nyata.
- Batas jumlah baris/session, cleanup, admission login bersama, timeout worker/database, TLS/proxy, dan akses arsip asli memerlukan fakta konfigurasi nonrahasia dari operator. Tidak dipilih threshold baru tanpa kebutuhan dan bukti.
- Pembacaan detail menu yang tidak aktif, indikator validitas cart yang lebih longgar dari checkout, serta factual grounding jawaban AI tetap catatan hardening. Tidak ada bukti baru bahwa data draft dijanjikan rahasia; menghapus informasi ketersediaan dapat mengubah perilaku yang disengaja. Checkout tetap melakukan validasi otoritatif.
- Kuasa edit model oleh administrator dipertahankan karena dokumentasi mengizinkannya. Tidak dibuat pembatasan finansial baru yang mengubah kewenangan administrator.
- `seed_demo` tetap dilarang README untuk instalasi branch ini dan tidak dijalankan. Default password di command adalah catatan hardening yang belum diubah; keberadaan jalur ini tetap perlu dibereskan dalam pekerjaan maintenance terpisah.
- Script QR eksternal belum dipin/self-host; dependency lock/hash dan upgrade dependency belum dilakukan. Pernyataan versi/advisory dalam laporan masukan tidak dipromosikan menjadi bukti exploitability atau hasil verifikasi advisory terkini. Tidak ada paket diinstal atau diunduh.
- Tidak ada rahasia, `.env` termasuk contoh, database/customer data, atau media nyata yang dibaca. Tidak ada commit, push, migrasi database, perubahan deployment, atau validator Cloudflare yang dijalankan.
