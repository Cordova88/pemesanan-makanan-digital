# Latihan membaca OOP dari proyek

[Kembali ke indeks](README.md).

Latihan ini memakai class yang sudah ada. Mulai dengan membaca file. Untuk
operasi database gunakan instalasi latihan terpisah; jangan mengubah data tim
atau memanggil Gemini hanya untuk mencoba inheritance.

## 1. Class dan object

Buka MenuItem dan AddOn pada menu/models.py. Sebutkan dua atribut, satu method,
dan contoh dua object yang berbeda. Jelaskan perbedaan membuat object model
dengan menyimpannya ke database.

## 2. Atribut dan method

Buka CartService. Kelompokkan SESSION_KEY, session, _lines, clear, dan _ids.
Mengapa clear membutuhkan self, sedangkan _ids merupakan static method?

## 3. Enkapsulasi

Buka BudgetConstraint. Telusuri penolakan minimum lebih besar dari maksimum.
Kemudian buka MenuSelection.options. Mengapa tuple tidak membuat seluruh model
Django di dalamnya menjadi immutable?

## 4. Relasi UML

Gambar Category–MenuItem dan Order–OrderItem berdasarkan field model.
Tambahkan multiplisitas serta catatan PROTECT. Jelaskan mengapa itu tidak sama
dengan janji penghapusan otomatis seluruh bagian.

## 5. Inheritance

Baca MenuPhotoForm.__init__ dan MenuPhotoWidget.get_context. Tandai pekerjaan
induk melalui super dan pekerjaan tambahan anak. Buat prediksi apa yang bermasalah
jika inisialisasi induk tidak dijalankan.

## 6. Polimorfisme dan abstraksi

Bandingkan generate pada TextGenerator, GeminiClient, dan TurnGenerator.
Lalu bandingkan __str__ pada MenuItem dan VariantGroup. Jelaskan pemanggilan sama,
implementasi berbeda. Mengapa kontrak generate belum cukup untuk converse?

## 7. SOLID

Pilih satu prinsip dari solid.md. Tunjukkan bukti penerapan, batasnya, dan contoh
perubahan yang mungkin memengaruhi desain itu. Hindari kesimpulan bahwa banyak
class otomatis berarti seluruh SOLID sudah dipenuhi.

## Contoh latihan tanpa database atau API

Jalankan dari folder proyek melalui Python proyek. Potongan ini memakai class
nyata, bukan mendefinisikan class latihan baru.

```python
from decimal import Decimal
from recommendation.services.budget import BudgetConstraint

murah = BudgetConstraint(maximum=Decimal("10000"))
lebih_longgar = BudgetConstraint(maximum=Decimal("20000"))

print(murah.allows(Decimal("15000")))          # False
print(lebih_longgar.allows(Decimal("15000")))  # True
print(murah == BudgetConstraint(maximum=Decimal("10000")))  # True
```

Angka pada contoh adalah data latihan. Baca alur method sebelum menjalankannya,
lalu jelaskan hasil dengan istilah object, keadaan, method, dan kesamaan nilai.

## Pola presentasi satu kasus

1. Jelaskan masalah pelanggan atau anggota tim.
2. Tunjukkan file dan class/method yang terkait.
3. Telusuri input, data internal, pemrosesan, dan hasil.
4. Hubungkan dengan satu konsep OOP utama.
5. Sebutkan batas penerapannya supaya penjelasan tidak berlebihan.
