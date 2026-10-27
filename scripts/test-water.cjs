'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const code=fs.readFileSync('index.html','utf8').split('// BEGIN WATER UI')[1].split('// END WATER UI')[0];
const hash=b=>crypto.createHash('sha256').update(b).digest('hex'), h='a'.repeat(64);
const flush=async()=>{for(let i=0;i<40;i++) await Promise.resolve();};
function setup({corrupt=false,delay=false}={}) {
 const elements={},requests=[];let sourceReads=0;
 const el=id=>elements[id]??={value:'',checked:false,hidden:false,textContent:'',events:{},addEventListener(n,f){this.events[n]=f;}};
 const a={id:'A',datetime:'2026-09-24T11:00:00Z',quality_mask:{sha256:h}},b={id:'B',datetime:'2026-10-14T11:00:00Z',quality_mask:{sha256:h}};
 const data={version:1,method:'scl_new_surface_water_v1',status:'exploratory',resolution_m:20,min_valid_percent:80,
  area_method:'fractional_cell_intersection_25830',a:{id:a.id,datetime:a.datetime},b:{id:b.id,datetime:b.datetime},
  scl_sha256:[h,h],parcel_web_sha256:h,master_sha256:h,
  columns:['new_water_m2','water_both_dates_m2','evaluated_m2','parcel_m2'],
  parcels:Object.fromEntries(Array.from({length:919},(_,i)=>['r'+i,[0,0,1000,1000]]))};
 data.parcels.r0=[100,200,900,1000];data.parcels.r2=[100,0,500,1000];data.parcels.r3=[0,0,0,1000];
 const zones={type:'FeatureCollection',features:[{type:'Feature',properties:{refcat:'r0'},geometry:{type:'Polygon',coordinates:[]}}]};
 const pair={id:'comparison-'+'1'.repeat(24),a:'A',b:'B',parcel_web_sha256:h,water:{method:data.method,parcel_web_sha256:h}};
 const tableBytes=Buffer.from(JSON.stringify(data)),zoneBytes=Buffer.from(JSON.stringify(zones));
 for(const [k,name,bytes] of [['table','parcel-water.json',tableBytes],['zones','water-zones.geojson',zoneBytes]]) pair.water[k]={path:'sentinel/'+pair.id+'/'+name,sha256:hash(bytes)};
 const layer={visible:false,setVisible(v){this.visible=v;},setSource(s){this.source=s;}};
 const context={Map,Intl,TextDecoder,Uint8Array,crypto:{subtle:{digest:async(_,bytes)=>crypto.createHash('sha256').update(bytes).digest()}},
  document:{getElementById:el},waterLayer:layer,selectedParcel:null,parcelWebHash:h,areaFormat:new Intl.NumberFormat('es-ES',{maximumFractionDigits:2}),
  acquisitions:[b,a],dateSelect:{value:'B'},formatDate:d=>d.slice(0,10),productPath:(p,id,n,e)=>{assert.equal(p,`sentinel/${id}/${n}.${e}`);return p;},
  ol:{source:{Vector:class{constructor(o){this.options=o;}}},format:{GeoJSON:class{readFeatures(d,o){assert.equal(o.featureProjection,'EPSG:3857');sourceReads++;return d.features;}}}},
  fetch:path=>new Promise(resolve=>{const r={path,resolve};requests.push(r);if(!delay)resolve({ok:true,arrayBuffer:async()=>corrupt?Buffer.from('{}'):path.endsWith('.geojson')?zoneBytes:tableBytes});})};
 el('waterToggle').checked=true;el('compareDateA').value='A';
 vm.createContext(context);vm.runInContext(code,context);context.acceptWater({comparisons:[pair]});
 const feature=ref=>({get:key=>key==='refcat'?ref:1000});
 return {context,layer,e:elements,requests,sourceReads:()=>sourceReads,select(ref){context.selectedParcel=feature(ref);return context.refreshParcelWater();},
  respond(){for(const r of requests)r.resolve({ok:true,arrayBuffer:async()=>r.path.endsWith('.geojson')?zoneBytes:tableBytes});}};
}
(async()=>{
 const s=setup();s.context.syncWater();await flush();assert(s.layer.visible);assert.equal(s.requests.length,2);assert.equal(s.sourceReads(),1);
 await s.select('r0');assert.match(s.e.parcelWaterValue.textContent,/10%/);assert.match(s.e.parcelWaterNote.textContent,/20%.*10%/);
 await s.select('r1');assert.match(s.e.parcelWaterValue.textContent,/^0%/);
 await s.select('r2');assert.equal(s.e.parcelWaterValue.textContent,'No concluyente');assert.match(s.e.parcelWaterNote.textContent,/10%.*50%/);
 await s.select('r3');assert.equal(s.e.parcelWaterValue.textContent,'No concluyente');assert.match(s.e.parcelWaterNote.textContent,/100%/);
 s.e.waterToggle.checked=false;s.context.syncWater();await flush();assert(!s.layer.visible);assert.equal(s.e.parcelWaterValue.textContent,'No concluyente');
 s.e.waterToggle.checked=true;s.context.syncWater();await flush();assert(s.layer.visible);assert.equal(s.requests.length,2);assert.equal(s.sourceReads(),1);
 s.context.dateSelect.value='A';s.context.syncWater();await flush();assert(!s.layer.visible);assert.equal(s.e.parcelWaterValue.textContent,'—');assert(s.e.waterToggle.disabled);
 const late=setup({delay:true});late.context.syncWater();late.select('r0');late.select('r1');late.respond();await flush();assert.match(late.e.parcelWaterValue.textContent,/^0%/);
 const off=setup({delay:true});off.context.syncWater();off.e.waterToggle.checked=false;off.context.syncWater();off.respond();await flush();assert(!off.layer.visible);
 const closed=setup({delay:true});closed.context.syncWater();closed.select('r0');closed.context.selectedParcel=null;closed.respond();await flush();assert.equal(closed.e.parcelWaterValue.textContent,'—');
 const bad=setup({corrupt:true});bad.context.syncWater();await flush();assert(!bad.layer.visible);assert(!bad.e.waterRetry.hidden);await bad.select('r0');assert.equal(bad.e.parcelWaterValue.textContent,'No disponible');
 const count=bad.requests.length;bad.e.waterRetry.events.click();await flush();assert(bad.requests.length>count);
 const mismatch=setup();mismatch.context.syncWater();await flush();mismatch.context.parcelWebHash='b'.repeat(64);await mismatch.select('r0');assert.equal(mismatch.e.parcelWaterValue.textContent,'No disponible');
 console.log('PASS: water percentages, whole-parcel denominator, insufficient/unknown/zero, caches, source reuse, toggles, dates, stale selection, close, integrity and retry');
})().catch(e=>{console.error(e);process.exitCode=1;});
