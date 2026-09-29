from django.contrib.auth.models import AbstractUser
from django.db import models

# Create your models here.
# OOP Inheritance: Kelas Pengguna mewarisi seluruh fitur User bawaan Django (login, password hashing)
class Pengguna(AbstractUser):
    nomor_telepon = models.CharField(max_length=15, blank=True)
    is_kasir = models.BooleanField(default=False)

    # Method untuk representasi objek saat di-print
    def __str__(self):
        peran = "Kasir" if self.is_kasir else "Pelanggan"
        return f"{self.username} ({peran})"