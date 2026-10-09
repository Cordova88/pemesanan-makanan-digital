from django.urls import path
from . import views

app_name = 'staff'
urlpatterns = [
    path('login/', views.staff_login, name='login'), path('logout/', views.staff_logout, name='logout'), path('', views.dashboard, name='dashboard'),
    path('tables/', views.tables, name='tables'), path('tables/<int:pk>/edit/', views.table_edit, name='table-edit'), path('tables/<int:pk>/qr/', views.table_qr, name='table-qr'), path('tables/<int:pk>/qr/download/', views.table_qr_download, name='table-qr-download'),
    path('categories/', views.categories, name='categories'), path('categories/<int:pk>/edit/', views.category_edit, name='category-edit'),
    path('tags/', views.tags, name='tags'), path('tags/<int:pk>/edit/', views.tag_edit, name='tag-edit'),
    path('tags/<int:pk>/delete/', views.tag_delete, name='tag-delete'),
    path('menu-items/', views.menu_items, name='menu-items'), path('menu-items/<int:pk>/edit/', views.menu_item_edit, name='menu-item-edit'),
    path('variants/', views.variants, name='variants'), path('variants/groups/<int:pk>/edit/', views.variant_group_edit, name='variant-group-edit'), path('variants/options/<int:pk>/edit/', views.variant_option_edit, name='variant-option-edit'),
    path('addons/', views.addons, name='addons'), path('addons/<int:pk>/edit/', views.addon_edit, name='addon-edit'),
    path('orders/', views.orders, name='orders'), path('audit-log/', views.audit_log, name='audit-log'),
]
