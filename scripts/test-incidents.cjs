'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const A=require('../averias/shared.js');
const id='d005995d-5432-4b9f-a123-d8d438751111';
const record={id,kind:'fuga',priority:'normal',element:'Válvula 4',description:'Agua en la junta <script>alert(1)</script>',observed_at:'2026-01-01T10:00:00.000Z',longitude:-4.371848,latitude:39.834749,location_source:'manual',accuracy_m:null};
const feature={type:'Feature',id,geometry:{type:'Point',coordinates:[record.longitude,record.latitude]},properties:{...record,status:'pendiente',version:1,photo_path:`incidents/${id}/photo`}};
function page(features,next=null){return {type:'FeatureCollection',coordinate_reference_system:'EPSG:4326',features,next,as_of:'2026-01-02 10:00:00'};}
(async()=>{
  A.validate(record);A.publicFeature(feature);
  for(const bad of [{longitude:NaN},{latitude:91},{description:'x'},{priority:'<img>'},{location_source:'gps',accuracy_m:null},{observed_at:'invalid'}])assert.throws(()=>A.validate({...record,...bad}));
  assert.throws(()=>A.publicFeature({...feature,properties:{...feature.properties,photo_path:'https://evil.invalid/x'}}));
  const blob=await A.kmz(record,new Blob([new Uint8Array([0xff,0xd8,0xff,0xd9])],{type:'image/jpeg'}));
  const bytes=Buffer.from(await blob.arrayBuffer());let offset=0;const entries={};
  while(bytes.readUInt32LE(offset)===0x04034b50){const size=bytes.readUInt32LE(offset+18),n=bytes.readUInt16LE(offset+26),name=bytes.subarray(offset+30,offset+30+n).toString();entries[name]=bytes.subarray(offset+30+n,offset+30+n+size);offset+=30+n+size;}
  assert.deepEqual(Object.keys(entries),['doc.kml','files/foto.jpg']);
  assert.equal(entries['files/foto.jpg'][0],255);assert.match(entries['doc.kml'].toString(),/-4.371848,39.834749,0/);
  assert(!entries['doc.kml'].toString().includes('<script>'));assert.match(entries['doc.kml'].toString(),/files\/foto.jpg/);
  let calls=0;global.fetch=async()=>({ok:true,json:async()=>{calls++;return page([feature]);}});
  assert.equal((await A.list('https://example.org/api/')).length,1);assert.equal(calls,1);
  global.fetch=async()=>({ok:false,status:503,json:async()=>({})});await assert.rejects(()=>A.list('https://example.org/api/'));
  global.fetch=async()=>({ok:true,json:async()=>page([feature],id)});await assert.rejects(()=>A.list('https://example.org/api/'),/repetida/);
  global.fetch=async()=>({ok:true,json:async()=>({...page([]),coordinate_reference_system:'EPSG:3857'})});await assert.rejects(()=>A.list('https://example.org/api/'));
  const sw=fs.readFileSync('averias/sw.js','utf8'),events={};let cached,installed;
  vm.runInNewContext(sw.replace('__ASSETS__',JSON.stringify('https://example.org/plugin/app/')),{self:{location:'https://example.org/averias-campo/sw.js',addEventListener:(n,f)=>events[n]=f},URL,caches:{open:async()=>({addAll:async urls=>{cached=urls;}})}});
  events.install({waitUntil:promise=>{installed=promise;}});await installed;
  for(const match of fs.readFileSync('averias/index.html','utf8').matchAll(/(?:src|href)="([^"]+\.(?:js|css)(?:\?[^"]+)?)"/g))
    assert(cached.includes(new URL(match[1],'https://example.org/plugin/app/').href),'offline cache missing '+match[1]);
  for(const path of ['/wp-json/castrejon/v1/incidents','/wp-json/castrejon/v1/location-check','/averias-campo/session/','/wp-login.php']){let intercepted=false;events.fetch({request:{method:'GET',url:'https://example.org'+path,mode:'cors'},respondWith(){intercepted=true;}});assert.equal(intercepted,false);}
  for(const name of ['shared.js','map-layer.js','app.js','location.js','location-policy.js'])new vm.Script(fs.readFileSync('averias/'+name,'utf8'),{filename:name});
  console.log('PASS: validation, literal public fields, KMZ with embedded photo, network failures/pagination, no session/API cache, JS syntax');
})().catch(error=>{console.error(error);process.exitCode=1;});
