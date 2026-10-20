# Acuan pengembangan V1

Folder ini adalah baseline pengembangan aktif. Folder pemesanan-makanan-digital-figma
adalah arsip; jangan mengeditnya untuk pekerjaan v1. Ikuti juga panduan PBO
di ../AGENTS/AGENTS.txt selama tersedia.

- Kerjakan perubahan bertahap dengan batas yang jelas; pertahankan perubahan lokal.
- Jangan membaca/menampilkan nilai .env atau secret. Jangan menyalin akun percobaan lama.
- Jangan commit/push/merge tanpa izin pengguna.
- Uji perubahan data pada database/media terpisah; jangan menimpa katalog pengguna.
- manage.py default memakai v1_settings.py untuk lokal. Baca README.md dan docs/V1_BASELINE.md.
- Jangan menjalankan seed_demo untuk bootstrap v1; gunakan fixture v1_catalog hanya pada database baru.
- Akun admin dibuat pengguna secara interaktif melalui createsuperuser.
