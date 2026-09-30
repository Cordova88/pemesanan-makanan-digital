from django.urls import path

from . import views

urlpatterns = [
    path("", views.detail, name="cart-detail"),
    path("add/", views.add, name="cart-add"),
    path("<str:line_id>/", views.line, name="cart-line"),
    path("clear/", views.clear, name="cart-clear"),
]
