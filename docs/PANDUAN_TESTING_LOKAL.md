# Panduan pengujian lokal RasaKita V1

> Untuk instalasi baru branch `ahmad`, mulai dari [README proyek](../README.md).
> Runner di folder `output/` pada panduan ini adalah alat workspace penulis;
> folder itu tidak ikut clone GitHub dan tidak diperlukan untuk menjalankan web.

Disusun 18 Oktober 2026. Tujuan: memeriksa fitur dan perubahan kode sebelum
hosting, dengan membedakan pengujian tanpa API dari percobaan Gemini nyata.
Panduan ini bukan catatan bahwa semua langkah manual di bawah sudah dijalankan.

Riwayat fase dan hasil pengujian terdahulu berada di [arsip pengembangan](../../output/pengembangan/README.md). Hasil mock tidak membuktikan kualitas Gemini live atau kesiapan hosting.

## 1. Pilih jenis pengujian

| Jenis | Perlu API key? | Menghubungi Google? | Cocok untuk |
|---|---|---|---|
| Tes otomatis terisolasi | Tidak | Tidak; provider dipalsukan | Regresi kode, validasi, aturan rekomendasi |
| Coba browser profil v1 | Tidak | Tidak; Gemini dinonaktifkan | Tampilan, katalog, budget, percakapan lokal |
| Percobaan Gemini nyata | Ya | Ya, bila jalur provider dipanggil | Koneksi, model, respons dan fallback integrasi |

Mulai dari dua baris pertama. API key baru tidak diperlukan untuk membuktikan
aturan budget, filter katalog, memori percakapan, dan validasi input lokal.

## 2. Persiapan dan batas data

- Aktifkan virtual environment proyek yang dependency-nya sudah tersedia.
- Gunakan Python 3.14+ yang sesuai proyek. Jangan memasang ulang dependency bila
  lingkungan yang ada sudah bekerja.
- Tes otomatis di bawah memakai SQLite dalam memori, media sementara Windows,
  dan cache lokal terisolasi. Tidak memuat `.env` atau memakai database katalog.
- Percobaan browser dengan `v1_settings` memakai `db.sqlite3` dan `media/` v1
  yang sebenarnya. Membuat pesanan, mengedit katalog, dan login dapat menyimpan
  data di sana. Untuk menguji transaksi, gunakan salinan kerja/database percobaan
  yang sengaja Anda siapkan; jangan memuat fixture ke database katalog yang ada.
- Jangan menjalankan `seed_demo`, migrasi atau `loaddata` sebagai langkah rutin
  pengujian pada database pengguna.

## 3. Jalankan pengujian otomatis tanpa Gemini

Dari folder workspace **UTS**, bukan dari dalam folder v1:

```powershell
python -B output/ai-v2-phase7/run_tests.py menu cart orders users recommendation
```

Untuk fokus chatbot:

```powershell
python -B output/ai-v2-phase7/run_tests.py recommendation
```

Gunakan runner Phase7 ini, karena sudah menyiapkan cache dan isolasi pengujian
terbaru. Folder `output/` adalah pendamping workspace; runner tersebut tidak ikut
otomatis jika Anda hanya menyalin folder v1. Periksa keberadaannya terlebih dahulu.
Runner lama menggunakan media di workspace dan tidak menjadi pilihan utama lagi.
Jika modul pengujian seperti `dotenv` belum tersedia, catat dependency pengujian
yang hilang dan pasang di virtual environment; jangan mengganti ke database pengguna.

Lulus jika akhir keluaran menunjukkan `OK`, tanpa kegagalan/error dan pemeriksaan
Django tidak menemukan masalah. Catat tanggal, revisi, jumlah tes, dan hasil nyata;
angka historis bukan bukti kelulusan source terbaru.

## 4. Coba chatbot lokal di browser

Sebelum menjalankan server pada database v1 yang sudah ada, periksa migrasi:

```powershell
python -B manage.py showmigrations menu --settings=v1_settings
```

Jika `0005_menuitemalias` masih bertanda `[ ]`, hentikan server percobaan Anda
dan salin `db.sqlite3` sebagai cadangan, lalu terapkan migrasi tersebut:

```powershell
python -B manage.py migrate menu 0005_menuitemalias --settings=v1_settings
```

Migrasi ini menambah tabel alias nama menu, indeks dan constraint; tidak memuat
fixture atau mengganti katalog. Pastikan hasilnya `Applying menu.0005_menuitemalias...
OK` dan pemeriksaan berikutnya menunjukkan `[X]`. Jangan menjalankan `makemigrations`,
`seed_demo`, `loaddata`, atau menghapus database untuk mengatasi migrasi tertunda ini.
Jika semua migrasi menu sudah `[X]`, langkah penerapan tersebut tidak diperlukan.

Tanpa tabel alias, halaman `/chatbot/` masih bisa tampil, tetapi request chat
dapat mengembalikan 503 karena constructor membaca alias katalog. Error ini
tidak berarti chatbot membutuhkan Gemini. Tes otomatis menjalankan migrasi pada
database terpisah; kelulusannya tidak mengubah schema database lokal pengguna.

Dari folder `pemesanan-makanan-digital-v1`, jika belum ada server di port tersebut:

```powershell
python -B manage.py runserver 127.0.0.1:8890 --noreload --settings=v1_settings
```

Buka `http://127.0.0.1:8890/chatbot/`. Jika server sudah berjalan, gunakan server
itu atau pilih port lain; jangan menghentikan proses yang belum dikenali.
Profil ini menampilkan pemberitahuan mode lokal dan mematikan Gemini, termasuk
jika terminal memiliki `GEMINI_API_KEY`.

Gunakan katalog yang tersedia sebagai sumber hasil yang diharapkan:

Untuk kasus yang berdiri sendiri, tekan tombol reset sebelum mencoba kasus
berikutnya. Untuk menguji memori, sengaja lanjutkan dalam sesi yang sama.
Contoh: setelah `budget 1 rupiah`, `jangan pedas` tetap memakai batas Rp1;
hasil kosong dapat benar. Sapaan `halo` dan refresh halaman bukan reset.
Permintaan `yang terakhir` memerlukan kartu rekomendasi sebelumnya, bukan
sekadar sapaan. `yang lain` tidak boleh mengulang menu yang sudah dilewati;
jika kandidat habis, chatbot harus menjelaskannya, bukan menjanjikan kartu baru.

Setelah perubahan kode Python, hentikan server percobaan Anda dengan Ctrl+C dan
jalankan kembali perintah `runserver` di atas. Opsi `--noreload` tidak memuat kode
baru secara otomatis. Refresh halaman setelah server kembali berjalan.

| Percobaan | Input/langkah | Hasil yang diperiksa |
|---|---|---|
| Sapaan | `halo` | Respons wajar, tidak error |
| Budget | `makan dengan budget 20000` | Kartu yang ditawarkan memenuhi batas budget sesuai aturan rekomendasi; tidak mengarang harga |
| Budget sangat kecil | `budget 1 rupiah` | Penjelasan bila tidak ada pilihan; tidak memaksakan menu mahal |
| Variasi nominal | `aku mau minuman 10k`, `minuman 10000`, `minuman 10.000` | Ketiganya memakai maksimum Rp10.000, bukan nama menu yang mengandung harga |
| Rupiah literal | `minuman 10 rupiah` lalu `minuman 10.000` | Batas pertama Rp10; pesan kedua menggantinya menjadi Rp10.000 |
| Objek di luar menu | `aku ingin motor` | Menjelaskan keterbatasan dan mengarahkan ke menu; tidak mengaku menjual motor |
| Variasi | Ulangi permintaan nonmakanan beberapa kali | Pilihan kalimat dapat bervariasi; tidak menjanjikan semua 10 variasi muncul berurutan |
| Pengecualian | `jangan pedas` | Kandidat mematuhi tag/pengecualian yang tersedia; periksa data menu |
| Lanjutan | Setelah budget: `yang lain` | Konteks dan budget tetap diperhitungkan |
| Ganti konteks | `sekarang cari minuman` | Fokus berubah; batas yang masih berlaku tidak hilang sembarangan |
| Reset | Tombol reset lalu sapaan | Preferensi percakapan dibersihkan; reset bukan penghapus kuota |
| Referensi | Pilih/referensikan saran terakhir | Menu diverifikasi kembali, tidak memakai harga/ketersediaan lama |
| Referensi nama | `yang es kelapa` | Nama persis didahulukan dari tag dingin/es, tanpa melewati budget |
| Keranjang | Tambahkan satu saran pada database percobaan | Item/jumlah benar; harga dihitung server |

Jangan menilai hanya kelancaran kalimat. Catat nama/ID menu, harga, tag, budget,
dan urutan pesan. Jika tidak ada menu dengan tag yang diminta, respons tanpa
kandidat dapat benar. Jangan menganggap rekomendasi kondisi fisik sebagai nasihat medis.

Jika ada dua minuman Rp10.000 tetapi hanya satu muncul, periksa keduanya di CMS
v1 yang sama: aktif, tersedia, kategori aktif/Minuman, harga dasar, dan tag yang
memenuhi pencarian. Periksa juga pengecualian, pencarian nama persis, dan riwayat
`yang lain`; reset menghapus konteks pencarian, bukan mengubah katalog.
Harga sama tidak menjamin kesesuaian semua filter. Jangan memuat ulang fixture
untuk memperbaiki hasil; itu dapat menimpa katalog yang sudah diedit.

Kategori `Minuman` sekarang cukup untuk filter jenis `drink`, walaupun tag drink
belum dipasang. Ini hanya pemaknaan filter: tidak menambah tag pada database,
tidak mengarang label rasa/bahan, dan tidak melewati filter lainnya. Permintaan
`minuman manis` tetap memerlukan bukti tag Manis. Uji dengan dua minuman harga
sama, salah satunya hanya bertag Manis; keduanya harus dapat ditemukan.
Setelah semua kandidat ditampilkan, `yang lain` dapat tetap kosong karena kartu
yang sudah dilewati tidak diulang. Gunakan reset untuk mengulang tes mandiri.

Validasi API (JSON salah, pesan >500 karakter, tipe salah, batas body, CSRF,
429/503) terutama dibuktikan oleh tes otomatis. Form browser memiliki batas
karakter, sehingga menempel 501 karakter di form belum menguji batas server.
Jika menguji endpoint `/api/recommendation/chat/` secara manual, pakai sesi dan
token CSRF valid; respons 403 tanpa token membuktikan CSRF, bukan validasi JSON.

### Budget dan AI pada mode lokal

V3 Phase1 menambahkan koreksi lokal berbasis nama katalog. Coba urutan
`aku mau minuman 10k` → `yang es kelapa` → `eh yang es jeruk aja deh` → `yang lain`.
Fokus menu berpindah tanpa mengunci seluruh candidate pool. `Bukan Es Kelapa,
Es Jeruk aja` menolak ID Kelapa saja; tidak melarang semua minuman dingin.
Permintaan alternatif bukan penolakan eksplisit. Setelah fokus, kandidat yang
pernah ditampilkan dapat ditawarkan kembali jika tidak ada kandidat belum dilihat,
selama tidak ditolak eksplisit. Nama/kategori/status di database tetap menentukan
hasil. Revision metadata Phase1 belum melindungi multitab/request serentak.

Aturan budget terbaru (pilihan pengguna, 18 Oktober 2026): nominal baru mengganti
seluruh rentang lama. `maksimal 15000` → `diatas 5000` menghapus maksimum lama;
`minuman 10k` berikutnya menghapus minimum lama dan menetapkan maksimum 10000.
Untuk dua batas, tulis satu pesan seperti `minuman antara 5 ribu sampai 10 ribu`.
Permintaan kategori baru tidak mewarisi budget lokal kategori lama. Dalam konteks yang sama, budget tetap berlaku. `balik ke minuman tadi` dapat memulihkan batas pencarian sebelumnya; budget total rencana dan restriction global yang dinyatakan eksplisit tetap berlaku lintas kategori. Nominal lokal baru mengganti rentang lokal pencarian tersebut. `maksimal 20rb` mencakup harga <=20000,
bukan harga persis atau toleransi sekitar 20000. Permintaan relatif `lebih murah`
tetap memerlukan acuan dan mempertahankan batas keras yang sudah berlaku.

Mode lokal bukan seluruhnya jawaban statis: menu, harga, kategori, tag dan status
dibaca dari database. Namun interpretasi lokal memakai aturan dan variasi kalimat
template. Gemini yang aktif dapat membantu klasifikasi objek ambigu, usulan
perubahan tag/intent dan ungkapan pada jalur tertentu. Tidak semua pesan dikirim;
jalur budget eksplisit tetap lokal saat ini. Pengujian offline/fake provider tidak
membuktikan mutu atau koneksi model nyata. AI tidak menjadi sumber harga/stok;
tag yang diusulkan harus ada dalam daftar yang diizinkan dan filter akhir server
tetap menentukan kandidat. Perlu pengujian Gemini terpisah bila itu target evaluasi.


## 5. Mengapa `.env` bisa tidak ada?

Pada source v1 saat panduan dibuat:

- `manage.py` memilih `v1_settings` secara default.
- `v1_settings.py` menetapkan `GEMINI_ENABLED=False` dan key kosong.
- `config/settings.py` membaca variabel lingkungan proses, bukan memuat `.env`.
- `GeminiClient` memerlukan flag aktif serta key, dan tidak memuat `.env` sendiri.

`.env` adalah berkas opsional untuk menyimpan nilai lokal; bukan API key itu
sendiri dan bukan berkas yang otomatis dibaca Django. Tidak adanya `.env`
bukan kerusakan proyek. Panduan ini tidak memeriksa apakah Anda sudah membuat
berkas tersebut setelah baseline. **Mengisi `.env` tanpa pemuat dan tanpa profil
Gemini yang aktif tidak cukup.** Jangan membagikan isinya ke chat atau Git.

## 6. Opsional: buat API key Gemini baru

Langkah ini hanya untuk percobaan integrasi nyata setelah tes lokal lulus.

1. Masuk ke [Google AI Studio](https://aistudio.google.com/apikey) dengan akun Anda.
2. Pilih/buat proyek khusus percobaan, lalu buat API key. Jika proyek tidak
   terlihat, impor proyek melalui halaman Projects. Ikuti izin yang diminta
   antarmuka; akun organisasi dapat memerlukan persetujuan administrator.
3. Beri nama yang mudah dikenali, misalnya `rasakita-local-test`. Key berbeda
   pada proyek yang sama tidak otomatis memiliki kuota/tagihan terpisah.
4. Periksa pembatasan key, model yang tersedia, kuota serta status billing proyek.
   Jangan menganggap API gratis hanya karena aplikasinya berjalan di localhost.
5. Simpan key secara pribadi. Gunakan key percobaan terpisah dari produksi.
   Jika pernah bocor, ganti dan nonaktifkan key yang bocor.

Google mendokumentasikan pengelolaan key, proyek, pembatasan dan variabel
lingkungan pada [panduan API key](https://ai.google.dev/gemini-api/docs/api-key).
Pilih nama model teks yang tersedia untuk akun/proyek dari
[daftar model resmi](https://ai.google.dev/gemini-api/docs/models).
Jangan mengandalkan nama model lama yang tertulis pada profil lokal v1.

## 7. Profil percobaan Gemini tanpa mengubah profil lokal utama

Ini **contoh berkas yang Anda buat nanti**, bukan profil yang sudah diaktifkan.
Di folder v1, buat `local_gemini_settings.py` dengan isi berikut. Tidak ada key
di dalam kode. Tambahkan nama berkas itu ke `.gitignore` lokal sebelum dipakai.
Profil tetap memakai database/media v1; jalankan pada salinan percobaan bila
Anda hendak melakukan tindakan yang mengubah data.

```python
from v1_settings import *
import os

GEMINI_ENABLED = os.environ.get('GEMINI_ENABLED', 'false').lower() == 'true'
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', '')
if GEMINI_ENABLED and (not GEMINI_API_KEY or not GEMINI_MODEL):
    raise RuntimeError('Isi key dan nama model melalui lingkungan proses.')

# Batas percobaan kecil; satu pesan dapat melewati beberapa tahap provider.
GEMINI_MAX_CALLS_PER_SESSION = 2
GEMINI_CLIENT_CALLS_PER_DAY = 3
GEMINI_GLOBAL_CALLS_PER_DAY = 5
CHATBOT_REQUIRE_SHARED_CACHE = False  # hanya profil lokal DEBUG=True
CACHES = {'default': {
    'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    'LOCATION': 'rasakita-local-gemini-test',
}}
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'recommendation.services.gemini': {
        'handlers': ['console'], 'level': 'INFO', 'propagate': False,
    }},
}
```

Jangan gunakan profil ini untuk hosting. Kuota LocMem hilang ketika proses
direstart dan tidak menyatukan beberapa proses. Batas ini bukan batas uang.

### Pilihan A — tanpa `.env` dan tanpa dependency tambahan

Dari folder v1, gunakan terminal baru. Ganti placeholder model dengan model
yang sudah Anda periksa. Key dimasukkan melalui prompt tersembunyi Python,
sehingga tidak ditulis langsung pada riwayat perintah.

```powershell
$env:GEMINI_ENABLED = 'true'
$env:GEMINI_MODEL = 'GANTI_DENGAN_MODEL_TEKS_YANG_TERSEDIA'
python -B -c "import getpass,os,runpy,sys; os.environ['GEMINI_API_KEY']=getpass.getpass('Gemini API key: '); sys.argv=['manage.py','runserver','127.0.0.1:8891','--noreload','--settings=local_gemini_settings']; runpy.run_path('manage.py',run_name='__main__')"
```

Buka `http://127.0.0.1:8891/chatbot/`. Key hanya diberikan ke proses Python itu;
tidak disimpan sebagai `.env` oleh perintah ini. Setelah selesai, Ctrl+C lalu
tutup terminal percobaan. Jangan menampilkan variabel key untuk diagnosis.

### Pilihan B — memakai `.env` yang Anda buat sendiri

Gunakan ini jika Anda ingin menyimpan konfigurasi untuk dipakai ulang.
File `.env` sudah diabaikan `.gitignore`, tetapi Git ignore tidak mencegah
sinkronisasi OneDrive, pencadangan, atau pembacaan oleh pengguna komputer lain.
Pilihan A lebih sesuai bila Anda tidak ingin menyimpan key di folder sinkronisasi.

1. Di folder v1, buat `.env` melalui editor pribadi. Jika sudah ada, jangan
   menimpa; sesuaikan hanya entri yang diperlukan. Contoh berikut berisi placeholder:

   ```dotenv
   GEMINI_ENABLED=true
   GEMINI_API_KEY=ISI_KEY_BARU_DI_KOMPUTER_ANDA
   GEMINI_MODEL=ISI_MODEL_TEKS_YANG_TERSEDIA
   ```

2. Untuk pemuat eksplisit ini, instal dependency opsional **di virtual environment**:

   ```powershell
   python -m pip install "python-dotenv[cli]"
   ```

   Dependency ini bukan bagian dari `requirements.txt` utama saat panduan dibuat.
   Panduan tidak memasangnya otomatis. Rujukan pemuat dan CLI:
   [dokumentasi python-dotenv](https://bbc2.github.io/python-dotenv/).

3. Dari terminal percobaan yang tidak berisi variabel Gemini lama, jalankan:

   ```powershell
   python -m dotenv -f .env run --no-override -- python -B manage.py runserver 127.0.0.1:8891 --noreload --settings=local_gemini_settings
   ```

   `--no-override` mempertahankan variabel lingkungan yang sudah ada. Jika flag
   atau model berbeda dari harapan, tutup terminal tersebut dan gunakan terminal
   bersih; jangan mencetak key. Gunakan profil khusus di atas, bukan `v1_settings`.

4. Periksa hanya status ignore, bukan isi rahasia:

   ```powershell
   git check-ignore .env local_gemini_settings.py
   ```

   Keduanya harus terdaftar sebelum Anda mempertimbangkan commit. Ignore tidak
   menghapus file yang sudah pernah dilacak Git; hentikan dan tangani riwayat
   rahasia bila key pernah terlanjur masuk repository.

## 8. Buktikan Gemini benar-benar dipanggil

1. Catat waktu mulai dan penggunaan awal pada dashboard penyedia.
2. Kirim satu pesan percobaan tanpa data pribadi. Pesan lokal yang mudah dikenali
   dapat dijawab tanpa provider; kalimat yang terdengar alami bukan bukti API dipakai.
3. Periksa metadata terminal: `event=provider_attempt`, `outcome`,
   `provider_called`, model, latency, dan token bila tersedia. Satu pesan dapat
   menyebabkan lebih dari satu upaya API.
4. `provider_called=true` berarti aplikasi mencoba memanggil SDK; hasil
   `success` menunjukkan respons diterima. Ini belum menjamin keluaran dipakai
   chatbot, karena validasi keluaran dapat memilih fallback lokal.
5. Cocokkan dengan dashboard penggunaan Gemini proyek. Data dapat terlambat
   diperbarui. Token tidak diketahui dan `estimated_cost=null` bukan berarti nol.
6. Bila `disabled/unconfigured/quota_exhausted/guard_unavailable`, periksa flag,
   profil, model, atau cache tanpa menampilkan key. `provider_error` bersifat
   umum; periksa akses model/kuota/key pada dashboard, jangan mematikan pembatas.
7. Hentikan setelah bukti cukup. Kembali ke server `--settings=v1_settings`
   untuk pengujian biasa tanpa API; tidak perlu menghapus key yang masih diperlukan.

Jangan memakai keluaran `chatbot_usage` dari proses LocMem terpisah untuk
mengukur server lokal: cache tiap proses berbeda. Jangan mengulang key/pesan
berkali-kali untuk mengatasi fallback; itu dapat menambah pemakaian API.

## 9. Catatan hasil dan serah terima

Salin format berikut tanpa rahasia:

| Tanggal/revisi/profil | Kasus | Hasil yang diharapkan | Hasil nyata | Lulus/gagal | Bukti aman |
|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ID permintaan/hasil tes, tanpa pesan pribadi/key |

Checklist: tes otomatis OK; perilaku budget/konteks diperiksa; katalog tidak
berubah tanpa sengaja; transaksi hanya pada data percobaan; hasil API nyata
dipisahkan dari hasil mock; penggunaan penyedia diperiksa bila Gemini aktif.
Dokumen ini tidak membuat profil, key, `.env`, database atau transaksi untuk Anda.

Pertanyaan pemahaman: mengapa key di `.env` belum mengaktifkan Gemini pada
profil v1? Mengapa respons chatbot yang bagus belum membuktikan API dipanggil?
