'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const code=fs.readFileSync('index.html','utf8').split('// BEGIN WATER UI')[1].split('// END WATER UI')[0];
const hash=b=>crypto.createHash('sha256').update(b).digest('hex'),h='a'.repeat(64);
const flush=async()=>{for(let i=0;i<60;i++)await Promise.resolve();};
function setup({corrupt=false,delay=false,mutate=()=>{}}={}) {
 const elements={},requests=[],payloads={};let sourceReads=0;
 const el=id=>elements[id]??={value:'',checked:false,hidden:false,textContent:'',events:{},addEventListener(n,f){this.events[n]=f;}};
 const a={id:'A',datetime:'2023-08-16T11:00:00Z',water_raster_sha256:h,parcel_indices:{parcel_web_sha256:h}};
 const b={...a,id:'B',datetime:'2026-10-31T11:00:00Z'};
 for(const entry of [a,b]) {
  const previous=entry===b;
  const data={version:3,method:'optical_field_visit_v3',status:'field_visit_estimate',resolution_m:10,support_resolution_m:20,min_valid_percent:80,
   area_method:'fractional_cell_intersection_25830',observation:{id:entry.id,datetime:entry.datetime},
   previous:previous?{id:a.id,datetime:a.datetime}:null,source_sha256:h,previous_sha256:previous?h:null,
   parcel_web_sha256:h,master_sha256:h,
   columns:['water_m2','ambiguous_m2','unknown_m2','evaluated_m2','parcel_m2','appeared_m2','both_observations_m2','disappeared_m2','common_evaluated_m2','residual_m2'],
   parcels:Object.fromEntries(Array.from({length:919},(_,i)=>['r'+i,[0,0,0,1000,1000,0,0,0,1000,0]]))};
  data.parcels.r0=[300,100,100,800,1000,100,200,0,800,0];data.parcels.r2=[100,100,400,500,1000,100,0,0,500,0];data.parcels.r3=[0,0,1000,0,1000,0,0,0,0,0];
  data.parcels.r4=[0,0,0,800,1000,0,0,0,800,200];
  if(!previous) for(const row of Object.values(data.parcels))row.splice(5,4,null,null,null,null);
  mutate(data);
  const zones={type:'FeatureCollection',features:[{type:'Feature',properties:{refcat:'r0',class:1},geometry:{type:'Polygon',coordinates:[]}},{type:'Feature',properties:{refcat:'r4',class:4},geometry:{type:'Polygon',coordinates:[]}}]};
  entry.water={method:data.method,parcel_web_sha256:h};
  for(const [key,name,payload] of [['table','parcel-water.json',data],['zones','water-zones.geojson',zones]]) {
   const bytes=Buffer.from(JSON.stringify(payload)),path=`sentinel/${entry.id}/${name}`;
   payloads[path]=bytes;entry.water[key]={path,sha256:hash(bytes)};
  }
 }
 const layer={visible:false,setVisible(v){this.visible=v;},setSource(s){this.source=s;}};
 const context={Map,Intl,TextDecoder,Uint8Array,crypto:{subtle:{digest:async(_,bytes)=>crypto.createHash('sha256').update(bytes).digest()}},
  document:{getElementById:el},waterLayer:layer,selectedParcel:null,parcelWebHash:h,areaFormat:new Intl.NumberFormat('es-ES',{maximumFractionDigits:2}),
  acquisitions:[b,a],dateSelect:{value:'B'},formatDate:d=>d.slice(0,10),productPath:(p,id,n,e)=>{assert.equal(p,`sentinel/${id}/${n}.${e}`);return p;},
  ol:{source:{Vector:class{constructor(o){this.options=o;}}},format:{GeoJSON:class{readFeatures(d,o){assert.equal(o.featureProjection,'EPSG:3857');sourceReads++;return d.features;}}}},
  fetch:path=>new Promise(resolve=>{requests.push({path,resolve});if(!delay)resolve({ok:true,arrayBuffer:async()=>corrupt?Buffer.from('{}'):payloads[path]});})};
 el('waterToggle').checked=true;el('compareDateA').value='A';
 vm.createContext(context);vm.runInContext(code,context);context.acceptWater({version:2,acquisitions:[b,a]});
 return {context,layer,e:elements,requests,sourceReads:()=>sourceReads,
  select(ref){context.selectedParcel={get:key=>key==='refcat'?ref:1000};return context.refreshParcelWater();},
  respond(){for(const r of requests)r.resolve({ok:true,arrayBuffer:async()=>payloads[r.path]});}};
}
(async()=>{
 const s=setup();s.context.syncWater();await flush();assert(s.layer.visible);assert.equal(s.requests.length,2);assert.equal(s.sourceReads(),1);
 await s.select('r0');assert.match(s.e.parcelWaterValue.textContent,/30%/);assert.match(s.e.parcelWaterNote.textContent,/ambas 20%/);
 assert.match(s.e.parcelWaterDates.textContent,/2026-10-31.*aproximación para campo/);assert.match(s.e.parcelWaterNote.textContent,/Ambigua: 10%.*No evaluable: 10%/);
 await s.select('r4');assert.match(s.e.parcelWaterNote.textContent,/residual: 200 m²/);assert.match(s.e.parcelWaterValue.textContent,/revisar 200 m²/);
 await s.select('r1');assert.match(s.e.parcelWaterValue.textContent,/^0%/);
 await s.select('r2');assert.equal(s.e.parcelWaterValue.textContent,'No concluyente');assert.match(s.e.parcelWaterNote.textContent,/Cobertura clasificable: 50%/);
 await s.select('r3');assert.equal(s.e.parcelWaterValue.textContent,'No concluyente');assert.match(s.e.parcelWaterNote.textContent,/No evaluable: 100%/);
 s.e.waterToggle.checked=false;s.context.syncWater();await flush();assert(!s.layer.visible);assert.equal(s.e.parcelWaterValue.textContent,'No concluyente');
 s.e.waterToggle.checked=true;s.context.syncWater();await flush();assert(s.layer.visible);assert.equal(s.requests.length,2);
 s.context.dateSelect.value='A';s.context.syncWater();await flush();await s.select('r0');assert(s.layer.visible);assert.match(s.e.parcelWaterValue.textContent,/30%/);
 assert.match(s.e.parcelWaterDates.textContent,/2023-08-16/);assert.match(s.e.parcelWaterNote.textContent,/Sin comparación anterior/);
 s.e.compareToggle.checked=true;s.e.compareDateA.value='unavailable';s.context.syncWater();await flush();assert(s.layer.visible);
 s.context.dateSelect.value='C';s.context.syncWater();await flush();assert(!s.layer.visible);assert.equal(s.e.parcelWaterValue.textContent,'—');assert(s.e.waterToggle.disabled);
 const late=setup({delay:true});late.context.syncWater();late.select('r0');late.select('r1');late.respond();await flush();assert.match(late.e.parcelWaterValue.textContent,/^0%/);
 const date=setup({delay:true});date.context.syncWater();date.select('r0');date.context.dateSelect.value='A';date.context.syncWater();date.respond();await flush();assert.match(date.e.parcelWaterDates.textContent,/2023-08-16/);assert.match(date.e.parcelWaterNote.textContent,/Sin comparación anterior/);
 const off=setup({delay:true});off.context.syncWater();off.e.waterToggle.checked=false;off.context.syncWater();off.respond();await flush();assert(!off.layer.visible);
 const closed=setup({delay:true});closed.context.syncWater();closed.select('r0');closed.context.selectedParcel=null;closed.respond();await flush();assert.equal(closed.e.parcelWaterValue.textContent,'—');
 const bad=setup({corrupt:true});bad.context.syncWater();await flush();assert(!bad.layer.visible);assert(!bad.e.waterRetry.hidden);await bad.select('r0');assert.equal(bad.e.parcelWaterValue.textContent,'No disponible');
 const count=bad.requests.length;bad.e.waterRetry.events.click();await flush();assert(bad.requests.length>count);
 const mismatch=setup();mismatch.context.syncWater();await flush();mismatch.context.parcelWebHash='b'.repeat(64);await mismatch.select('r0');assert.equal(mismatch.e.parcelWaterValue.textContent,'No disponible');
 const legacy=setup({mutate:d=>{d.version=1;}});legacy.context.syncWater();await flush();assert(!legacy.layer.visible);await legacy.select('r0');assert.equal(legacy.e.parcelWaterValue.textContent,'No disponible');
 console.log('PASS: current/old water, no previous, date/method/quality, ambiguity, unknown, stale selection/date, cache/integrity and retry');
})().catch(e=>{console.error(e);process.exitCode=1;});
