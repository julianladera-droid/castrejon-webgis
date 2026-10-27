'use strict';
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict'), crypto=require('node:crypto');
const code=fs.readFileSync('index.html','utf8').split('// BEGIN COMPARISON UI')[1].split('// END COMPARISON UI')[0];
const flush=()=>new Promise(r=>setTimeout(r,25));
function setup(mutate=()=>{}) {
  const els={}, requests=[], sources=[];
  const el=id=>els[id]??={textContent:'',value:'',style:{},checked:false,hidden:true,events:{},
    addEventListener(n,f){this.events[n]=f;},replaceChildren(...children){this.children=children;}};
  const indices=id=>Object.fromEntries(['NDVI','EVI2','NDMI'].map(name=>[name,{sha256:id+name,
    resolution_m:name==='NDMI'?20:10,projection:'EPSG:3857',extent:[0,0,100,100],range:[-1,1],
    colors:['#000000','#ffffff'],image:`sentinel/${id}/${name}.png`}]));
  const a={id:'A',datetime:'2026-09-24T11:00:00Z',indices:indices('A')},b={id:'B',datetime:'2026-10-14T11:00:00Z',indices:indices('B')};
  const data={version:1,method:'common_valid_pixel_centres',min_valid_percent:80,a:{id:a.id,datetime:a.datetime},b:{id:b.id,datetime:b.datetime},
    parcel_web_sha256:'web',columns:['mean_a','mean_b','delta_b_minus_a','common_pixels','total_pixels'],
    indices:Object.fromEntries(['NDVI','EVI2','NDMI'].map(name=>[name,{resolution_m:name==='NDMI'?20:10,pixel_area_m2:name==='NDMI'?400:100,a_sha256:a.indices[name].sha256,b_sha256:b.indices[name].sha256}])),
    parcels:Object.fromEntries(Array.from({length:919},(_,i)=>['r'+i,{NDVI:[.2,.4,.2,9,10],EVI2:[1.5,1.25,-.25,9,10],NDMI:[null,null,null,7,10]}]))};
  data.parcels.r1.NDVI=[0,0,0,10,10]; mutate(data);
  const bytes=Buffer.from(JSON.stringify(data)),id='comparison-'+'a'.repeat(24);
  const pair={id,a:'A',b:'B',parcel_web_sha256:'web',path:`sentinel/${id}/parcel-comparison.json`,sha256:crypto.createHash('sha256').update(bytes).digest('hex')};
  const layer=()=>({visible:false,events:{},on(n,f){this.events[n]=f;},setVisible(v){this.visible=v;},setSource(s){this.source=s;},setOpacity(o){this.opacity=o;}});
  const la=layer(),lb=layer();let renders=0;
  class ImageStatic{constructor(options){this.options=options;this.events={};sources.push(this);}on(n,f){this.events[n]=f;}}
  const context={Map,crypto:crypto.webcrypto,TextDecoder,Uint8Array,Intl,selectedParcel:null,parcelWebHash:'web',
    acquisitions:[b,a],dateSelect:el('sentinelDate'),indexSelect:el('sentinelIndex'),satelliteStatus:el('sentinelStatus'),
    compareLayerA:la,compareLayerB:lb,formatDate:d=>d.slice(0,10),
    productPath(p,id,name,ext){assert.equal(p,`sentinel/${id}/${name}.${ext}`);return p;},
    map:{getSize:()=>[100,50],render(){renders++;}},
    ol:{source:{ImageStatic},render:{getRenderPixel:(e,p)=>p}},
    document:{getElementById:el,createElement:()=>({})},
    fetch:path=>new Promise(resolve=>requests.push({path,resolve}))};
  context.dateSelect.value='B';el('compareOpacity').value='1';el('compareSwipe').value='50';
  context.updateSatellite=()=>context.syncComparison();
  vm.createContext(context);vm.runInContext(code,context);context.acceptComparisons({comparisons:[pair]});
  return {context,els,requests,sources,la,lb,pair,data,bytes,renders:()=>renders,
    enable(){els.compareToggle.checked=true;els.compareToggle.events.change();},
    select(ref){context.selectedParcel={get:()=>ref};return context.refreshParcelComparison();},
    respond(payload=bytes){requests[requests.length-1].resolve({ok:true,arrayBuffer:async()=>payload});}};
}
(async()=>{
  const s=setup();assert.equal(s.els.compareToggle.disabled,false);assert.equal(s.requests.length,0);
  s.enable();assert(s.la.visible&&s.lb.visible);assert.equal(s.sources.length,2);assert.equal(s.requests.length,0);
  s.sources.forEach(x=>x.events.imageloadend());assert.match(s.els.compareStatus.textContent,/misma escala/);
  const points=[];const canvas={save(){},beginPath(){},moveTo(...p){points.push(p);},lineTo(...p){points.push(p);},closePath(){},clip(){},restore(){}};
  s.la.events.prerender({context:canvas});s.la.events.postrender({context:canvas});assert.deepEqual(points,[[0,0],[50,0],[50,50],[0,50]]);
  s.els.compareSwipe.value='100';s.els.compareSwipe.events.input();assert.equal(s.els.compareDivider.style.left,'100%');assert.equal(s.renders(),1);
  s.select('r0');s.select('r1');assert.equal(s.requests.length,1);s.respond();await flush();
  assert.equal(s.els.compareNDVIDelta.textContent,'0,000');assert.equal(s.els.compareEVI2Delta.textContent,'-0,250');
  assert.equal(s.els.compareNDMIDelta.textContent,'—');assert.equal(s.els.compareNDMICoverage.textContent,'70%');
  await s.select('r0');assert.equal(s.els.compareNDVIDelta.textContent,'+0,200');assert.equal(s.requests.length,1);
  s.els.compareToggle.checked=false;s.context.syncComparison();assert(!s.la.visible&&!s.lb.visible);assert.equal(s.els.parcelSingleIndices.hidden,false);
  s.enable();assert.equal(s.sources.length,2);assert.equal(s.requests.length,1);
  s.context.dateSelect.value='A';s.context.syncComparison();assert(!s.la.visible&&!s.lb.visible);assert.match(s.els.compareStatus.textContent,/distintas/);
  const late=setup();late.enable();late.select('r0');late.els.compareToggle.checked=false;late.context.syncComparison();late.respond();await flush();assert.equal(late.els.compareNDVIDelta.textContent,'—');
  const corrupt=setup(d=>d.parcels.r0.NDVI=[.2,.4,99,9,10]);corrupt.enable();corrupt.select('r0');corrupt.respond();await flush();
  assert.equal(corrupt.els.compareNDVIDelta.textContent,'—');assert.match(corrupt.els.parcelComparisonNote.textContent,/no disponible/);
  const failed=setup();failed.enable();failed.sources[0].events.imageloaderror();assert(!failed.la.visible&&!failed.lb.visible);
  failed.enable();assert.equal(failed.sources.length,3);assert(failed.la.visible&&failed.lb.visible);
  const badHash=setup();badHash.enable();badHash.select('r0');badHash.respond(Buffer.from('{}'));await flush();assert.match(badHash.els.parcelComparisonNote.textContent,/no disponible/);
  badHash.select('r0');assert.equal(badHash.requests.length,2);badHash.respond();await flush();assert.equal(badHash.els.compareNDVIDelta.textContent,'+0,200');
  console.log('PASS: A/B clipping, same scales, signed paired changes, zero/nodata, caching, stale selections, off/same-date, integrity and image retries');
})().catch(e=>{console.error(e);process.exitCode=1;});
