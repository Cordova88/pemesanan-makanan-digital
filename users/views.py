from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import CreateView
from django.urls import reverse_lazy
from .models import Pengguna

# OOP Inheritance: Mewarisi logika login bawaan Django
class UserLoginView(LoginView):
    template_name = 'users/login.html'
    redirect_authenticated_user = True

class UserLogoutView(LogoutView):
    next_page = 'login'

# OOP Inheritance: Menggunakan CreateView untuk form registrasi otomatis
class UserRegisterView(CreateView):
    model = Pengguna
    template_name = 'users/register.html'
    fields = ['username', 'password', 'nomor_telepon'] # Kolom yang akan muncul di form
    success_url = reverse_lazy('login')