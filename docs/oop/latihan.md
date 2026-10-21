# 8. Latihan dan bahan diskusi tim

Tujuan: menjelaskan konsep memakai alur proyek, bukan mengulang definisi buku.
Kerjakan latihan kode di file terpisah. Tidak perlu mengubah aplikasi atau
memakai database restoran untuk latihan awal.

## Latihan A — dua batas harga

Gunakan contoh pada [class dan object](class-dan-object.md).

1. Buat budget maksimal Rp10.000 dan Rp20.000.
2. Periksa harga Rp8.000, Rp15.000, dan Rp25.000.
3. Tulis tebakan sebelum menjalankan program.
4. Jelaskan mengapa satu class dapat menghasilkan keputusan berbeda.

Hasil acuan untuk pengecekan sesudah mencoba:

| Harga | Maksimal Rp10.000 | Maksimal Rp20.000 |
|---|---|---|
| Rp8.000 | Boleh | Boleh |
| Rp15.000 | Tidak | Boleh |
| Rp25.000 | Tidak | Tidak |

## Latihan B — batas tidak masuk akal

Coba buat `BudgetConstraint` dengan minimum Rp20.000 dan maksimum Rp10.000.
Tangani `ValueError`, lalu jelaskan mengapa penolakan saat pembuatan object
lebih membantu daripada membiarkan nilai tidak sah dipakai bagian lain.

## Latihan C — pembuat teks palsu

1. Jalankan contoh [polymorphism](polymorphism.md).
2. Buat turunan lain yang mengembalikan teks berbeda.
3. Berikan object itu ke `minta_teks` tanpa mengubah fungsi tersebut.
4. Jelaskan mana inheritance, mana override, dan mana pemakaian polymorphism.

Jangan mengganti contoh dengan panggilan Gemini nyata. Tujuannya memahami
hubungan class tanpa menambah penggunaan API.

## Latihan D — telusuri pilihan menu

Baca kode saja:

1. Buka [`CartService.add_item`](../../cart/services.py).
2. Cari pemakaian [`MenuSelection`](../../menu/selection.py).
3. Temukan pemeriksaan opsi wajib dan tambahan.
4. Temukan perhitungan harga satuan dan total.
5. Jelaskan mengapa browser tidak boleh menetapkan harga akhir sendiri.

Bedakan apa yang Anda lihat di kode dengan perilaku yang benar-benar sudah
Anda jalankan. Untuk mencoba transaksi, gunakan instalasi latihan sesuai
[panduan penggunaan](../PANDUAN_PENGGUNAAN.md), bukan data kerja anggota lain.

## Latihan E — ceritakan perjalanan satu chat

Baca [Chatbot.md](../Chatbot.md), lalu jelaskan pesan `minuman maksimal 10 ribu`:

1. Apa yang dimaksud pelanggan?
2. Informasi apa yang perlu diingat?
3. Menu seperti apa yang harus dikeluarkan dari kandidat?
4. Kapan AI mungkin diperlukan?
5. Mengapa kartu rekomendasi belum berarti pesanan sudah dibuat?

## Cara presentasi singkat

Gunakan urutan: **masalah → contoh kode → alur → alasan desain → batasnya**.
Contoh masalah: “Kami perlu menguji chatbot tanpa menghubungi provider.”
Tunjukkan `TextGenerator`, generator palsu pada tes, lalu pemanggilnya. Jelaskan
bahwa tes itu membuktikan kontrak/fallback, bukan kualitas bahasa Gemini live.

## Checklist belajar

- [ ] Bisa membedakan class dan object dengan contoh sendiri.
- [ ] Bisa menjelaskan property dan jalur validasi.
- [ ] Bisa menunjukkan induk/turunan yang benar-benar ada pada kode.
- [ ] Bisa membedakan inheritance dengan memakai object bantuan.
- [ ] Bisa menjelaskan manfaat generator palsu tanpa membuka API key.
- [ ] Bisa menunjukkan bagian yang masih besar atau mempunyai keterbatasan.

Pertanyaan penutup: mengapa “kode mempunyai banyak class” belum membuktikan
desainnya mudah dirawat? Apa yang perlu diuji ketika alat pembuat teks diganti?
