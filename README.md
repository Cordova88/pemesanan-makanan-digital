# Pemesanan Makanan Digital

Project website pemesanan makanan digital menggunakan Django.

## Cara Menjalankan Project

Ikuti langkah-langkah di bawah ini dari folder project:

```powershell
cd pemesanan-makanan-digital
```

### 1. Buat virtual environment

```powershell
python -m venv venv
```

### 2. Aktifkan virtual environment

Untuk Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

Jika berhasil, biasanya akan muncul tulisan `(venv)` di awal terminal.

### 3. Install dependency

```powershell
pip install -r requirements.txt
```

### 4. Jalankan migrasi database

Untuk sementara project ini masih memakai database lokal bawaan Django.

```powershell
python manage.py migrate
```

### 5. Jalankan server

```powershell
python manage.py runserver
```

Setelah server berjalan, buka browser dan akses:

```text
http://127.0.0.1:8000/
```

Untuk menghentikan server, tekan:

```text
CTRL + C
```

## Catatan

- Jangan mengedit isi folder `venv`.
- Jika ada dependency baru, jalankan `pip freeze > requirements.txt` agar daftar package tetap terbaru.
- File database lokal seperti `db.sqlite3` tidak perlu dibagikan ke anggota kelompok.
