'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('index.html', 'utf8');
const code = html.split('// BEGIN SENTINEL UI')[1].split('// END SENTINEL UI')[0].split('\n').slice(1).join('\n');
const sources = [];
const fixture = JSON.parse(fs.readFileSync('scripts/fixtures/sentinel-catalog.json', 'utf8'));
const flush = async () => { for (let i=0;i<10;i++) await Promise.resolve(); };
function setup(response) {
  const elements = {};
  const element = () => ({value:'',style:{},events:{},hidden:false,disabled:true,
    addEventListener(n, f) {this.events[n] = f;}, replaceChildren(...children) {this.children = children;}});
  const sentinel = {visible:false, opacity:.8,setVisible(v){this.visible=v;},
    setSource(s){this.source=s;},setOpacity(v){this.opacity=v;}};
  class ImageStatic {
    constructor(options){this.options=options;this.events={};sources.push(this);}
    on(n, f){this.events[n]=f;}
  }
  const context = {sentinel, fetch: async () => response,
    document: {getElementById: id => elements[id] ??= element(), createElement: element},
    ol:{source:{ImageStatic}}};
  vm.runInNewContext(code, context);
  return {elements, sentinel};
}
(async () => {
  const {elements:e, sentinel:s} = setup({ok:true,json:async()=>fixture});
  await flush();
  assert.equal(e.sentinelIndex.disabled, false);
  assert.equal(s.visible, false);
  e.sentinelIndex.value='NDVI'; e.sentinelIndex.events.change();
  assert.equal(s.visible,true);
  const old = s.source;
  assert.match(e.sentinelDownload.href, /NDVI.tif$/);
  e.sentinelIndex.value='NDMI'; e.sentinelIndex.events.change();
  old.events.imageloaderror(); // stale failure cannot hide a new selection
  assert.equal(s.visible,true);
  s.source.events.imageloadend();
  assert.match(e.sentinelStatus.textContent,/NDMI/);
  assert.match(e.sentinelMeaning.textContent,/no mide directamente/);
  e.sentinelOpacity.events.input({target:{value:'0'}});
  assert.equal(s.opacity,0);
  s.source.events.imageloaderror();
  assert.equal(s.visible,false);
  e.sentinelIndex.value=''; e.sentinelIndex.events.change();
  assert.equal(e.sentinelDetails.hidden,true);
  const broken=setup({ok:false}); await flush();
  assert.match(broken.elements.sentinelStatus.textContent,/no disponible/);
  assert.equal(broken.sentinel.visible,false);
  const bad = JSON.parse(JSON.stringify(fixture));
  bad.acquisitions[0].indices.NDVI.image='https://untrusted.example/x.png';
  const invalid = setup({ok:true,json:async()=>bad}); await flush();
  invalid.elements.sentinelIndex.value='NDVI'; invalid.elements.sentinelIndex.events.change();
  assert.equal(invalid.sentinel.visible,false);
  console.log('PASS: Sentinel UI selection, dates, opacity, stale responses, failures and same-origin paths');
})().catch(e=>{console.error(e);process.exitCode=1;});
