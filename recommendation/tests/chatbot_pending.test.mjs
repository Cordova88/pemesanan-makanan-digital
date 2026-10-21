/** Execute the production inline script against a delayed transport fixture. */
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { test } from 'node:test';

class Element {
  constructor() { this.children=[]; this.attributes={}; this.listeners={}; this.value=''; this.disabled=false; }
  append(...children) { for(const child of children) { child.parent=this; this.children.push(child); } }
  replaceChildren(...children) { this.children=[]; this.append(...children); }
  remove() { if(this.parent) this.parent.children=this.parent.children.filter(child=>child!==this); }
  setAttribute(name,value) { this.attributes[name]=value; }
  addEventListener(name,callback) { this.listeners[name]=callback; }
  get childElementCount() { return this.children.length; }
}
function fixture() {
  const elements=Object.fromEntries(['#messages','#input','#form','#send','#reset','[name=csrfmiddlewaretoken]'].map(key=>[key,new Element()]));
  elements['[name=csrfmiddlewaretoken]'].value='synthetic-csrf';
  const calls=[];
  const context=vm.createContext({document:{querySelector:selector=>elements[selector],createElement:()=>new Element()},
    createFoodVisual:()=>new Element(),window:{location:{}},fetch:(url,options)=>new Promise((resolve,reject)=>calls.push({url,options,resolve,reject}))});
  const template=readFileSync(new URL('../templates/recommendation/chatbot.html',import.meta.url),'utf8');
  let source=template.match(/<script type="module">([\s\S]*?)<\/script>/)[1];
  source=source.replace(/^import .*;$/m,'').replace('sendMessage("","");','');
  vm.runInContext(source+'\nglobalThis.transport={sendMessage,resetChat,getRevision:()=>revision};',context);
  return {elements,calls,api:context.transport,context};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const response=(revision,extra={})=>({ok:true,status:200,json:async()=>({revision,message:'Pilihan tersedia.',preferences:{tags:[]},quick_replies:[],recommendations:[],...extra})});

test('slow request blocks duplicate form/quick/reset sends with one accessible loader',async()=>{
  const f=fixture();f.elements['#input'].value='minuman';
  const first=f.api.sendMessage('minuman');
  f.api.sendMessage('minuman');f.api.sendMessage('yang lain');f.api.resetChat();
  await tick();
  assert.equal(f.calls.length,1);
  assert.equal(f.elements['#send'].disabled,true);
  assert.equal(f.elements['#reset'].disabled,true);
  assert.equal(f.elements['#form'].attributes['aria-busy'],'true');
  assert.equal(f.elements['#messages'].children.filter(child=>child.attributes.role==='status').length,1);
  f.calls[0].resolve(response(1));await first;
  assert.equal(f.elements['#send'].disabled,false);
  assert.equal(f.elements['#form'].attributes['aria-busy'],'false');
  assert.equal(f.elements['#messages'].children.filter(child=>child.attributes.role==='status').length,0);
});
test('text typed while waiting survives and sends only after completion with current revision and CSRF',async()=>{
  const f=fixture();const first=f.api.sendMessage('minuman');await tick();
  f.elements['#input'].value='ayam geprek';f.api.sendMessage('ayam geprek');
  assert.equal(f.elements['#input'].value,'ayam geprek');assert.equal(f.calls.length,1);
  f.calls[0].resolve(response(4));await first;
  const next=f.api.sendMessage(f.elements['#input'].value);await tick();
  assert.equal(f.calls.length,2);
  const body=JSON.parse(f.calls[1].options.body);
  assert.equal(body.message,'ayam geprek');assert.equal(body.revision,4);
  assert.equal(f.calls[1].options.headers['X-CSRFToken'],'synthetic-csrf');
  f.calls[1].resolve(response(5));await next;
});
test('network error releases busy controls, does not auto retry, and manual retry sends once',async()=>{
  const f=fixture();const pending=f.api.sendMessage('minuman');await tick();
  f.calls[0].reject(new Error('synthetic failure'));await pending;
  assert.equal(f.elements['#send'].disabled,false);assert.equal(f.calls.length,1);
  const failure=f.elements['#messages'].children.find(child=>child.textContent==='Gagal terhubung.');
  assert.ok(failure);failure.children[0].onclick();failure.children[0].onclick();await tick();
  assert.equal(f.calls.length,2);f.calls[1].resolve(response(1));await tick();
  assert.equal(f.elements['#send'].disabled,false);
});
test('409 keeps the server revision and visible conflict without rendering stale success',async()=>{
  const f=fixture();const pending=f.api.sendMessage('minuman');await tick();
  f.calls[0].resolve({ok:false,status:409,json:async()=>({revision:9,error:'Percakapan sudah berubah.'})});await pending;
  assert.equal(f.api.getRevision(),9);
  assert.ok(f.elements['#messages'].children.some(child=>child.textContent==='Percakapan sudah berubah.'));
  assert.equal(f.elements['#send'].disabled,false);
});
test('non-increasing success revision is rejected and pending state clears',async()=>{
  const f=fixture();let pending=f.api.sendMessage('minuman');await tick();f.calls[0].resolve(response(2));await pending;
  pending=f.api.sendMessage('makanan');await tick();f.calls[1].resolve(response(2,{message:'Stale result canary'}));await pending;
  assert.ok(!f.elements['#messages'].children.some(child=>child.textContent==='Stale result canary'));
  assert.equal(f.elements['#form'].attributes['aria-busy'],'false');
});

test('populated preferences render no obsolete chip container or removal handler',async()=>{
  const f=fixture();const pending=f.api.sendMessage('minuman');await tick();
  f.calls[0].resolve(response(1,{preferences:{tags:['Minuman','Manis'],mood_tags:['Segar']}}));await pending;
  assert.ok(!f.elements['#preferences']);
  assert.equal(f.elements['#messages'].children.length,2);
  assert.ok(f.elements['#messages'].children.every(child=>child.className!=='preference-chip'));
  const template=readFileSync(new URL('../templates/recommendation/chatbot.html',import.meta.url),'utf8');
  for(const obsolete of ['renderPreferences','id="preferences"','preference-chip','Hapus preferensi'])assert.ok(!template.includes(obsolete));
});
test('quick reply sends its value and bound revision, reset clears transcript without old container',async()=>{
  const f=fixture();let pending=f.api.sendMessage('halo');await tick();
  f.calls[0].resolve(response(1,{quick_replies:[{label:'Minuman',value:'minuman'}]}));await pending;
  const quick=f.elements['#messages'].children.find(child=>child.className==='chat-quick-replies');
  quick.children[0].onclick();await tick();
  assert.equal(JSON.parse(f.calls[1].options.body).message,'minuman');
  assert.equal(JSON.parse(f.calls[1].options.body).revision,1);
  f.calls[1].resolve(response(2));await tick();
  pending=f.api.resetChat();await tick();assert.equal(JSON.parse(f.calls[2].options.body).action,'reset');
  f.calls[2].resolve(response(3,{message:'Percakapan baru.'}));await pending;
  assert.equal(f.elements['#messages'].children.length,1);
  assert.equal(f.elements['#messages'].children[0].textContent,'Percakapan baru.');
});
test('cards and menu navigation remain available after chip removal',async()=>{
  const f=fixture();const pending=f.api.sendMessage('minuman');await tick();
  f.calls[0].resolve(response(1,{recommendations:[{id:12,name:'Es Jeruk',price:'10000.00',labels:['Minuman']}]}));await pending;
  const card=f.elements['#messages'].children.find(child=>child.className==='chat-recommendation');
  assert.ok(card);assert.ok(card.children.some(child=>child.textContent==='Es Jeruk'));
  card.children.find(child=>child.textContent==='Lihat pilihan menu').onclick();
  assert.equal(f.context.window.location.href,'/?menu=12#menu');
});
test('form submits conversational preference edits with accessible controls intact',async()=>{
  const f=fixture();f.elements['#input'].value='gak jadi pedas';let prevented=false;
  f.elements['#form'].listeners.submit({preventDefault(){prevented=true;}});await tick();
  assert.ok(prevented);assert.equal(JSON.parse(f.calls[0].options.body).message,'gak jadi pedas');
  f.calls[0].resolve(response(1));await tick();assert.equal(f.elements['#send'].disabled,false);
});
