'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const crypto=require('node:crypto');
const code=fs.readFileSync('index.html','utf8').split('// BEGIN PARCEL NDVI')[1].split('// END PARCEL NDVI')[0].split('\n').slice(1).join('\n');
const flush=()=>new Promise(r=>setTimeout(r,25));
function fixture(id='A',date='2026-10-14T11:00:00Z',mutate=()=>{}){
  const parcels=Object.fromEntries(Array.from({length:919},(_,i)=>['r'+i,{mean:.4567,valid_pixels:9,total_pixels:10,valid_percent:90,status:'ok'}]));
  parcels.r1={mean:null,valid_pixels:0,total_pixels:0,valid_percent:0,status:'no_pixels'};
  parcels.r2={mean:0,valid_pixels:10,total_pixels:10,valid_percent:100,status:'ok'};
  parcels.r3={mean:null,valid_pixels:7,total_pixels:10,valid_percent:70,status:'insufficient'};
  for(const [ref,row] of Object.entries(parcels)) parcels[ref]={NDVI:[row.mean,row.valid_pixels,row.total_pixels],EVI2:[1.25,10,10],NDMI:[-.25,8,10]};
  parcels.r1.NDMI=[null,0,0];
  parcels.r3.NDMI=[null,7,10];
  const indices={NDVI:{sha256:'ndvi',resolution_m:10},EVI2:{sha256:'evi2',resolution_m:10},NDMI:{sha256:'ndmi',resolution_m:20}};
  const data={version:2,acquisition_id:id,datetime:date,indices,parcel_web_sha256:'web',method:'pixel_center_mean',min_valid_percent:80,columns:['mean','valid_pixels','total_pixels'],parcels};
  mutate(data);
  const bytes=Buffer.from(JSON.stringify(data));
  return {bytes,acquisition:{id,datetime:date,indices,parcel_indices:{path:`sentinel/${id}/parcel-indices.json`,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),parcel_web_sha256:'web'}}};
}
function setup(custom){
  const a=custom||fixture(),b=fixture('B','2026-09-24T11:00:00Z'),els={},requests=[];
  const context={Map,crypto:crypto.webcrypto,TextDecoder,Uint8Array,Date,selectedParcel:null,
    acquisitions:[a.acquisition,b.acquisition],dateSelect:{value:'A'},parcelWebHash:'web',refreshParcelNdvi:null,
    formatDate:d=>d.slice(0,10),productPath:(p,id)=>{assert.equal(p,`sentinel/${id}/parcel-indices.json`);return p;},
    document:{getElementById:id=>els[id]??={textContent:'',style:{},hidden:true}},
    fetch:path=>new Promise(resolve=>requests.push({path,resolve}))};
  vm.createContext(context);vm.runInContext(code,context);
  return {context,els,requests,a,b,select(ref){context.selectedParcel={get:()=>ref};return context.refreshParcelNdvi();},
    respond(index=0,bytes=a.bytes,ok=true){requests[index].resolve({ok,arrayBuffer:async()=>bytes});}};
}
(async()=>{
  const s=setup();s.context.refreshParcelNdvi();assert.equal(s.requests.length,0);
  s.select('r0');s.select('r1');assert.equal(s.requests.length,1);s.respond();await flush();
  assert.equal(s.els.parcelNdvi.textContent,'Sin datos suficientes');
  await s.select('r0');assert.equal(s.els.parcelNdvi.textContent,'0,46');assert.equal(s.requests.length,1);
  await s.select('r2');assert.equal(s.els.parcelNdvi.textContent,'0,00');
  await s.select('r3');assert.equal(s.els.parcelNdvi.textContent,'Sin datos suficientes');
  assert.match(s.els.parcelNdviCoverage.textContent,/70%/);
  assert.equal(s.els.parcelEvi2.textContent,'1,25');assert.equal(s.els.parcelNdmi.textContent,'Sin datos suficientes');
  await s.select('r0');assert.equal(s.els.parcelNdmi.textContent,'-0,25');assert.equal(s.requests.length,1);
  assert.equal(s.els.parcelNdmiMarker.style.left,'37.5%');
  assert.equal(s.els.parcelEvi2Marker.style.left,'100%');
  assert.equal(s.els.parcelEvi2.textContent,'1,25');
  await s.select('r2');assert.equal(s.els.parcelNdviMarker.style.left,'50%');
  await s.select('r3');assert.equal(s.els.parcelNdviScale.hidden,true);
  assert.equal(s.els.parcelEvi2Scale.hidden,false);
  const late=setup();late.select('r0');late.context.dateSelect.value='B';late.select('r0');
  late.respond(1,late.b.bytes);await flush();late.respond();await flush();
  assert.equal(late.els.parcelImageDate.textContent,'2026-09-24');
  const closed=setup();closed.select('r0');closed.context.selectedParcel=null;closed.respond();await flush();
  assert.notEqual(closed.els.parcelNdvi.textContent,'0,46');
  const bad=setup();bad.select('r0');bad.respond(0,Buffer.from('{}'));await flush();
  assert.equal(bad.els.parcelNdvi.textContent,'No disponible');
  assert.equal(bad.els.parcelNdviScale.hidden,true);
  bad.select('r0');assert.equal(bad.els.parcelNdviScale.hidden,true);assert.equal(bad.requests.length,2);bad.respond(1);await flush();
  assert.equal(bad.els.parcelNdvi.textContent,'0,46');
  const mismatch=setup();mismatch.context.parcelWebHash='different';await mismatch.select('r0');
  assert.equal(mismatch.requests.length,0);assert.equal(mismatch.els.parcelNdvi.textContent,'No disponible');
  const unavailable=setup();unavailable.context.acquisitions=[];await unavailable.select('r0');
  assert.equal(unavailable.requests.length,0);assert.equal(unavailable.els.parcelImageDate.textContent,'—');
  const wrongGrid=setup(fixture('A','2026-10-14T11:00:00Z',d=>{d.indices.NDMI.resolution_m=10;}));
  wrongGrid.select('r0');wrongGrid.respond();await flush();assert.equal(wrongGrid.els.parcelNdmi.textContent,'No disponible');
  const badMean=setup(fixture('A','2026-10-14T11:00:00Z',d=>{d.parcels.r0.NDMI[0]=2;}));
  badMean.select('r0');badMean.respond();await flush();
  assert.equal(badMean.els.parcelNdmi.textContent,'No disponible');assert.equal(badMean.els.parcelNdvi.textContent,'No disponible');
  console.log('PASS: three indices, independent coverage, EVI2 range, native resolutions, lazy/shared load, caching, dates, missing/zero, stale responses, close, hashes and retry');
})().catch(e=>{console.error(e);process.exitCode=1;});
