from django.views.generic import ListView, DetailView
from .models import Produk

class DaftarMenuView(ListView):
    model = Produk
    template_name = 'menu/daftar_menu.html'
    context_object_name = 'semua_produk'

    # Polimorfisme: Override fungsi bawaan untuk menyaring menu yang "is_available=True" saja
    def get_queryset(self):
        return Produk.objects.filter(is_available=True)

class DetailMenuView(DetailView):
    model = Produk
    template_name = 'menu/detail_menu.html'
    context_object_name = 'produk'