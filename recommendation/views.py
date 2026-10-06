import json
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from cart.services import CartService
from menu.models import MenuItem
from .services.chatbot import ChatbotService

def _body(request): return json.loads(request.body or '{}')
def _item(item): return {'id':item.id,'name':item.name,'description':item.description,'price':format(item.price,'.2f'),'tags':[t.name for t in item.tags.all()], 'variants':[{'id':g.id,'name':g.name,'required':g.is_required,'options':[{'id':o.id,'name':o.name,'price_adjustment':format(o.price_adjustment,'.2f')} for o in g.options.filter(is_active=True)]} for g in item.variant_groups.filter(is_active=True)], 'addons':[{'id':a.id,'name':a.name,'price':format(a.price,'.2f')} for a in item.allowed_addons.filter(is_active=True,is_available=True)]}

@require_POST
def chat(request):
    try:
        body=_body(request); result=ChatbotService(request.session).reply(body.get('message',''), body.get('action')=='more')
        result['recommendations']=[_item(item) for item in result['recommendations']]
        return JsonResponse(result)
    except (ValueError, json.JSONDecodeError): return JsonResponse({'error':'Pesan tidak valid.'}, status=400)

@require_POST
def add_to_cart(request):
    try:
        body=_body(request); item=MenuItem.objects.get(pk=body.get('menu_item_id'))
        CartService(request.session).add_item(item.id, int(body.get('quantity',1)), body.get('variant_ids',[]), body.get('addon_ids',[]))
        return JsonResponse({'message':'✅ Sudah masuk ke keranjang!'})
    except (MenuItem.DoesNotExist, ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc: return JsonResponse({'error':str(exc)}, status=400)

@require_GET
def chatbot_page(request): return render(request, 'recommendation/chatbot.html')
