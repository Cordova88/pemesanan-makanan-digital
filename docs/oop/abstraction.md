# 3. Abstraksi

Tujuan: memakai suatu pekerjaan tanpa perlu memahami semua detail pelaksanaannya.

## Mulai dari kegiatan sehari-hari

Ketika meminta “buatkan minuman”, pelanggan menyebut hasil yang diinginkan.
Cara menyiapkan bahan dan memakai alat merupakan detail pelaksanaannya.
Dalam kode, abstraksi membantu menyepakati **pekerjaan yang tersedia**, lalu
memisahkannya dari detail cara mengerjakan.

## Contoh proyek: pembuat teks

[`TextGenerator`](../../recommendation/services/text_generator.py) menyatakan:

> Object pembuat teks menyediakan `generate(prompt)`, dengan hasil teks atau `None`.

- `prompt`: petunjuk/data yang diberikan kepada pembuat teks.
- `str`: hasil berupa teks.
- `None`: hasil tidak tersedia; pemanggil perlu menangani keadaan itu.

Class tersebut memakai `ABC` dan `@abstractmethod` dari Python. Bentuk ringkas
aturan yang sama dapat dibaca seperti ini; ini **contoh penjelasan**, bukan file baru aplikasi:

```python
from abc import ABC, abstractmethod


class PembuatTeks(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str | None:
        raise NotImplementedError
```

`ABC` menandai class abstrak. `@abstractmethod` menandai pekerjaan yang harus
disediakan turunannya. `raise NotImplementedError` pada contoh bukan panggilan
Gemini; itu penanda bahwa detailnya belum diberikan.

Class abstrak belum lengkap untuk dipakai membuat hasil:

```python
try:
    pembuat = PembuatTeks()
except TypeError:
    print('Belum ada pelaksanaan generate yang lengkap.')
```

## Mengapa berguna di RasaKita?

Bagian penjelasan rekomendasi membutuhkan teks. Ia tidak perlu menangani sendiri
koneksi, timeout, dan konfigurasi SDK Google. Detail provider ditempatkan pada
[`GeminiClient`](../../recommendation/services/gemini.py). Pemanggil tetap wajib
memeriksa format dan isi hasil; teks dari provider tidak otomatis benar.

Abstraksi juga ada tanpa `ABC`: saat memakai `CartService.add_item`, view tidak
perlu menghitung ulang seluruh pilihan dengan kode sendiri. Namun, tidak semua
class yang menyembunyikan detail adalah abstract class Python.

## Bedakan dengan enkapsulasi

| Pertanyaan | Konsep yang paling dekat |
|---|---|
| Pekerjaan apa yang disediakan? | Abstraksi |
| Bagaimana data dijaga/dibaca melalui jalur tertentu? | Enkapsulasi |

Keduanya dapat hadir pada desain yang sama.

## Cek pemahaman

1. Mengapa `PembuatTeks()` ditolak pada contoh?
2. Mengapa pemanggil tetap perlu menangani `None`?
3. Apakah setiap class pada proyek harus memakai `ABC`? Jelaskan alasannya.

Lanjut: [inheritance](inheritance.md).
