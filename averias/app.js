(async () => {
  'use strict';
  const A=window.CastrejonAverias, L=window.CastrejonLocation, $=id=>document.getElementById(id), storage=A.drafts();
  const configured=!document.querySelector('meta[name="api-base"]').content.startsWith('__');
  const base=configured?document.querySelector('meta[name="api-base"]').content:null;
  const home=configured?document.querySelector('meta[name="app-home"]').content:null;
  let session={authorized:false}, currentId=crypto.randomUUID(), location=null, photo=null, previewUrl=null, dirty=false, busy=false, locked=false;
  let publicItems=[], map, source;
  let coordinatesEdited=false;
  function locationReview(value){
    try{return L.locationQuality(value);}
    catch(error){return {severity:'danger',warnings:[{code:'invalid_location',message:error.message}]};}
  }
  function qualityNotice(target,value){
    target.replaceChildren();target.hidden=!value;if(!value)return;
    target.className=`location-quality ${value.severity}`;
    const title=document.createElement('strong');title.textContent=value.warnings.length?'Revisión de ubicación':'Ubicación dentro del perímetro de referencia';target.append(title);
    for(const warning of value.warnings){const p=document.createElement('p');p.textContent=warning.message;target.append(p);}
  }
  function message(text,error=false){$('message').textContent=text;$('message').hidden=false;$('message').classList.toggle('error',error);}
  function button(text,action,disabled=false){const b=document.createElement('button');b.type='button';b.textContent=text;b.disabled=disabled;b.addEventListener('click',()=>perform(action));return b;}
  async function perform(action){if(busy)return;busy=true;try{await action();}catch(error){message(error.message||'No se pudo completar la operación.',true);}finally{busy=false;}}
  function dateInput(value=new Date()){return new Date(value.getTime()-value.getTimezoneOffset()*60000).toISOString().slice(0,16);}
  $('observedAt').value=dateInput();
  function setPhoto(value){photo=value;if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=value?URL.createObjectURL(value):null;$('photoPreview').hidden=!value;$('photoHint').hidden=!!value;if(value)$('photoPreview').src=previewUrl;else $('photoPreview').removeAttribute('src');}
  function setLocation(value){location=value;coordinatesEdited=false;$('latitude').value=value?.latitude??'';$('longitude').value=value?.longitude??'';
    $('locationStatus').textContent=value?(value.location_source==='gps'?`GPS · precisión aproximada ±${Math.round(value.accuracy_m)} m${value.accuracy_m>50?' · Revisa el punto antes de guardar.':''}`:'Punto marcado manualmente · sin precisión GPS'):'Todavía no has marcado la ubicación.';
    qualityNotice($('locationQuality'),value?locationReview(value):null);
    if(source){source.clear();if(value&&Number.isFinite(value.longitude)&&Math.abs(value.longitude)<=180&&Number.isFinite(value.latitude)&&Math.abs(value.latitude)<85.05112878){const coordinate=ol.proj.fromLonLat([value.longitude,value.latitude]);source.addFeature(new ol.Feature(new ol.geom.Point(coordinate)));map.getView().animate({center:coordinate,zoom:17,duration:200});}}
  }
  function applyManualLocation(){setLocation(L.manualLocation($('latitude').value,$('longitude').value));dirty=true;}
  for(const id of ['latitude','longitude'])$(id).addEventListener('input',()=>{
    coordinatesEdited=true;dirty=true;$('locationStatus').textContent='Coordenadas manuales editadas · sin precisión GPS. Se comprobarán al guardar o descargar.';
    $('locationQuality').hidden=true;
  });
  if(window.ol){
    source=new ol.source.Vector();map=new ol.Map({target:'locationMap',layers:[new ol.layer.Tile({source:new ol.source.XYZ({url:'https://tms-pnoa-ma.idee.es/1.0.0/pnoa-ma/{z}/{x}/{-y}.jpeg',maxZoom:19,attributions:'PNOA · IGN/CNIG'})}),new ol.layer.Vector({source,style:new ol.style.Style({image:new ol.style.Circle({radius:9,fill:new ol.style.Fill({color:'#c55128'}),stroke:new ol.style.Stroke({color:'white',width:3})})})})],view:new ol.View({center:ol.proj.fromLonLat([-4.371848,39.834749]),zoom:13.27}),controls:[new ol.control.Zoom(),new ol.control.Attribution({collapsible:false})]});
    map.on('singleclick',event=>{if(locked||busy)return;const [longitude,latitude]=ol.proj.toLonLat(event.coordinate);setLocation({longitude,latitude,location_source:'manual',accuracy_m:null});dirty=true;});
  }else{$('locationMap').textContent='Mapa no disponible. Usa GPS o introduce las coordenadas.';}
  function lock(value){locked=value;for(const field of $('incidentForm').querySelectorAll('input,select,textarea,button'))field.disabled=value; $('newDraft').disabled=false;$('exportDraft').disabled=false;}
  function reset(){currentId=crypto.randomUUID();$('incidentForm').reset();$('observedAt').value=dateInput();setPhoto(null);setLocation(null);lock(false);dirty=false;$('saveStatus').textContent='El borrador se guarda solo en este dispositivo. No aparece en el mapa público.';}
  $('newDraft').addEventListener('click',()=>{if(busy)return;if(dirty&&!confirm('Hay cambios sin guardar. ¿Abrir una ficha nueva y descartarlos?'))return;reset();});
  $('incidentForm').addEventListener('input',()=>{dirty=true;});
  $('photo').addEventListener('change',()=>perform(async()=>{if(!$('photo').files.length)return;const value=await A.photoFromFile($('photo').files[0]);setPhoto(value);dirty=true;}));
  $('locate').addEventListener('click',()=>perform(async()=>{
    if(!navigator.geolocation)throw new Error('Este navegador no ofrece GPS. Marca la ubicación manualmente.');
    $('locationStatus').textContent='Buscando posición GPS…';
    try {const position=await new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,timeout:20000,maximumAge:0}));setLocation({latitude:position.coords.latitude,longitude:position.coords.longitude,accuracy_m:position.coords.accuracy,location_source:'gps'});dirty=true;}
    catch(error){if(!coordinatesEdited)setLocation(location);throw new Error(error.code===1?'Permite la ubicación en el navegador o marca el punto manualmente.':'No se ha obtenido una posición GPS. Puedes marcarla manualmente.');}
  }));
  $('manualLocation').addEventListener('click',()=>perform(async()=>applyManualLocation()));
  function collect(){if(coordinatesEdited)applyManualLocation();if(!location)throw new Error('Obtén la ubicación GPS o marca un punto.');if(!photo)throw new Error('Añade una fotografía de la avería.');const date=new Date($('observedAt').value);if(!Number.isFinite(date.getTime()))throw new Error('Revisa la fecha.');return A.validate({id:currentId,kind:$('kind').value,priority:$('priority').value,element:$('element').value.trim(),description:$('description').value.trim(),observed_at:date.toISOString(),...location});}
  async function save(){const payload=collect();await storage.put({id:currentId,payload,photo,savedAt:Date.now(),attempted:false,published:false});dirty=false;$('saveStatus').textContent='Borrador guardado en este dispositivo. Revisa «Mis borradores» para publicarlo.';await renderDrafts();message('Borrador guardado con su fotografía. Todavía no está publicado.');}
  $('incidentForm').addEventListener('submit',event=>{event.preventDefault();perform(save);});
  $('exportDraft').addEventListener('click',()=>perform(async()=>{const payload=collect();A.download(await A.kmz(payload,photo),`averia-${payload.id}.kmz`);}));
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  async function access(){
    if(!configured){$('sessionStatus').textContent='Vista local: puedes guardar borradores y descargar KMZ. La publicación se activa al instalar el plugin en WordPress.';$('sessionRefresh').hidden=true;return;}
    try{session=await A.request(new URL('session/',home),{credentials:'same-origin'});$('login').href=session.login_url;$('login').hidden=session.authorized;
      $('sessionStatus').textContent=session.authorized?'Acceso autorizado. Puedes publicar averías y actualizar su estado.':'Para publicar, entra con una cuenta de WordPress con permiso de averías. Puedes preparar borradores sin entrar.';
    }catch{session={authorized:false};$('sessionStatus').textContent='No se puede comprobar el acceso. Conserva tus borradores y reintenta con conexión.';}
    await renderDrafts();renderPublished();
  }
  $('sessionRefresh').addEventListener('click',()=>perform(access));
  async function publish(id){
    if(!session.authorized)throw new Error('Entra en WordPress con una cuenta autorizada antes de publicar.');
    const draft=await storage.get(id);if(!draft||draft.published)return;
    if(id===currentId&&dirty)throw new Error('Guarda los cambios de la ficha antes de publicar su borrador.');
    if(!draft.attempted){
      // Server recomputes QA before the first write; no review fields enter the immutable payload/hash.
      const {longitude,latitude,location_source,accuracy_m}=draft.payload;
      const quality=await A.request(new URL('location-check',base),{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-WP-Nonce':session.nonce},body:JSON.stringify({longitude,latitude,location_source,accuracy_m})});
      if(!Array.isArray(quality.warnings)||!['ok','notice','warning','danger'].includes(quality.severity)||quality.warnings.some(w=>typeof w.message!=='string'))throw new Error('No se pudo comprobar la ubicación. El borrador se conserva.');
      if(!confirm(L.publicationPrompt(draft.payload,quality)))return;
    }
    // Freeze the exact payload before any network attempt; unknown outcomes retry the same UUID/data.
    draft.attempted=true;await storage.put(draft);if(id===currentId)lock(true);await renderDrafts();
    try{
      const result=await A.request(new URL('incidents',base),{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-WP-Nonce':session.nonce},body:JSON.stringify({...draft.payload,photo_base64:await A.base64(draft.photo)})});
      A.publicFeature(result);draft.published=true;await storage.put(draft);await renderDrafts();message('Avería publicada. Ya puede consultarse en el mapa público.');await refreshPublished();
    }catch(error){message(`${error.message} El borrador y la foto se conservan. Reintenta el envío de esta misma ficha.`,true);await renderDrafts();}
  }
  async function renderDrafts(){
    let drafts;try{drafts=await storage.all();}catch(error){message(error.message,true);return;}
    drafts.sort((a,b)=>b.savedAt-a.savedAt);$('draftCount').textContent=drafts.filter(x=>!x.published).length;$('draftList').replaceChildren();
    if(!drafts.length){const p=document.createElement('p');p.className='empty';p.textContent='Aún no hay borradores en este dispositivo.';$('draftList').append(p);}
    for(const draft of drafts){const item=document.createElement('article');item.className='record';const title=document.createElement('h3');title.textContent=`${A.labels[draft.payload.kind]} · ${draft.id.slice(0,8)}`;const state=document.createElement('span');state.className='status';state.textContent=draft.published?'Publicada':draft.attempted?'Envío pendiente de confirmar':'Borrador local';const p=document.createElement('p');p.textContent=draft.payload.description;const actions=document.createElement('div');actions.className='actions';
      actions.append(button('Abrir',async()=>{if(dirty&&!confirm('¿Descartar los cambios sin guardar y abrir este borrador?'))return;currentId=draft.id;for(const key of ['kind','priority','element','description'])$(key).value=draft.payload[key];$('observedAt').value=dateInput(new Date(draft.payload.observed_at));setPhoto(draft.photo);setLocation({latitude:draft.payload.latitude,longitude:draft.payload.longitude,location_source:draft.payload.location_source,accuracy_m:draft.payload.accuracy_m});lock(draft.attempted);dirty=false;$('saveStatus').textContent=draft.attempted?'Ficha enviada: se conserva sin cambios para evitar duplicados. Actualiza el estado desde Publicadas.':'Borrador local abierto.';$('capture').scrollIntoView();}));
      actions.append(button('KMZ',async()=>A.download(await A.kmz({...draft.payload,status:draft.published?'pendiente':undefined},draft.photo),`averia-${draft.id}.kmz`)));
      if(!draft.published)actions.append(button(draft.attempted?'Reintentar envío':'Publicar',()=>publish(draft.id),!session.authorized));
      actions.append(button('Quitar del móvil',async()=>{if(!confirm('¿Quitar esta copia local y su foto? No borra una avería ya publicada.'))return;await storage.remove(draft.id);if(currentId===draft.id)reset();await renderDrafts();}));
      const position=document.createElement('p');position.className='hint';position.textContent=`Latitud ${draft.payload.latitude} · Longitud ${draft.payload.longitude}`;
      const quality=document.createElement('div');qualityNotice(quality,locationReview(draft.payload));
      item.append(title,state,p,position,quality,actions);$('draftList').append(item);
    }
  }
  async function refreshPublished(){
    if(!base){$('publishedStatus').textContent='La consulta estará disponible al conectar WordPress.';return;}
    $('publishedStatus').textContent='Consultando averías…';
    try{publicItems=await A.list(base);$('publishedStatus').textContent=`${publicItems.length} averías · actualizado ${new Date().toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit'})}`;renderPublished();}
    catch(error){publicItems=[];renderPublished();$('publishedStatus').textContent='No se pudieron consultar las averías. Pulsa Actualizar para reintentar.';}
  }
  function renderPublished(){
    $('publishedList').replaceChildren();const items=publicItems.filter(f=>!$('statusFilter').value||f.properties.status===$('statusFilter').value).sort((a,b)=>b.properties.created_at.localeCompare(a.properties.created_at));
    for(const feature of items){const p=feature.properties,item=document.createElement('article');item.className='record';const title=document.createElement('h3');title.textContent=`${A.labels[p.kind]} · ${p.id.slice(0,8)}`;const state=document.createElement('span');state.className=`status ${p.status}`;state.textContent=A.labels[p.status];const desc=document.createElement('p');desc.textContent=p.description;const img=document.createElement('img');img.src=new URL(p.photo_path,base);img.alt='Fotografía de la avería';img.loading='lazy';img.onerror=()=>{img.hidden=true;};const actions=document.createElement('div');actions.className='actions';
      actions.append(button('Descargar KMZ',async()=>{const response=await fetch(new URL(p.photo_path,base),{credentials:'omit'});if(!response.ok)throw new Error('No se pudo descargar la foto.');A.download(await A.kmz({...p,longitude:feature.geometry.coordinates[0],latitude:feature.geometry.coordinates[1]},await response.blob()),`averia-${p.id}.kmz`);}));
      if(session.authorized){const label=document.createElement('label');label.textContent='Cambiar estado';const select=document.createElement('select');for(const value of ['pendiente','en_reparacion','resuelta']){const option=document.createElement('option');option.value=value;option.textContent=A.labels[value];select.append(option);}select.value=p.status;label.append(select);item.append(label);actions.append(button('Guardar estado',async()=>{try{await A.request(new URL(`incidents/${p.id}`,base),{method:'PATCH',credentials:'same-origin',headers:{'Content-Type':'application/json','X-WP-Nonce':session.nonce},body:JSON.stringify({status:select.value,version:p.version})});message('Estado actualizado.');}finally{await refreshPublished();}}));}
      item.prepend(title,state,desc,img);item.append(actions);$('publishedList').append(item);
    }
  }
  $('refreshPublished').addEventListener('click',()=>perform(refreshPublished));$('statusFilter').addEventListener('change',renderPublished);
  function connection(){$('connection').textContent=navigator.onLine?'Con conexión':'Sin conexión · guarda borradores';}
  window.addEventListener('online',connection);window.addEventListener('offline',connection);connection();
  await renderDrafts();await access();await refreshPublished();
  if(configured&&'serviceWorker' in navigator){try{await navigator.serviceWorker.register(new URL('sw.js',home),{scope:home});}catch{message('No se pudo preparar el formulario para abrirlo sin conexión. Los borradores guardados permanecen en este navegador.',true);}}
})();
