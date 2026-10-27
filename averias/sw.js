/* Served by WordPress under /averias-campo/sw.js. Never cache API/session data. */
const ASSETS = __ASSETS__;
const CACHE = 'castrejon-field-v1';
const HOME = new URL('./', self.location).href;
const FILES = ['app.css','app.js','shared.js','icon.svg','manifest.webmanifest','vendor/ol.js','vendor/ol.css'].map(path=>new URL(path,ASSETS).href);
self.addEventListener('install',event=>event.waitUntil((async()=>{const cache=await caches.open(CACHE);await cache.addAll([HOME,...FILES]);})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{for(const name of await caches.keys())if(name.startsWith('castrejon-field-')&&name!==CACHE)await caches.delete(name);await self.clients.claim();})()));
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET')return;
  const url=new URL(event.request.url);
  if(url.href===HOME || (event.request.mode==='navigate' && url.origin===new URL(HOME).origin && url.pathname===new URL(HOME).pathname)){
    event.respondWith(fetch(event.request).then(async response=>{if(response.ok&&!response.redirected){const cache=await caches.open(CACHE);await cache.put(HOME,response.clone());}return response;}).catch(()=>caches.match(HOME)));return;
  }
  if(FILES.includes(url.href))event.respondWith(caches.match(event.request).then(hit=>hit||fetch(event.request)));
});
