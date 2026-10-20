# 6. Composition dan bantuan dari luar

Tujuan: melihat bagaimana object bekerja sama tanpa harus saling mewarisi.

## “Mempunyai” berbeda dengan “merupakan”

Pelayan memakai alat tulis, tetapi pelayan bukan jenis alat tulis. Begitu pula
`ChatbotService` memakai pembuat teks, penafsir pesan, dan pencari menu; ia bukan
turunan dari semua bagian itu.

Dalam pembahasan sehari-hari pengembang, penyusunan object dari object bantuan
sering disebut composition. Pada UML yang lebih ketat, composition juga dapat
menyatakan kepemilikan umur object. Object bantuan yang diberikan dari luar
tidak selalu dimiliki secara eksklusif; jangan menggambar berlian penuh tanpa
memeriksa kepemilikannya.

## Contoh latihan

```python
from recommendation.services.text_generator import TextGenerator


class GeneratorLatihan(TextGenerator):
    def generate(self, prompt: str) -> str | None:
        return 'Silakan lihat pilihan menu.'


class PelayanLatihan:
    def __init__(self, pembuat_teks: TextGenerator) -> None:
        self.pembuat_teks = pembuat_teks

    def menyapa(self) -> str:
        hasil = self.pembuat_teks.generate('Buat sapaan')
        return hasil if hasil is not None else 'Halo, mau pilih menu apa?'


pelayan = PelayanLatihan(GeneratorLatihan())
print(pelayan.menyapa())
```

`PelayanLatihan` mempunyai pembuat teks. Pemberian object bantuan lewat
`__init__` sering disebut **dependency injection**. Artinya sederhana:
“alat yang dibutuhkan diberikan dari luar”.

Manfaatnya: untuk mencoba pembuat teks lain, kita mengganti object yang
diberikan, tanpa mengubah isi `menyapa`.

## Contoh nyata pada chatbot

Buka [`ChatbotService.__init__`](../../recommendation/services/chatbot.py):

1. Parameter `gemini_client` menerima `TextGenerator` opsional.
2. Jika tidak diberikan, layanan menyiapkan adapter default.
3. Generator dipakai melalui `TurnGenerator` oleh bagian AI yang membutuhkan.
4. Penafsir, pencari menu, dan penyusun respons mempunyai tugas berbeda.

Membuat adapter default belum berarti API dipanggil. Panggilan baru bergantung
pada tugas, konfigurasi, dan pemeriksaan penggunaan.

[`SemanticReranker`](../../recommendation/services/ai/semantic_reranker.py)
juga menerima generator melalui constructor. Ini contoh lain alat bantuan
diberikan dari luar agar mudah diuji.

## Bandingkan tiga hubungan

| Hubungan | Pertanyaan | Contoh |
|---|---|---|
| Inheritance | Apakah ini merupakan jenis dari induknya? | `GeminiClient` adalah `TextGenerator`. |
| Memakai object bantuan | Apakah bagian ini membutuhkan bantuannya? | Chatbot memakai generator. |
| Hubungan data | Apakah data ini menunjuk data lain? | Menu menunjuk kategori di database. |

Relasi database tidak otomatis menjadi inheritance Python.

## Cek pemahaman

1. Apa yang diberikan dari luar pada `PelayanLatihan`?
2. Mengapa cara ini membantu tes tanpa menghubungi Google?
3. Mengapa semua hubungan object tidak tepat digambar sebagai composition UML penuh?

Lanjut: [SOLID](solid.md).
