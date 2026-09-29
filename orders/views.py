from django.views.generic import ListView, View
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Pesanan, ItemPesanan
from menu.models import Produk

class KeranjangBelanjaView(LoginRequiredMixin, ListView):
    model = ItemPesanan
    template_name = 'orders/keranjang.html'
    context_object_name = 'item_keranjang'

    def get_queryset(self):
        # Mencari keranjang (pesanan) aktif milik user yang sedang login
        pesanan, created = Pesanan.objects.get_or_create(pelanggan=self.request.user, status='Menunggu')
        return pesanan.item_pesanan.all()

    def get_context_data(self, **kwargs):
        # Polimorfisme: Menambahkan data total harga ke dalam template HTML
        context = super().get_context_data(**kwargs)
        pesanan = Pesanan.objects.get(pelanggan=self.request.user, status='Menunggu')
        # Memanggil method OOP 'hitung_total_tagihan' dari models.py
        context['total_tagihan'] = pesanan.hitung_total_tagihan() 
        return context

# OOP Override: Menggunakan kelas dasar View untuk menangani aksi klik tombol (POST request)
class TambahKeKeranjangView(LoginRequiredMixin, View):
    def post(self, request, produk_id):
        produk = get_object_or_404(Produk, id=produk_id)
        pesanan, created = Pesanan.objects.get_or_create(pelanggan=request.user, status='Menunggu')
        
        # Cek apakah makanan sudah ada di keranjang, jika ada tambah jumlahnya
        item, item_created = ItemPesanan.objects.get_or_create(pesanan=pesanan, produk=produk)
        if not item_created:
            item.jumlah += 1
            item.save()
            
        return redirect('orders:keranjang') # Arahkan kembali ke halaman keranjang