from django.urls import path
from . import cashier_views as v

app_name = 'kasir'
urlpatterns = [
    path('', v.dashboard, name='dashboard'),
    path('<str:public_id>/', v.order_detail, name='order'),
]