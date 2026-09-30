from django.urls import path
from .views import customer_menu
urlpatterns=[path("",customer_menu,name="customer-menu")]
