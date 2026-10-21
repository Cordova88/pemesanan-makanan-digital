# 1. Class dan object

Tujuan: memahami empat istilah dasar sebelum membahas inheritance.

## Mulai dari contoh restoran

Dua pelanggan sama-sama memiliki batas harga, tetapi nominalnya berbeda.
Program tidak perlu membuat aturan baru untuk setiap pelanggan. Program cukup
memiliki satu bentuk data “batas harga”, kemudian membuat object sesuai kebutuhan.

| Istilah | Arti sederhana | Contoh proyek |
|---|---|---|
| Class | Bentuk/cetakan yang menjelaskan data dan pekerjaan | `BudgetConstraint` |
| Object | Satu hasil pembuatan dari class | Batas maksimal Rp10.000 |
| Atribut | Informasi milik object | `maximum` |
| Method | Pekerjaan yang dapat diminta dari object | `allows(harga)` |

## Coba membuat dua object

Contoh memakai class proyek yang tidak membutuhkan database:

```python
from decimal import Decimal

from recommendation.services.budget import BudgetConstraint

budget_ani = BudgetConstraint(maximum=Decimal('10000'))
budget_budi = BudgetConstraint(maximum=Decimal('20000'))

print(budget_ani.allows(Decimal('15000')))
print(budget_budi.allows(Decimal('15000')))
```

Hasilnya `False`, lalu `True`. Class-nya sama, tetapi isi kedua object berbeda.
`Decimal` dipakai untuk nilai uang; jangan mengartikannya sebagai class menu.

Saat baris `BudgetConstraint(...)` dijalankan, Python memanggil `__init__`
untuk menyiapkan isi object. `self` dalam method menunjuk object yang sedang
dipakai. Ketika `budget_ani.allows(...)` dipanggil, `self` menunjuk budget Ani,
bukan budget Budi.

## Lihat kode proyek

Buka [`budget.py`](../../recommendation/services/budget.py), lalu cari:

1. `class BudgetConstraint`: nama bentuk datanya.
2. `__init__`: pemeriksaan dan penyiapan batas.
3. `maximum`: cara membaca batas atas.
4. `allows`: memeriksa apakah satu harga diperbolehkan.

Method tidak selalu menulis database. `BudgetConstraint` cukup menyimpan nilai
dan melakukan pemeriksaan. Sebaliknya, class model Django seperti
[`MenuItem`](../../menu/models.py) berhubungan dengan penyimpanan katalog.
Membuat object model Python belum selalu berarti data sudah disimpan.

## Salah paham yang sering terjadi

- `BudgetConstraint` adalah class; `budget_ani` adalah nama variabel yang menunjuk object.
- Satu class dapat dipakai untuk banyak object dengan nilai berbeda.
- Method bukan harus tombol layar; method adalah bagian kode yang dipanggil program.
- Class biasa tidak otomatis menjadi tabel database. Model Django mempunyai aturan tambahan.

## Cek pemahaman

1. Mengapa hasil dua pemeriksaan harga Rp15.000 di atas berbeda?
2. Jika dibuat object ketiga, apakah batas Ani otomatis berubah?
3. Apa perbedaan menyimpan harga menu dan memeriksa apakah harga memenuhi budget?

Lanjut: [enkapsulasi](encapsulation.md).
