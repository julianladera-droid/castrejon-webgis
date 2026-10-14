'use strict';
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const crypto=require('node:crypto');
const raw=fs.readFileSync('data/parcels/parcelas.geojson');
const data=JSON.parse(raw), meta=JSON.parse(fs.readFileSync('data/parcels/metadata.json'));
assert.equal(data.features.length,919);
assert.equal(meta.web_sha256,crypto.createHash('sha256').update(raw).digest('hex'));
assert.equal(meta.master_crs,'EPSG:25830');
assert.equal(meta.web_crs,'EPSG:4326');
assert.equal(new Set(data.features.map(f=>f.id)).size,919);
for(const f of data.features){
  assert.equal(f.id,f.properties.refcat);
  assert.deepEqual(Object.keys(f.properties).sort(),['area_m2','refcat']);
  assert(f.properties.area_m2>0);
  const rings=f.geometry.type==='Polygon'?f.geometry.coordinates:f.geometry.coordinates.flat();
  for(const ring of rings){
    assert(ring.length>=4); assert.deepEqual(ring[0],ring.at(-1));
    assert(ring.every(([x,y])=>x>-4.49&&x<-4.30&&y>39.79&&y<39.87));
  }
}
const code=fs.readFileSync('index.html','utf8').split('// BEGIN PARCEL UI')[1].split('// END PARCEL UI')[0].split('\n').slice(1).join('\n');
const flush=async()=>{for(let i=0;i<15;i++)await Promise.resolve();};
function setup(fail=false){
  let zoom=13.27,requests=0,resolve;
  const events={},els={};
  for(const id of ['parcelsToggle','parcelsStatus','parcelsRetry'])els[id]={checked:true,addEventListener:(n,f)=>events[id+n]=f};
  const parcels={setVisible(v){this.visible=v;},setOpacity(v){this.opacity=v;}};
  let count=0;
  vm.runInNewContext(code,{document:{getElementById:id=>els[id]},parcels,
    parcelSource:{addFeatures:f=>count+=f.length},view:{getZoom:()=>zoom,on:(n,f)=>events[n]=f},
    fetch:()=>{requests++;return new Promise(r=>resolve=r);},
    ol:{format:{GeoJSON:class{readFeatures(d,o){assert.equal(o.featureProjection,'EPSG:3857');return d.features;}}}}});
  return {els,parcels,events,requests:()=>requests,count:()=>count,
    zoom(z){zoom=z;events['change:resolution']();},
    respond(ok=!fail){resolve({ok,json:async()=>data});}};
}
(async()=>{
  const s=setup();assert.equal(s.requests(),0);assert.equal(s.parcels.visible,false);
  s.zoom(15);s.zoom(16);assert.equal(s.requests(),1);
  s.zoom(13);s.respond();await flush();assert.equal(s.count(),919);assert.equal(s.parcels.visible,false);
  s.zoom(15);assert.equal(s.parcels.visible,true);assert.equal(s.parcels.opacity,.425);
  s.zoom(16);assert.equal(s.parcels.opacity,.85);assert.equal(s.requests(),1);
  s.els.parcelsToggle.checked=false;s.events.parcelsTogglechange();assert.equal(s.parcels.visible,false);
  const bad=setup(true);bad.zoom(15);bad.respond();await flush();
  assert.equal(bad.parcels.visible,false);assert.equal(bad.els.parcelsRetry.hidden,false);
  bad.zoom(16);assert.equal(bad.requests(),1);bad.events.parcelsRetryclick();assert.equal(bad.requests(),2);
  bad.respond(true);await flush();assert.equal(bad.parcels.visible,true);
  console.log('PASS: parcel geometry/identity, public attributes, zoom, late response, single load, toggle and retry');
})().catch(e=>{console.error(e);process.exitCode=1;});
