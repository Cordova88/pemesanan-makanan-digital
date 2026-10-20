# 2. Enkapsulasi

Tujuan: memahami mengapa data tidak selalu dibiarkan diubah langsung.

## Mengapa perlu jalur khusus?

Di restoran, total pesanan sebaiknya dihitung dari menu dan jumlah porsi.
Jika siapa pun dapat menulis total sesukanya, isi pesanan dan totalnya mudah
berbeda. Pada kode, enkapsulasi membantu mengumpulkan data dan aturan pemakaiannya
di tempat yang sama.

Ini bukan sekadar membuat nama atribut memakai garis bawah. Yang penting:
**bagian mana boleh dibaca, dan lewat jalur apa data diperiksa atau berubah?**

## Contoh nyata: batas harga

```python
from decimal import Decimal

from recommendation.services.budget import BudgetConstraint

budget = BudgetConstraint(maximum=Decimal('10000'))
print(budget.maximum)

try:
    budget.maximum = Decimal('20000')
except AttributeError:
    print('Buat batas baru melalui jalur yang disediakan.')
```

Nilai dapat dibaca melalui `maximum`, tetapi property itu tidak menyediakan
setter untuk menggantinya. Jika perlu batas lain, buat object baru:

```python
budget_baru = BudgetConstraint(maximum=Decimal('20000'))
print(budget_baru.maximum)
```

`__init__` memeriksa nilainya. Misalnya, minimum yang lebih besar dari maksimum
ditolak, sehingga object tidak dimulai dalam keadaan yang tidak masuk akal.

## Contoh nyata: pilihan menu

Buka [`MenuSelection`](../../menu/selection.py):

1. `from_ids()` memeriksa opsi yang dikirim pelanggan.
2. Opsi dan tambahan disimpan dalam tuple privat.
3. Property `options` dan `addons` menyediakan cara membacanya.
4. `unit_price` menghitung harga berdasarkan pilihan tersebut.

Tuple mencegah koleksi diubah dengan `.append()`. Ini tidak membuat seluruh
object/menu di dalamnya kebal perubahan. Katalog tetap bisa berubah dan harus
diperiksa lagi pada alur yang memerlukannya.

Pada percakapan, [`ConversationSession`](../../recommendation/services/conversation_session.py)
juga menyediakan method untuk menyimpan fokus dan pencarian. Pengembang tidak
perlu menebak banyak nama key setiap kali mengubah percakapan.

## Batas konsep ini

Python memakai `__nama` untuk membedakan nama internal class, bukan untuk
menyembunyikan rahasia dari penyerang. Enkapsulasi **tidak menggantikan** izin
akses, validasi request, CSRF, atau penyimpanan API key yang benar.

## Cek pemahaman

1. Apa manfaat membaca `maximum` melalui property?
2. Mengapa tuple tidak berarti seluruh katalog menjadi tidak bisa berubah?
3. Mengapa total keranjang tetap harus dihitung server meskipun kode memakai enkapsulasi?

Lanjut: [abstraksi](abstraction.md).
