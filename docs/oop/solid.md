# 7. SOLID dengan bahasa sederhana

Tujuan: memakai lima pertanyaan untuk menilai desain, bukan menghafal singkatan
atau mengklaim seluruh proyek sudah sempurna.

## Lima pertanyaan

| Prinsip | Pertanyaan sederhana | Contoh pada RasaKita |
|---|---|---|
| S — Single Responsibility | Apakah bagian ini punya tanggung jawab yang jelas? | `StaffAccess` memeriksa peran; bukan menghitung pembayaran. |
| O — Open/Closed | Bisakah menambah pelaksanaan tanpa membongkar setiap pemanggil? | Generator latihan baru dapat mengikuti `TextGenerator`. |
| L — Liskov Substitution | Apakah turunan tetap memenuhi janji induk? | `generate` menghasilkan teks atau `None`, bukan sembarang struktur. |
| I — Interface Segregation | Apakah pemanggil dipaksa memahami pekerjaan yang tidak diperlukannya? | Kontrak `TextGenerator` kecil, hanya pekerjaan membuat teks. |
| D — Dependency Inversion | Apakah bagian pemakai bergantung pada aturan umum, bukan detail satu alat? | `SemanticReranker` menerima `TextGenerator`, bukan membuat koneksi Google sendiri. |

## Ikuti satu contoh

Bagian rekomendasi ingin memberi penjelasan menu. Ia menyerahkan pembuatan
teks kepada generator. Adapter provider mengurus panggilan eksternal; bagian
penjelasan memeriksa apakah hasil sesuai fakta yang diberikan.

Pembagian itu membuat kita bisa mengganti generator dengan versi latihan.
Namun, pemeriksaan fakta tetap diperlukan. Mengikuti antarmuka bukan berarti
isi jawaban sudah benar atau aman ditampilkan.

## Tempat melihat penerapannya

- [`users/access.py`](../../users/access.py): keputusan peran dipusatkan.
- [`text_generator.py`](../../recommendation/services/text_generator.py): kontrak kecil.
- [`gemini.py`](../../recommendation/services/gemini.py): detail provider.
- [`semantic_reranker.py`](../../recommendation/services/ai/semantic_reranker.py): menerima alat dari luar dan memeriksa hasil.
- [`menu/selection.py`](../../menu/selection.py): aturan pilihan/harga dipakai bersama.

## Batas yang harus jujur disebutkan

`ChatbotService` masih besar dan mengatur banyak cabang percakapan. Adanya
beberapa class bantuan tidak otomatis membuat seluruh tanggung jawabnya kecil.
Kontrak generator memberi ruang mengganti pelaksanaan, tetapi perubahan aturan
dialog tetap dapat memerlukan perubahan pada router atau service.

Jadi, gunakan kalimat “bagian ini menunjukkan penerapan prinsip…” dan jelaskan
buktinya. Hindari klaim “seluruh kode sudah SOLID” hanya karena banyak class.
Model Django dan fungsi transaksi tetap mempunyai peran yang sah; tidak perlu
memindahkan semuanya ke pewarisan bertingkat.

## Latihan penilaian

Misalnya seseorang menambahkan akses database, perhitungan total, pengiriman
email, dan format HTML ke satu method. Tanyakan:

1. Apakah perubahan harga harus ikut mengubah bagian email?
2. Apakah perhitungan bisa diuji tanpa mengirim email?
3. Bagian mana dapat dipisahkan karena tugasnya berbeda?

Diskusikan dahulu; jangan memecah method menjadi banyak class tanpa tujuan.

Lanjut: [latihan proyek](latihan.md).
