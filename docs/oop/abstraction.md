# Catatan pendamping: abstraksi

[Kembali ke indeks](README.md) · Materi utama: [Modul 6](polymorphism.md).

Abstraksi membantu pemanggil mengetahui pekerjaan yang dapat diminta tanpa harus
membaca seluruh cara kerjanya. Contoh formalnya adalah
[TextGenerator](../../recommendation/services/text_generator.py).

```python
class TextGenerator(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str | None:
```

Cuplikan deklarasi proyek ini tidak menampilkan import dan isi method.
Janji dasarnya menerima prompt dan mengembalikan teks atau None. Implementasi
konkret tersedia pada GeminiClient dan TurnGenerator. ABC melarang instansiasi
turunan yang belum memenuhi abstract method, tetapi tidak memeriksa kebenaran
semua kalimat hasil provider.

## Jangan menyamakan dua kontrak

| Kebutuhan | Lokasi nyata | Batas |
|---|---|---|
| Membuat teks umum | TextGenerator.generate | str atau None. |
| Meminta format ranking | TextGenerator.generate_ranking | Implementasi bawaan meneruskan ke generate. |
| Percakapan dengan tool | GeminiClient.converse | Kemampuan tambahan di luar kontrak TextGenerator. |
| Menjalankan percakapan AI-first | GeminiAssistant.respond | Memakai converse dan tool katalog. |

Abstraksi juga dapat berupa antarmuka layanan, tanpa harus selalu menggunakan
ABC. CartService menyediakan add_item tanpa meminta view mengatur langsung
seluruh list internalnya. Itu berbeda dari menjadikan CartService abstract class.

Lima kasus yang dihitung untuk materi polimorfisme dan abstraksi tersedia di
[Modul 6](polymorphism.md). Tidak perlu membuat class fiktif agar jumlah contoh
terpenuhi.
