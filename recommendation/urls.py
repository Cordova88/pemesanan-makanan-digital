from django.urls import path
from . import views
urlpatterns = [path('chat/', views.chat, name='recommendation-chat'), path('add/', views.add_to_cart, name='recommendation-add')]
