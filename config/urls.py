"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from menu.views import storefront
from orders.views import confirmation

urlpatterns = [
    path('', storefront, name='storefront'),
    path('orders/<str:public_id>/', confirmation, name='order-confirmation'),
    path('admin/', admin.site.urls),
    path('staff/', include('users.urls')),
    path('api/menu/', include('menu.urls')),
    path('api/cart/', include('cart.urls')),
    path('api/orders/', include('orders.urls')),
    path('api/recommendation/', include('recommendation.urls')),
    path('chatbot/', include('recommendation.urls_page')),
    path('kasir/', include('users.cashier_urls')),
]

# Uploaded files are served here only for local development (DEBUG=True).
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
