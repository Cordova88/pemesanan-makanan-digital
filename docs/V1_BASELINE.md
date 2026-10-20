# Acuan V1

Folder repository `pemesanan-makanan-digital` pada branch `ahmad` memakai
baseline v1. Jalankan perintah
dari folder ini, bukan folder arsip.

- `manage.py` memakai `v1_settings` secara default: server lokal tanpa Gemini.
- Profil opsional `local_gemini_settings` membaca konfigurasi lokal; jangan
  membagikan `.env`, API key, atau `.local-secret-key`.
- Database lokal: `db.sqlite3`; foto katalog: `media/`; arsip upload:
  `private/menu-originals/`. Cadangkan database dan media bersama.
- `menu/fixtures/v1_catalog.json` hanya untuk database baru. Jangan mengulang
  `loaddata` atau menjalankan `seed_demo` pada katalog yang sudah diedit.
- Tests, migrations, perintah pengelolaan, dan aset pemulihan foto merupakan
  bagian source yang dipertahankan.

```powershell
python -B manage.py check
python -B manage.py runserver 127.0.0.1:8890 --noreload
```

Panduan lengkap: [README](../README.md), [pengujian lokal](PANDUAN_TESTING_LOKAL.md),
[CMS/Admin](PANDUAN_CMS_ADMIN.md), dan [hosting](PANDUAN_VERIFIKASI_HOSTING.md).

Catatan penyiapan awal, audit, fase implementasi, diagram, dan hasil pengujian
historis disimpan terpisah di `UTS/output/pengembangan/` pada workspace penulis;
folder itu tidak diperlukan saat clone repository.
Dokumen historis tidak menyatakan kondisi data atau kesiapan production saat ini.
