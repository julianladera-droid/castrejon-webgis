'use strict';
// Run the real app handlers with an offline DOM/GPS/API double; no external services.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const A=require('../averias/shared.js'),L=require('../averias/location.js');
class Element{
  constructor(){this.value='';this.hidden=false;this.children=[];this.handlers={};this.disabled=false;this.classList={toggle(){}};}
  addEventListener(name,fn){(this.handlers[name]||=[]).push(fn);}
  append(...items){this.children.push(...items);} prepend(...items){this.children.unshift(...items);}
  replaceChildren(...items){this.children=items;} removeAttribute(){} scrollIntoView(){}
  querySelectorAll(){return [];} reset(){} set textContent(s){this.text=s;this.children=[];} get textContent(){return this.text||'';}
}
async function harness(initial=[]){
  const ids=[...fs.readFileSync('averias/index.html','utf8').matchAll(/id="([^"]+)"/g)].map(m=>m[1]);
  const elements=Object.fromEntries(ids.map(id=>[id,new Element()]));
  Object.assign(elements.kind,{value:'fuga'});elements.priority.value='normal';elements.description.value='Junta rota';
  const records=new Map(initial.map(x=>[x.id,structuredClone(x)])),requests=[],prompts=[];
  let answer=true,failWrite=false,gps={latitude:39.834749,longitude:-4.371848,accuracy:5},mapClick;
  const storage={all:async()=>structuredClone([...records.values()]),get:async id=>structuredClone(records.get(id)),put:async d=>records.set(d.id,structuredClone(d)),remove:async id=>records.delete(id)};
  const shared={...A,drafts:()=>storage,photoFromFile:async()=>new Blob(['jpeg']),base64:async()=> 'photo-bytes',list:async()=>[],publicFeature:x=>x,
    request:async(url,opts)=>{requests.push({url:String(url),...opts});if(String(url).endsWith('/session/'))return {authorized:true,nonce:'test'};
      if(String(url).endsWith('/location-check'))return L.locationQuality(JSON.parse(opts.body));
      if(failWrite)throw new Error('Respuesta perdida');return {};}};
  const noop=class{constructor(){} clear(){} addFeature(){}};
  const context={window:{CastrejonAverias:shared,CastrejonLocation:L,addEventListener(){},ol:true},document:{getElementById:id=>elements[id],querySelector:s=>({content:s.includes('api-base')?'https://example.org/api/':'https://example.org/averias-campo/'}),createElement:()=>new Element()},
    navigator:{onLine:true,geolocation:{getCurrentPosition:resolve=>resolve({coords:gps})}},crypto,URL,Date,Blob,
    confirm:text=>{prompts.push(text);return answer;},ol:{source:{Vector:noop,XYZ:noop},Map:class{on(name,handler){mapClick=handler;}getView(){return {animate(){}};}},layer:{Tile:noop,Vector:noop},style:{Style:noop,Circle:noop,Fill:noop,Stroke:noop},View:noop,control:{Zoom:noop,Attribution:noop},proj:{fromLonLat:x=>x,toLonLat:x=>x},Feature:noop,geom:{Point:noop}}};
  await vm.runInNewContext(fs.readFileSync('averias/app.js','utf8'),context);
  async function settle(){for(let i=0;i<8;i++)await new Promise(setImmediate);}
  async function fire(id,event='click'){for(const handler of elements[id].handlers[event]||[])handler({preventDefault(){}});await settle();}
  async function clickDraft(text){const article=elements.draftList.children[0];const action=article.children.at(-1).children.find(x=>x.textContent===text);assert(action,`draft action ${text}`);for(const fn of action.handlers.click)fn();await settle();}
  return {elements,records,requests,prompts,fire,clickDraft,setAnswer:v=>answer=v,setFail:v=>failWrite=v,setGPS:v=>gps=v,mapClick:async c=>{mapClick({coordinate:c});await settle();}};
}
(async()=>{
  const h=await harness(),e=h.elements;
  e.photo.files=[{}];await h.fire('photo','change');await h.fire('locate');
  e.latitude.value='40,4168';e.longitude.value='-3,7038';await h.fire('latitude','input');
  await h.fire('incidentForm','submit');
  let draft=[...h.records.values()][0];assert(draft);assert.equal(draft.payload.latitude,40.4168);assert.equal(draft.payload.longitude,-3.7038);assert.equal(draft.payload.location_source,'manual');assert.equal(draft.payload.accuracy_m,null);
  assert.equal(e.locationQuality.className,'location-quality danger');
  h.setAnswer(false);await h.clickDraft('Publicar');assert.equal(h.records.get(draft.id).attempted,false);assert.equal(h.requests.filter(r=>r.url.endsWith('/incidents')).length,0);assert.match(h.prompts.at(-1),/muy alejado/);assert.match(h.prompts.at(-1),/40.4168/);
  h.setAnswer(true);h.setFail(true);await h.clickDraft('Publicar');assert.equal(h.records.get(draft.id).attempted,true);
  const first=h.requests.filter(r=>r.url.endsWith('/incidents'))[0].body;
  h.setFail(false);await h.clickDraft('Reintentar envío');assert.equal(h.records.get(draft.id).published,true);
  assert.equal(h.requests.filter(r=>r.url.endsWith('/incidents'))[1].body,first,'retry must preserve UUID/photo and every payload byte');
  assert.equal(h.requests.filter(r=>r.url.endsWith('/location-check')).length,2,'no preflight mutation of attempted retry');
  const g=await harness();g.setGPS({longitude:-4.371848,latitude:39.834749,accuracy:120});await g.fire('locate');assert.equal(g.elements.locationQuality.className,'location-quality warning');
  g.setGPS({longitude:-4.371848,latitude:39.834749,accuracy:5});await g.fire('locate');assert.equal(g.elements.locationQuality.className,'location-quality ok');
  await g.mapClick([-4.5,39.84]);assert.match(g.elements.locationStatus.textContent,/manualmente/);assert.equal(g.elements.locationQuality.className,'location-quality warning');
  g.elements.photo.files=[{}];await g.fire('photo','change');g.elements.latitude.value='NaN';await g.fire('latitude','input');await g.fire('incidentForm','submit');assert.equal(g.records.size,0);assert.match(g.elements.message.textContent,/decimales/);
  const old={...draft,attempted:false,published:false};const legacy=await harness([old]);await legacy.clickDraft('Publicar');assert.match(legacy.prompts[0],/muy alejado/);assert(legacy.records.get(old.id).published);
  const invalid={...old,payload:{...old.payload,location_source:'gps',accuracy_m:100001}};
  const repair=await harness([invalid]);await repair.clickDraft('Abrir');assert.equal(repair.elements.locationQuality.className,'location-quality danger');
  await repair.fire('locate');await repair.fire('incidentForm','submit');assert.equal(repair.records.get(old.id).payload.accuracy_m,5,'legacy draft with invalid accuracy can be reopened and repaired');
  console.log('PASS: real form handlers, pending manual edits, GPS correction, map input, old draft review, cancel before write and byte-identical retries');
})().catch(error=>{console.error(error);process.exitCode=1;});
