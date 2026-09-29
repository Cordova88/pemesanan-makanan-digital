from django.db import models
from users.models import Pengguna
from menu.models import Produk

class Pesanan(models.Model):
    pelanggan = models.ForeignKey(Pengguna, on_delete=models.CASCADE)
    tanggal_pesan = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='Menunggu') # Menunggu, Diproses, Selesai

    # OOP Encapsulation: Objek menghitung totalnya sendiri dengan memanggil method subtotal dari ItemPesanan
    def hitung_total_tagihan(self):
        total = sum(item.hitung_subtotal() for item in self.item_pesanan.all())
        return total

    def __str__(self):
        return f"Pesanan #{self.id} - {self.pelanggan.username}"

class ItemPesanan(models.Model):
    pesanan = models.ForeignKey(Pesanan, on_delete=models.CASCADE, related_name="item_pesanan")
    produk = models.ForeignKey(Produk, on_delete=models.CASCADE)
    jumlah = models.IntegerField(default=1)

    # Method internal untuk menghitung harga item dikali jumlah belinya
    def hitung_subtotal(self):
        return self.produk.price * self.jumlah