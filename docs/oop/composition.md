# Catatan pendamping: memakai object bantuan

[Kembali ke indeks](README.md) · Materi utama: [Modul 4](uml-class-relationships.md).

## “Mempunyai” berbeda dari “merupakan”

[TurnGenerator](../../recommendation/services/ai/turn_generator.py) mempunyai
referensi provider melalui constructor. Ia juga merupakan turunan TextGenerator.
Satu class dapat memiliki dua jenis hubungan tersebut sekaligus.

```python
class TurnGenerator(TextGenerator):
    def __init__(self, provider: TextGenerator) -> None:
        self.provider = provider
        self.reset()
```

Cuplikan ini berasal dari proyek. Provider dibuat atau disediakan dari luar.
Karena itu, menyimpan self.provider tidak dengan sendirinya membuktikan komposisi
UML dengan kepemilikan eksklusif. Dalam percakapan desain, “object composition”
sering dipakai secara umum untuk merangkai layanan; arti umum itu lebih longgar
daripada simbol wajik terisi pada diagram UML.

## Pertanyaan sebelum menggambar komposisi

1. Siapa yang membuat object bagian?
2. Apakah bagian boleh dipakai bersama oleh object lain?
3. Apakah bagian memiliki arti dan siklus hidup mandiri?
4. Apakah pelepasan referensi di memori sama dengan menghapus baris database?
5. Apakah kode benar-benar mengatur ketergantungan hidup bagian kepada pemilik?

Pada Python, del menghapus suatu referensi; object yang masih dirujuk tempat lain
tidak otomatis musnah. Pada Django, periksa on_delete: OrderItem.order memakai
PROTECT, sehingga jangan menyatakan penghapusan Order otomatis menghapus semua
barisnya. Lima kasus relasi beserta diagram ada di
[Modul 4](uml-class-relationships.md).
