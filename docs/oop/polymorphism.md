# 5. Polymorphism — satu cara memanggil, beberapa pelaksanaan

Tujuan: memahami manfaat aturan induk ketika object yang dipakai dapat berbeda.

## Melanjutkan pembuat teks

Bagian aplikasi meminta `generate(prompt)`. Saat pengujian, pembuat teks bisa
berupa object latihan. Saat konfigurasi mengizinkan, provider asli dapat
menjalankan pekerjaan dengan cara lain. Pemanggil tidak perlu membuat cabang
untuk setiap nama class jika semuanya memenuhi aturan yang sama.

## Coba contoh ini

```python
from recommendation.services.text_generator import TextGenerator


class GeneratorSiap(TextGenerator):
    def generate(self, prompt: str) -> str | None:
        return 'Ada beberapa pilihan untuk dilihat.'


class GeneratorTidakTersedia(TextGenerator):
    def generate(self, prompt: str) -> str | None:
        return None


def minta_teks(generator: TextGenerator) -> str:
    hasil = generator.generate('Bantu pilih menu')
    return hasil if hasil is not None else 'Gunakan balasan lokal.'


print(minta_teks(GeneratorSiap()))
print(minta_teks(GeneratorTidakTersedia()))
```

Fungsi `minta_teks` sama, tetapi object yang diberikan berbeda. `None` tetap
memenuhi aturan `TextGenerator`; hasil tidak tersedia memang bagian dari
kemungkinan yang harus ditangani pemanggil.

Ini contoh latihan antarmuka pembuat teks, bukan format balasan HTTP chatbot.
Pada aplikasi, keluaran AI masih perlu diperiksa sebagai data/teks yang sesuai.

## Apa hubungannya dengan override?

- **Override:** turunan menyediakan pelaksanaan method induk.
- **Polymorphism:** pemanggil dapat memakai beberapa pelaksanaan melalui cara
  pemanggilan yang sama.

Keduanya berkaitan, tetapi bukan dua istilah untuk hal yang persis sama.
Python juga dapat memakai object yang mempunyai method sesuai tanpa hubungan
induk eksplisit; modul ini sengaja menggunakan kontrak proyek yang sudah ada.

## Bukti pada proyek

Baca [`test_text_generator.py`](../../recommendation/tests/test_text_generator.py).
Cari `RecordingGenerator` dan pengujian generator yang dapat saling menggantikan.
Generator palsu membantu menguji hasil berhasil/gagal tanpa key, internet, atau
tagihan provider. Jangan menyimpulkan tes palsu membuktikan kualitas Gemini live.

## Cek pemahaman

1. Bagian mana yang berubah pada dua pemanggilan `minta_teks`?
2. Mengapa contoh tidak perlu memeriksa `type(generator)` satu per satu?
3. Apakah turunan yang mengembalikan angka bebas sudah memenuhi aturan ini?

Lanjut: [composition](composition.md).
