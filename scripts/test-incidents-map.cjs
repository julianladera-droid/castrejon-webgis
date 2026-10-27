'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const A=require('../averias/shared.js'),id='d005995d-5432-4b9f-a123-d8d438751111';
const feature={type:'Feature',id,geometry:{type:'Point',coordinates:[-4.37,39.83]},properties:{id,kind:'fuga',status:'pendiente',priority:'alta',element:'<script>literal</script>',description:'<img onerror=evil>',version:1,location_source:'manual',accuracy_m:null,observed_at:'2026-01-01T10:00:00Z',created_at:'2026-01-01T10:00:00Z',updated_at:'2026-01-01T10:00:00Z',closed_at:null,photo_path:`incidents/${id}/photo`}};
const flush=()=>new Promise(resolve=>setTimeout(resolve,10));
function setup(fail=false){
  const els={},make=()=>({hidden:true,style:{},value:'',checked:true,events:{},children:[],addEventListener(n,f){this.events[n]=f;},append(...x){this.children.push(...x);},replaceChildren(...x){this.children=x;},contains(){return false;},focus(){}}),el=id=>els[id]??=make();
  let hit,closed=0,source,layer;
  class Vector{constructor(){source=this;this.features=[];}clear(){this.features=[];}addFeatures(features){this.features=features;}}
  class Layer{constructor(){layer=this;this.visible=true;}getVisible(){return this.visible;}setVisible(v){this.visible=v;}}
  const map={addLayer(){},updateSize(){},forEachFeatureAtPixel(pixel,cb,opts){assert(opts.layerFilter(layer));return hit&&cb(hit);},getView(){return {animate(){}};}};
  const context={window:{CastrejonAverias:{...A,list:async()=>{if(fail)throw new Error('offline');return [feature];}}},document:{getElementById:el,createElement:make},URL,Date,
    ol:{source:{Vector},layer:{Vector:Layer},style:{Style:class{},Circle:class{},Fill:class{},Stroke:class{}},format:{GeoJSON:class{readFeatures(data){return data.features.map(f=>({getProperties:()=>f.properties,get:key=>f.properties[key],getGeometry:()=>({getCoordinates:()=>f.geometry.coordinates})}));}}}}};
  vm.runInNewContext(fs.readFileSync('averias/map-layer.js','utf8'),context);
  const ui=context.window.CastrejonIncidentLayer.init({map,closeParcel(){closed++;},setPanelOpen(){},compact:{matches:true}});
  return {els,el,ui,source,layer,get closed(){return closed;},setHit(){hit=source.features[0];}};
}
(async()=>{
  const s=setup();await flush();assert.equal(s.source.features.length,1);s.setHit();assert(s.ui.selectAtPixel([0,0]));assert.equal(s.closed,1);assert.equal(s.el('incidentCard').hidden,false);
  assert.equal(s.el('incidentDescription').textContent,'<img onerror=evil>');assert.match(String(s.el('incidentPhoto').src),/\/photo$/);
  s.el('incidentToggle').checked=false;s.el('incidentToggle').events.change();assert.equal(s.el('incidentCard').hidden,true);assert(!s.ui.selectAtPixel([0,0]));
  s.el('incidentFilter').value='resuelta';s.el('incidentFilter').events.change();assert.equal(s.source.features.length,0);
  const failed=setup(true);await flush();assert.match(failed.el('incidentStatus').textContent,/no disponibles/);assert.equal(failed.source.features.length,0);
  console.log('PASS: incident hit before parcel, literal text/photo, close on layer/filter, API failure distinct from empty');
})().catch(error=>{console.error(error);process.exitCode=1;});
