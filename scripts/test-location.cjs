'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const L=require('../averias/location.js'),A=require('../averias/shared.js'),policy=require('../averias/location-policy.js');
const cases=require('./fixtures/location-cases.json');
for(const test of cases){
  const before=JSON.stringify(test),quality=L.locationQuality(test);
  assert.equal(quality.status,test.status,test.name);
  assert.deepEqual(quality.warnings.map(w=>w.code),test.codes,test.name);
  assert.equal(JSON.stringify(test),before,'QA must not change payload or GPS accuracy');
  assert.match(L.publicationPrompt(test,quality),/¿Publicar\?/);
}
const location={longitude:-4.371848,latitude:39.834749,location_source:'gps',accuracy_m:4};
for(const bad of [{longitude:NaN},{latitude:Infinity},{longitude:181},{latitude:-91},{latitude:'39.83'},{longitude:null},{longitude:true},{accuracy_m:null},{accuracy_m:-1},{accuracy_m:100001}])
  assert.throws(()=>L.locationQuality({...location,...bad}));
assert.deepEqual(L.manualLocation(' 39,834749 ','-4,371848'),{...location,location_source:'manual',accuracy_m:null});
assert.equal(L.manualLocation('39.834749','-4.371848').latitude,39.834749);
for(const [lat,lon] of [['','-4'],[' ','-4'],['39x','-4'],['NaN','-4'],['Infinity','-4'],['39,8.2','-4'],['39 8','-4'],['91','-4'],['39','181'],['1e2','-4']])assert.throws(()=>L.manualLocation(lat,lon));
const record={id:crypto.randomUUID(),kind:'fuga',priority:'normal',description:'Junta rota',element:'',observed_at:'2026-01-01T10:00:00Z',...location};
// Published legacy records and all mathematically valid outside locations still pass the contract.
for(const test of cases){A.validate({...record,...test});}
assert.deepEqual(policy,JSON.parse(fs.readFileSync('wordpress/castrejon-averias/location-policy.json')));
// Browser build uses exactly the same policy and helper as CommonJS, without a network lookup.
const browser={};vm.runInNewContext(fs.readFileSync('averias/location-policy.js','utf8'),browser);
vm.runInNewContext(fs.readFileSync('averias/location.js','utf8'),browser);
for(const test of cases)assert.equal(JSON.stringify(browser.CastrejonLocation.locationQuality(test)),JSON.stringify(L.locationQuality(test)));
// Exercise an unclosed ring and a hole; the real perimeter has one exterior ring.
const old=policy.geometry.coordinates,oldBox=policy.bbox;
policy.geometry.coordinates=[[[0,0],[4,0],[4,4],[0,4]],[[1,1],[3,1],[3,3],[1,3]]];
policy.bbox=[0,0,4,4];
try{
  assert.equal(L.locationQuality({...location,longitude:2,latitude:2}).status,'outside_reference');
  assert.equal(L.locationQuality({...location,longitude:0.5,latitude:0.5}).status,'inside_reference');
  assert.equal(L.locationQuality({...location,longitude:1,latitude:2}).status,'inside_reference');
  assert.equal(L.locationQuality({...location,longitude:0,latitude:0}).status,'inside_reference');
}finally{policy.geometry.coordinates=old;policy.bbox=oldBox;}
console.log(`PASS: ${cases.length} spatial cases, impossible coordinates, decimal parsing, no territorial rejection, browser parity, packaged policy`);
