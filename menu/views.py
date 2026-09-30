from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .models import MenuItem
@require_GET
def customer_menu(request):
    items=MenuItem.objects.filter(is_active=True,is_available=True,category__is_active=True).select_related("category")
    return JsonResponse({"items":[{"id":i.id,"name":i.name,"description":i.description,"price":str(i.price),"category":i.category.name} for i in items]})
