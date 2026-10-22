# Penerapan perubahan security ke project utama

> Dokumen historis perubahan security, 22 Oktober 2026. Penyelarasan panduan pada 23 Oktober 2026 tidak mengubah status kandidat audit atau mengulang tes aplikasi. Untuk perilaku/petunjuk terkini, gunakan [indeks dokumentasi](README.md). Hasil pengujian project utama dicatat di [SECURITY-TRANSFER.md](SECURITY-TRANSFER.md).

Tanggal: 22 Oktober 2026 (Asia/Makassar).

Perubahan aplikasi dari `pemesanan-makanan-digital-security` diterapkan ke
`pemesanan-makanan-digital`. Keduanya memiliki baseline Git
`fc5b256ef6c294fd89e76ae8eb7338c8fa663809`; project utama bersih sebelum
pemindahan. Isi 17 berkas yang dipindahkan diperiksa identik dengan sumber.
Folder skill dan `skills-lock.json` tidak termasuk perubahan aplikasi.

## Perilaku dan berkas terkait

| Berkas | Perubahan |
| --- | --- |
| `recommendation/services/gemini.py` | Kuota harian bersama diperiksa sebelum setiap dispatch, termasuk putaran tool. Log token, model, durasi, hasil, dan request ID dicatat setiap respons/error tanpa isi dialog atau API key. |
| `recommendation/services/conversation_session.py` | Reset juga menghapus teks pesan dan jawaban terakhir; counter pemakaian dipertahankan. |
| `cart/services.py`, `cart/views.py` | Validasi integer 1–99 pada tambah/gabung/edit; respons menghitung total dari snapshot yang sama agar tidak menyelesaikan katalog dua kali. Update integer <= 0 tetap menghapus baris. |
| `orders/services.py` | Checkout menghitung total database sekali di akhir; audit penambahan tetap memperoleh running total. Penambahan standalone tetap menghitung ulang total dari database. |
| `menu/image_processing.py` | Kedua pembukaan gambar hanya memilih parser JPEG, PNG, dan WEBP. |
| `users/views.py`, `users/templates/users/nav.html`, `users/templates/users/kasir/base.html` | Logout membutuhkan POST; kedua navigasi mengirim token CSRF. |
| `cart/tests/test_audit_regressions.py`, `orders/tests/test_audit_regressions.py`, `recommendation/tests/test_audit_regressions.py`, `users/tests/test_logout_security.py`, `menu/tests/test_image_processing.py` | Tes regresi perubahan dan kontrak yang dipertahankan. |
| `config/audit_test_settings.py` | Profil tes dengan SQLite di memori, media sementara, credential dummy, serta Gemini nonaktif secara default. |
| `docs/Chatbot.md`, `docs/AUDIT-FOLLOWUP.md` | Panduan log dan catatan audit asal. Catatan belum-diuji pada AUDIT-FOLLOWUP adalah riwayat project sumber; hasil project utama dicatat di dokumen ini. |

`CartService` memusatkan aturan kuantitas dan perhitungan total. `GeminiClient`
memusatkan pemeriksaan kuota dalam satu method untuk kedua jalur SDK.
Checkout tetap memakai transaksi atomic; logout memakai decorator HTTP dan
middleware CSRF Django. Tidak ada perubahan schema atau dependency.

Contoh: baris keranjang berjumlah 98 ditambah 1 menjadi 99. Penambahan 1 lagi
ditolak tanpa mengubah baris. Untuk Gemini, satu pesan dengan satu putaran tool
dapat menghasilkan dua log `provider_attempt` dengan `request_id` yang sama;
`total_tokens` berlaku per panggilan, bukan total sesi.

## Verifikasi

45 tes terfokus lulus dengan profil dummy:

```powershell
.\.venv\Scripts\python.exe -B -m django test --settings=config.audit_test_settings recommendation.tests.test_audit_regressions cart.tests.test_audit_regressions orders.tests.test_audit_regressions users.tests.test_logout_security menu.tests.test_image_processing --verbosity=1
```

Folder TEMP/TMP proses tes diarahkan ke
`../output/security-transfer-20261022/tmp` karena folder sementara bawaan
sandbox Windows menolak penulisan/pembersihan pada percobaan awal.
Pemeriksaan sistem Django tidak menemukan masalah; `git diff --check` lulus.
Regresi luas (`cart orders users menu recommendation`) menjalankan 1.099 tes:
39 failure dan 637 error (angka ini termasuk subtest). Salinan baseline HEAD
di folder output diuji dengan profil dummy yang sama: 1.069 tes, 39 failure,
dan 637 error. Seluruh entri failure/error identik sebelum dan sesudah;
tidak ditemukan tambahan kegagalan. Di antaranya provider palsu tes lama
tidak memiliki atribut `available`, anotasi tipe lama belum lengkap, serta
host localhost tidak diizinkan profil dummy. Ini bukan klaim seluruh suite
lulus. Log pembanding tersedia di
`../output/security-transfer-20261022/{baseline-tests,regression-tests}.log`.
Provider pada tes dipalsukan. Tidak ada pengujian Gemini asli atau browser,
perubahan database aplikasi, commit, push, atau deployment.

## Mencoba di web

Restart server yang dijalankan dari folder project utama dengan perintah lokal
yang biasa digunakan. Coba tambah/edit keranjang, checkout, unggah foto,
logout staf/kasir, serta reset dialog. Jika konfigurasi lokal mengaktifkan Gemini,
setiap panggilan akan menampilkan JSON `provider_attempt` di terminal server;
perhatikan `total_tokens`, `outcome`, dan `request_id`. Pengujian otomatis ini
tidak memverifikasi kualitas jawaban provider asli atau konfigurasi deployment.

Review sebelum commit: periksa diff, hasil tes, logout lewat tombol, serta log
token ketika mencoba chat. Usulan pesan commit:
`fix: apply security hardening and Gemini usage logs to main project`.
