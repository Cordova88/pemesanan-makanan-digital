from .tag_extractor import Preferences, TagExtractor
from .recommendation import RecommendationService

class ChatbotService:
    KEY = 'recommendation_state'
    def __init__(self, session): self.session=session; self.extractor=TagExtractor(); self.recommender=RecommendationService()
    def reset(self):
        self.session.pop(self.KEY, None)
        self.session.pop('recommendation_shown', None)
        self.session.modified=True
    def _prefs(self):
        data=self.session.get(self.KEY, {}); return Preferences(set(data.get('tags', [])), data.get('max_price'), data.get('category'))
    def reply(self, message, more=False):
        text=(message or '').strip().lower()
        if text in ('reset', 'mulai lagi'): self.reset(); return self._question()
        prefs=self._prefs(); extracted=self.extractor.extract(text); prefs.tags |= extracted.tags; prefs.max_price = extracted.max_price or prefs.max_price
        if text == 'heavy': prefs.tags.add('filling')
        if text == 'snack': prefs.tags.add('snack')
        if text == 'drink': prefs.tags.add('drink')
        if text == 'rice': prefs.tags.add('rice')
        if text == 'noodle': prefs.tags.add('noodle')
        if text == 'spicy': prefs.tags.add('spicy')
        if text == 'budget': prefs.max_price=15000
        self.session[self.KEY]={'tags':sorted(prefs.tags),'max_price':prefs.max_price}; self.session.modified=True
        if not prefs.tags or text in ('gak tahu','tidak tahu','bingung','terserah'): return self._question()
        shown=self.session.get('recommendation_shown', []) if more else []
        results=self.recommender.recommend(prefs, exclude_ids=shown)
        self.session['recommendation_shown']=shown+[item.id for item in results]; self.session.modified=True
        return {'message':'Ini beberapa menu yang cocok buat kamu.' if results else 'Maaf, aku belum menemukan menu yang cocok.', 'state':'RECOMMENDING', 'preferences':{'tags':sorted(prefs.tags),'max_price':prefs.max_price}, 'recommendations':results, 'quick_replies':[]}
    def _question(self):
        return {'message':'Tenang, aku bantu pilih 😊 Kamu lagi ingin apa?', 'state':'COLLECTING_PREFERENCES', 'preferences':{'tags':[],'max_price':None}, 'recommendations':[], 'quick_replies':[{'label':'🍚 Makanan berat','value':'heavy'},{'label':'🍟 Snack','value':'snack'},{'label':'🥤 Minuman','value':'drink'},{'label':'🌶️ Pedas','value':'spicy'},{'label':'🍜 Mie','value':'noodle'},{'label':'🍚 Nasi','value':'rice'},{'label':'💸 Hemat','value':'budget'}]}
