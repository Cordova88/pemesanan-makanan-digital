# Panduan Pemeriksaan Lokal RasaKita

Panduan ini dipakai anggota tim untuk memeriksa fitur melalui browser setelah
menjalankan proyek. Semua perintah dimulai dari folder repository yang berisi
`manage.py`. Instalasi pertama mengikuti [README](../README.md).

## 1. Siapkan lingkungan kerja

Gunakan data latihan untuk mencoba pesanan, pembayaran, atau perubahan katalog.
Tindakan tersebut benar-benar menyimpan data pada database lokal. Jika laptop
sudah mempunyai data kerja, cadangkan database dan media sebelum mencoba
perubahan yang memengaruhi data.

Aktifkan lingkungan Python dan periksa proyek:

```powershell
.\.venv\Scripts\Activate.ps1
python -B manage.py check
python -B manage.py showmigrations
```

Jika ada migrasi yang belum diterapkan, hentikan server, cadangkan data, lalu
jalankan `python -B manage.py migrate`. Tidak perlu menghapus database atau
memuat ulang fixture. Setelah itu jalankan:

```powershell
python -B manage.py runserver 127.0.0.1:8890 --noreload
```

Profil default memakai mode lokal tanpa Gemini. API key tidak diperlukan untuk
memeriksa katalog, keranjang, transaksi, atau percakapan lokal. Restart server
setelah mengubah kode Python karena perintah di atas memakai `--noreload`.

## 2. Periksa alur pelanggan

1. Buka `http://127.0.0.1:8890/` dan pastikan katalog serta foto terlihat.
2. Cari menu dan gunakan kategori untuk mempersempit hasil.
3. Buka detail menu. Pilih varian wajib jika tersedia, tambahan, jumlah, dan catatan.
4. Masukkan pilihan ke keranjang. Cocokkan harga dan jumlah dengan pilihan tadi.
5. Ganti jenis pesanan dari keranjang. Dialog harus terbuka di atas keranjang;
   setelah memilih atau membatalkan, pengguna tetap berada di keranjang.
6. Lanjut ke konfirmasi. Ringkasan bisa dibaca, sedangkan catatan dan jenis
   pesanan tidak bisa diedit di tahap ini. Kembali ke keranjang bila ingin mengubahnya.
7. Kirim satu pesanan latihan dan catat nomor pesanannya.

Untuk makan di tempat, siapkan meja/QR sesuai
[panduan penggunaan](PANDUAN_PENGGUNAAN.md#4-makan-di-tempat-dan-qr-meja).

## 3. Periksa alur staf dan kasir

Gunakan browser lain atau jendela privat agar sesi pelanggan dan operator terpisah.

1. Login melalui `/staff/login/` dengan akun yang sesuai.
2. Pada CMS, periksa apakah pesanan latihan muncul beserta jenis, jumlah,
   catatan, dan total yang benar.
3. Jalankan perubahan status sesuai pilihan yang tersedia pada aplikasi.
4. Pada `/kasir/`, pilih pesanan latihan dan catat pembayarannya satu kali.
5. Cocokkan status pembayaran dan struk dengan pesanan. Jangan membayar ulang
   pesanan yang sama untuk mengulangi percobaan.

Panduan setiap layar ada di [CMS/Admin](PANDUAN_CMS_ADMIN.md).

## 4. Periksa percakapan lokal

Buka `/chatbot/`. Cocokkan jawaban dengan menu yang tersedia pada katalog,
bukan dengan daftar menu milik anggota lain.

| Percakapan | Yang diperhatikan |
|---|---|
| `minuman maksimal 10 ribu` | Hasil sesuai kategori dan batas harga. |
| Lanjut `minimal 5 ribu` | Batas baru mengganti batas lokal lama. |
| `harga [nama menu] berapa?` | Harga sesuai katalog; pertanyaan tidak membuat pesanan. |
| `cari menu lain` | Alternatif mengikuti konteks yang masih berlaku. |
| Meminta varian atau tambahan | Bot mengarahkan pemilihan melalui detail menu/keranjang. |
| Pertanyaan alergi | Bot tidak menjamin keamanan bahan dari tag menu. |
| Menekan **Mulai Lagi** | Percakapan dimulai ulang dan keranjang tidak dikosongkan. |

Cara kerja budget dan konteks dijelaskan pada [Chatbot.md](Chatbot.md).
Pemeriksaan lokal ini tidak memerlukan pengaktifan Gemini.

## 5. Laporkan masalah agar bisa diulang

Sertakan branch/revisi, langkah yang dilakukan, hasil yang diharapkan, dan hasil
yang muncul. Untuk chatbot, urutan pesan sebelumnya dapat memengaruhi hasil.
Sertakan tangkapan layar bila membantu, dengan data pribadi disamarkan.

Contoh laporan: “Dari keranjang, saya membuka jenis pesanan lalu menekan batal.
Seharusnya tetap di keranjang, tetapi halaman berpindah ke katalog.”

Jangan membagikan API key, password, cookie, atau isi sesi. Keberhasilan mencoba
satu alur belum membuktikan seluruh fitur benar; fokuskan pemeriksaan pada
bagian yang berubah dan alur yang bergantung padanya.
