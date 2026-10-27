// npm/pnpm install --prefix artifacts/qa @wp-playground/cli@3.1.61 fake-indexeddb@6.2.6
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {runCLI}=await import(pathToFileURL(path.join(root,'artifacts/qa/node_modules/@wp-playground/cli/index.js')));
const blueprint={preferredVersions:{php:'8.3',wp:'6.9'},steps:[
  {step:'defineWpConfigConsts',consts:{AUTOMATIC_UPDATER_DISABLED:true,DISABLE_WP_CRON:true}},
  {step:'installPlugin',pluginData:{resource:'literal',name:'castrejon-averias.zip',contents:new Uint8Array(fs.readFileSync(path.join(root,'artifacts/castrejon-averias-1.0.0.zip')))},options:{activate:true}},
  {step:'setSiteOptions',options:{permalink_structure:'/%postname%/'}},
  {step:'runPHP',code:"<?php require '/wordpress/wp-load.php'; flush_rewrite_rules();"}
]};
let server;
try{
  server=await runCLI({command:'server',port:9410,workers:2,php:'8.3',wp:'6.9',blueprint,login:false});
  const result=await server.playground.run({code:fs.readFileSync(path.join(root,'scripts/test-wordpress-incidents.php'),'utf8')});
  const text=result.text??new TextDecoder().decode(result.bytes);
  console.log(text);
  if(result.exitCode!==0||!text.includes('PASS:'))throw new Error('WordPress integration failed.');
  const response=await fetch(server.serverUrl+'/averias-campo/');
  const html=await response.text();
  if(!response.ok||!html.includes('Del campo al mapa.')||html.includes('__API_BASE__'))throw new Error('Capture route failed');
  const anon=await fetch(server.serverUrl+'/averias-campo/session/').then(r=>r.json());
  if(anon.authorized||anon.nonce)throw new Error('Anonymous session leaked authorization');
  const denied=await fetch(server.serverUrl+'/wp-json/castrejon/v1/incidents',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  if(denied.status!==403)throw new Error('HTTP anonymous write not rejected');
  const cookieResult=await server.playground.run({code:"<?php require '/wordpress/wp-load.php'; $expiry=time()+3600; $token=WP_Session_Tokens::get_instance(1)->create($expiry); echo LOGGED_IN_COOKIE.'='.rawurlencode(wp_generate_auth_cookie(1,$expiry,'logged_in',$token));"});
  const cookie=cookieResult.text??new TextDecoder().decode(cookieResult.bytes);
  const authed=await fetch(server.serverUrl+'/averias-campo/session/',{headers:{Cookie:cookie}}).then(r=>r.json());
  if(!authed.authorized||!authed.nonce)throw new Error('Authorized session unavailable');
  const withoutNonce=await fetch(server.serverUrl+'/wp-json/castrejon/v1/incidents',{method:'POST',headers:{'Content-Type':'application/json',Cookie:cookie},body:'{}'});
  if(withoutNonce.status!==403)throw new Error('Missing nonce did not reject write');
  const withNonce=await fetch(server.serverUrl+'/wp-json/castrejon/v1/incidents',{method:'POST',headers:{'Content-Type':'application/json',Cookie:cookie,'X-WP-Nonce':authed.nonce},body:'{}'});
  if(withNonce.status!==422)throw new Error('Valid cookie/nonce did not reach validation');
  const sw=await fetch(server.serverUrl+'/averias-campo/sw.js').then(r=>r.text());
  if(sw.includes('__ASSETS__'))throw new Error('Service worker substitution failed');
  console.log('PASS: capture HTML, session bootstrap, actual HTTP cookie/nonce authorization, service worker route');
  if(process.argv.includes('--preview')){console.log('Preview: '+server.serverUrl+'/averias-campo/');await new Promise(()=>{});}
}finally{if(server)await server[Symbol.asyncDispose]();}
