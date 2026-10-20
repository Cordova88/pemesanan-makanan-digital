# Panduan verifikasi dan pemantauan hosting RasaKita V1

Disusun 18 Oktober 2026. Ini rencana pemeriksaan, bukan bukti deployment sudah
terjadi. Tujuan: memastikan perilaku yang diuji lokal tetap benar di server,
melindungi sesi pengguna, membatasi penggunaan API, serta menemukan kegagalan.

## 1. Urutan dan keputusan rilis

1. Pengembang menjalankan pengujian lokal; catat revisi dan hasil.
2. Pengelola hosting menyiapkan **staging**: lingkungan percobaan terpisah,
   database/media percobaan, domain, secret, cache, dan key API khusus staging.
3. Jalankan pemeriksaan konfigurasi, fungsi, pembatasan serta gangguan di staging.
4. Pemilik proyek meninjau bukti dan memutuskan deployment. Jangan otomatis
   merilis hanya karena tes lokal lulus.
5. Setelah deployment yang disetujui, lakukan pemeriksaan singkat produksi dan
   pemantauan. Pengujian beban/gangguan tetap di staging.

Tetapkan penanggung jawab aplikasi, hosting, data/backup, dan penggunaan Gemini;
satu orang boleh memegang beberapa peran. Isi domain, profil settings, versi
Python/dependency, proses aplikasi, database, cache, lokasi log, jadwal pembersihan,
serta kontak pemilik. Jangan memasukkan nilai rahasia ke lembar bukti.

## 2. Konfigurasi sebelum staging dibuka

`manage.py` default memakai `v1_settings`, yang merupakan profil lokal.
WSGI/ASGI atau perintah operator harus memilih profil deployment secara eksplisit.
`config.settings` adalah titik awal; bukan jaminan seluruh kebutuhan hosting
sudah terpenuhi. Pilih database/server yang sesuai hosting dan uji pemulihannya.
Tidak perlu mengganti database hanya untuk menyelesaikan panduan ini.

| Pemeriksaan | Cara membuktikan | Kriteria lulus |
|---|---|---|
| Secret | Pengelola memeriksa keberadaan secret runtime tanpa menampilkan nilainya | Key Django kuat, bukan fallback development; Gemini hanya di backend |
| Profil | Catat nama modul settings pada konfigurasi service | Profil produksi eksplisit; bukan `v1_settings`/profil Gemini lokal |
| Debug/host | Periksa konfigurasi dan uji Host salah pada staging | DEBUG mati, domain eksplisit, Host tak dikenal ditolak |
| Dependency | Catat versi runtime dan binding cache terpasang | Versi sesuai aplikasi; binding Redis/Memcached tersedia |
| Aset/media | Buka halaman, gambar dan modul JavaScript | Tidak ada aset 404; private original upload tidak menjadi URL publik |
| Database | Uji baca/tulis percobaan dan restart aplikasi | Data persisten; bukan database sementara proses |
| Backup | Pulihkan backup DB+media ke lingkungan terpisah | Katalog/pesanan/file cocok, bukan sekadar ada file backup |

Pada profil yang benar, jalankan dari folder aplikasi:

```powershell
python -B manage.py check --deploy --settings=config.settings
```

Jika operator membuat profil lain, ganti `config.settings` dengan profil itu
untuk **semua perintah** di panduan ini. Pemeriksaan membaca settings runtime;
jalankan hanya pada lingkungan yang memang dikelola operator. Tidak boleh ada
error; setiap warning harus diperbaiki atau memiliki penjelasan risiko tertulis.
Pemeriksaan ini tidak membuktikan jaringan Redis atau sertifikat berfungsi.

Kode `chatbot.E001`–`E009` memeriksa debug, hosts, cookie/HTTPS, backend cache,
enforcement dan binding. Jangan menonaktifkan pemeriksaan atau shared-cache
enforcement hanya agar hasil terlihat hijau. Rujukan:
[checklist deployment Django](https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/).

## 3. HTTPS, cookie, login dan CSRF

Lakukan dengan akun/data staging dan browser biasa:

1. Buka alamat HTTP; harus dialihkan ke HTTPS tanpa lingkaran redirect.
2. Periksa sertifikat: domain cocok, valid dan belum kedaluwarsa.
3. Login, refresh, logout, coba CMS/kasir dengan akun yang sesuai. Pelanggan
   tidak boleh mengakses fungsi staf.
4. Melalui alat pengembang browser, periksa cookie sesi: `Secure` dan `HttpOnly`.
   Cookie CSRF harus `Secure`; tidak harus `HttpOnly` jika JavaScript membacanya.
   Jangan menyalin nilai cookie ke laporan.
5. Kirim operasi POST normal melalui UI: berhasil. Uji POST tanpa token CSRF:
   ditolak 403. Jangan mematikan middleware CSRF untuk menghilangkan error.
6. Pastikan tidak ada permintaan HTTP campuran dari halaman HTTPS.

Jika TLS berakhir di reverse proxy, operator harus mengatur header/skema proxy
yang dipercaya. Proxy wajib menimpa header dari klien. Jangan menyalin setelan
`SECURE_PROXY_SSL_HEADER` tanpa memastikan perilaku penyedia hosting.
HSTS diterapkan setelah HTTPS terverifikasi, dengan strategi yang sesuai domain;
tidak perlu langsung melakukan preload untuk percobaan tugas.

## 4. Cache bersama dan batas penggunaan

Kode mendukung backend Django RedisCache, PyMemcacheCache, dan PyLibMCCache.
`config.settings` menyediakan opsi Redis lewat variabel `CHATBOT_REDIS_URL`;
URL berkredensial merupakan secret. Backend lain perlu konfigurasi settings
yang sesuai. Cache lokal per proses tidak cukup untuk produksi multiworker.
Rujukan perilaku backend: [cache Django](https://docs.djangoproject.com/en/6.0/topics/cache/).

Operator menyiapkan cache privat, namespace khusus aplikasi/lingkungan,
kontrol akses, enkripsi jaringan sesuai hosting, dan kebijakan memori. Gunakan
primary yang konsisten untuk pembatasan. Eviction/restart dapat mereset penghitung;
pastikan strategi persistensi dan kapasitas sesuai kebutuhan. Memcached tidak
menyediakan persistensi seperti Redis; catat keterbatasan ini bila dipilih.

Uji staging dengan minimal dua proses aplikasi dan batas percobaan kecil,
misalnya global 10, klien 6, sesi 4 per menit. Ini perlu ditetapkan sebagai
nilai settings `CHATBOT_REQUESTS_GLOBAL_PER_MINUTE`,
`CHATBOT_REQUESTS_CLIENT_PER_MINUTE`, `CHATBOT_REQUESTS_SESSION_PER_MINUTE`;
bukan sekadar menambahkan nama variabel ke `.env`, karena belum semua setting
memiliki pemetaan environment pada source. Gemini dinonaktifkan untuk tes beban ini.

| Kasus | Pelaksanaan terkendali di staging | Hasil yang diharapkan |
|---|---|---|
| Beberapa proses | Kirim permintaan valid bergantian ke dua proses dalam jendela waktu sama | Batas merupakan total bersama, bukan per proses |
| Bersamaan | Kirim sejumlah kecil permintaan paralel dengan CSRF/sesi valid | Penerimaan tidak melewati cap yang sedang diuji |
| Reset | Capai batas, tekan reset, ulangi | Reset tidak melewati pembatas |
| Sesi baru | Klien sama membuat sesi lain | Pembatas klien tetap bekerja |
| Header palsu | Ubah X-Forwarded-For pada permintaan staging | Klien tidak bebas mengganti identitas pembatas |
| Cache tidak tersedia | Operator putuskan akses cache staging sementara | Chat ditolak 503; tidak melewati guard/API; pulih setelah cache kembali |
| Jendela baru | Tunggu periode berikutnya | Permintaan dapat diterima kembali sesuai batas |

Gunakan batas satu lapis yang kecil dan lapis lain lebih besar agar hasil dapat
diatribusikan. Catat waktu UTC; fixed window dapat mengizinkan burst di batas
pergantian periode. Jangan memakai `cache.clear()` pada cache bersama untuk
mempermudah tes. Jangan melakukan gangguan cache/beban di produksi.

**Proxy dan NAT:** identitas klien memakai `REMOTE_ADDR`. Periksa apakah hosting
meneruskan alamat yang benar. Jika semua pengguna terlihat sebagai satu proxy,
kuota klien dapat menjadi kuota seluruh pengguna. Perubahan pemetaan IP hanya
boleh mempercayai proxy yang dikendalikan; jangan langsung mempercayai XFF publik.
Uji dua klien berbeda dan klien pada jaringan bersama untuk menilai salah blokir.

## 5. Validasi API dan fungsi bisnis

Gunakan endpoint `/api/recommendation/chat/` dengan cookie/token CSRF staging.

| Kasus | Hasil yang diperiksa |
|---|---|
| POST JSON valid, budget dan follow-up | 200; isi/kartu sesuai katalog dan batas |
| JSON rusak, root array, tipe pesan salah, field asing/duplikat | 400 generik |
| Pesan 501 karakter atau body >8192 byte | 413; atau batas proxy terdokumentasi yang lebih ketat |
| Content-Type tidak sesuai | 415 |
| GET pada endpoint POST | 405 |
| POST tanpa CSRF | 403 |
| Pembatas tercapai | 429, Retry-After; UI menjelaskan kegagalan |
| Guard/internal error percobaan | 503 generik, tanpa traceback/rahasia |
| Respons chat yang mencapai view | X-Request-ID dibuat server dan Cache-Control no-store |

403 dari middleware dan error proxy dapat memiliki header/body berbeda;
jangan salah menyebutnya kegagalan validator aplikasi. Periksa agar CDN/proxy
tidak menyimpan respons chat, sesi, keranjang, dan halaman staf secara publik.

Jalankan alur katalog → chatbot → tambah keranjang → checkout → kasir pada
database staging. Periksa harga server, jumlah, status, otorisasi, serta akses
pesanan milik pengguna lain. Pakai pembayaran percobaan bila ada integrasi.
Pemesanan/penjualan tidak boleh dianggap berhasil hanya karena chatbot menjawab.

## 6. Gemini: aktivasi bertahap dan penggunaan

Mulai staging dengan `GEMINI_ENABLED=false`. Aktifkan hanya setelah guard dan
mode lokal lulus. Secret runtime memuat `GEMINI_API_KEY`, model teks yang tersedia
melalui `GEMINI_MODEL`, serta flag aktif. `.env` tidak dimuat otomatis oleh source;
gunakan fasilitas environment/secret hosting. Jangan mengunggah `.env` lokal
sebagai aset publik. Key tidak boleh berada di JavaScript atau respons API.

Gunakan proyek/key staging terpisah, batas panggilan kecil dan pengujian singkat.
Periksa akses model/kuota/billing pada dashboard Google. Key baru dalam proyek
yang sama tidak otomatis memisahkan anggaran. Lihat
[pengelolaan API key](https://ai.google.dev/gemini-api/docs/api-key) dan
[daftar model](https://ai.google.dev/gemini-api/docs/models).

- Buktikan satu keberhasilan dari metadata `provider_attempt`: model, outcome,
  `provider_called`, latency dan token jika tersedia; cocokkan dengan dashboard.
- Simulasikan timeout, output salah, dan kuota habis menggunakan provider palsu
  pada tes terisolasi; mode lokal harus memberi fallback yang sesuai.
- Gangguan jaringan nyata bila diperlukan hanya di staging terkontrol. Jangan
  terus mengirim permintaan berbayar untuk memancing kegagalan.
- Periksa batas input/output dan timeout SDK tetap aktif. Satu pesan dapat
  memicu beberapa tahap provider; jangan menyamakan pesan dengan jumlah API call.
- `estimated_cost=null` berarti belum dihitung. Penghitung attempt bukan tagihan
  dan bukan batas uang keras. Periksa pemakaian/tagihan di penyedia; notifikasi
  anggaran saja tidak boleh diasumsikan menghentikan pengeluaran.

Sebelum publik, pemilik meninjau pemberitahuan pengguna, data yang dikirim,
ketentuan Google serta tier akun yang dipakai. Jangan menjanjikan kepatuhan
hukum atau perlakuan data tertentu hanya dari hasil tes kode.

## 7. Privasi, sesi dan penghapusan data

Uji menggunakan teks penanda sintetis, bukan data pelanggan:

1. Periksa log aplikasi/hosting/proxy: tidak boleh menyimpan body chat, key,
   cookie, session ID mentah, atau traceback berisi rahasia. Metadata request ID,
   waktu, status, token dan latency dapat digunakan.
2. Periksa pengaturan platform: perekaman request body/debugging eksternal harus
   dinilai terpisah; kode aplikasi tidak mengendalikan semua log platform.
3. Biarkan dialog tidak aktif melewati 1800 detik, lalu kirim pesan. Konteks lama
   harus dibersihkan secara logis tanpa menghapus login/keranjang/kuota.
4. Tetapkan penghapusan log operasional, misalnya maksimal 7 hari sesuai kebijakan
   proyek, akses terbatas dan rotasi. Ini usulan kebijakan, belum terpasang otomatis.
5. Jadwalkan `clearsessions` untuk sesi database yang kedaluwarsa, menggunakan
   profil deployment dan jadwal operator. Uji dahulu pada database staging.

```powershell
python -B manage.py clearsessions --settings=config.settings
```

Perintah itu **menghapus sesi kedaluwarsa**; bukan pemeriksaan read-only. Jangan
menjalankannya pada database yang salah. Kedaluwarsa konteks chatbot tidak
otomatis menghapus baris sesi dari database. Django menjelaskan pembersihan
pada [dokumentasi sesi](https://docs.djangoproject.com/en/6.0/topics/http/sessions/).
Selaraskan retensi backup dengan kebijakan; penghapusan di DB utama tidak
otomatis menghapus salinan backup.

## 8. Pemantauan setelah rilis

Rencana frekuensi berikut belum menjadi automation. Operator memilih alat
hosting, mengatur jadwal dan penerima notifikasi, lalu menguji notifikasinya.

| Frekuensi awal | Yang dipantau | Tindakan bila bermasalah |
|---|---|---|
| Tiap 5 menit | Halaman utama/aset dan kesehatan service; jangan membuat pesanan/API call sebagai probe rutin | Periksa hosting/proses/log; jangan mengulang transaksi |
| Tiap 5–15 menit | Rasio status 5xx, lonjakan 429, latensi chat, cache tidak tersedia | Korelasikan request ID, periksa kapasitas/cache/pembatas |
| Harian selama minggu pertama | Provider success/error/timeout, token, dashboard kuota/tagihan | Cari perubahan model/key/traffic; matikan Gemini jika perlu |
| Harian | Kapasitas DB/media/cache, hasil backup dan pekerjaan pembersihan | Tindak lanjuti job gagal/kapasitas sebelum penuh |
| Mingguan dan sebelum rilis | Sampel alur budget, follow-up, keranjang pada staging; sertifikat dan akses operator | Perbaiki regresi, akses dan jadwal pembaruan |
| Setelah perubahan konfigurasi | check --deploy dan smoke test staging | Tahan rilis jika ada error atau prasyarat tidak terbukti |

Contoh pemicu awal untuk disesuaikan dengan traffic: 3 kegagalan pemeriksaan
halaman berturut-turut; guard unavailable kapan pun; 5xx >5% dengan minimal
20 permintaan selama 5 menit; penggunaan provider mendekati 80% kuota proyek.
Ini usulan, bukan alarm yang sudah aktif atau ambang yang pasti tepat.

Operator dapat membaca snapshot cache bersama:

```powershell
python -B manage.py chatbot_usage --settings=config.settings
```

`request_attempts_current_minute` dan `provider_budget_attempts_current_utc_day`
mencakup upaya yang ditolak. Jendela harian mengikuti UTC, bukan tengah malam
Makassar. Snapshot tidak menghitung seluruh riwayat dan tidak membuktikan tagihan.
`guard_available=true` hanya menunjukkan operasi snapshot berhasil, bukan bukti
multiworker/concurrency sudah benar. Pada LocMem, proses perintah memiliki cache
sendiri sehingga angka nol tidak mewakili proses server.

Pemantauan API nyata memakai event `provider_called` dan dashboard penyedia;
metrik latency/error perlu dihimpun oleh operator. Source belum menyediakan
dashboard monitoring, alarm, atau hitungan biaya lengkap secara otomatis.

## 9. Penanganan gangguan dan rollback

1. Simpan waktu, revisi, request ID, status dan gejala; hindari body/secret.
2. Untuk masalah provider/pemakaian tak terduga, set `GEMINI_ENABLED=false`
   melalui konfigurasi service dan restart/redeploy sesuai hosting. Verifikasi
   mode lokal masih bekerja. Cache rusak tetap perlu diperbaiki; flag ini tidak
   melewati request guard.
3. Jangan flush cache, menonaktifkan CSRF, atau mengaktifkan DEBUG sebagai
   pemulihan produksi. Lindungi key bila ada indikasi kebocoran.
4. Jika perlu rollback, operator kembali ke revisi rilis terakhir yang diketahui
   baik. Jangan menimpa database/media dengan backup lama tanpa rencana karena
   transaksi baru dapat hilang. Phase7 tidak menambah migrasi schema.
5. Catat penyebab, tindakan, hasil pemulihan dan pengujian regresi sebelum rilis ulang.

## 10. Bukti dan checklist persetujuan

| Tanggal/revisi/lingkungan | Pemeriksaan | Pelaksana | Hasil | Bukti aman | Tindak lanjut |
|---|---|---|---|---|---|
| ... | ... | ... | Lulus/gagal/belum diuji | ID/log metadata, tanpa secret | ... |

- [ ] Tes lokal lulus dan revisi dicatat.
- [ ] Profil production, secret, hosts dan check --deploy ditinjau.
- [ ] HTTPS, cookie, CSRF, otorisasi dan aset lulus.
- [ ] Cache bersama dibuktikan pada beberapa proses; outage dan NAT ditinjau.
- [ ] Budget/konteks/keranjang/transaksi staging lulus.
- [ ] Mode lokal dan Gemini opsional/fallback diverifikasi sesuai kebutuhan.
- [ ] Log aman, retensi, pembersihan sesi dan backup-restore diuji.
- [ ] Pemantauan, penerima alarm, batas penggunaan dan rollback ditetapkan.
- [ ] Pemilik proyek menyetujui rilis; tidak ada prasyarat kritis yang belum jelas.

Dokumen ini tidak mengubah konfigurasi, memasang service, menjadwalkan job,
memakai API, atau melakukan deployment. Pertanyaan pemahaman: mengapa
check --deploy saja belum membuktikan Redis bekerja? Mengapa reset percakapan
tidak boleh menghapus penghitung penggunaan API?

## 11. Pemeriksaan konsistensi sesi chatbot

Implementasi lokal kini memakai chat-only canonical rows dengan SQL CAS di tabel
django_session existing. Semua worker harus memakai database dan secret konsisten.
Tidak ada schema migration baru; verifikasi normal sessions migration sudah diterapkan
pada staging. Main auth/cart session bukan authority chatbot; DEBUG=False menghapus
mirror chat. Jangan melakukan rollback hanya satu file endpoint/template.

- Uji dua koneksi/worker dan dua tab, aksi dari quick reply lama, reset pending,
  lost response dan retry. Satu writer untuk base sama boleh menang; stale lainnya
  harus409 atau storage-busy503, tanpa menimpa pantangan/budget/selection terbaru.
- Frontend terbaru mengirim revision; pastikan aset/template lama tidak tertahan cache.
  Jangan auto-retry conflict dengan versi baru tanpa keputusan pengguna.
- Uji contention DB dan shared-cache outage. CAS tidak memakai cache; quotas SDK
  tetap memerlukan shared atomic cache. SQLite dapat menolak writer saat busy;
  ukur pada staging sebelum menyatakan kapasitas production memadai.
- Verifikasi reset menjaga quota dan losing/failed provider attempt tetap dihitung.
  Pantau metadata request/provider/fallback dan 409/429/503, bukan raw chat/IP/key.
- Canonical row memiliki expiry24 jam dan prefix rkchatv3. Tentukan physical cleanup
  memakai operasi Django clearsessions yang dijadwalkan operator, akses DB/backup/log
  dan retention backup. Belum ada job dibuat/dijalankan oleh pekerjaan ini. Signing
  bukan enkripsi; expired records tetap bisa ada sampai cleanup berjalan.
- Review rotasi secret, invalidasi canonical scoped dan rollback; jangan menghapus
  seluruh django_session atau cache/quota untuk memperbaiki konflik.
- Jalankan deployment checks pada profil production. Tambahan check sessions dan
  warning HSTS/SameSite bukan bukti TLS/proxy/HSTS/shared cache sudah benar. Aktifkan
  HSTS hanya setelah HTTPS benar. v1 tetap development; config memerlukan explicit
  DEBUG=false/hosts/secret dan konfigurasi lingkungan yang tepat.

Hasil uji lokal tidak menggantikan verifikasi staging, beban, TLS, cache bersama, atau provider nyata. Riwayat verifikasi tersedia di [arsip pengembangan](../../output/pengembangan/README.md).
