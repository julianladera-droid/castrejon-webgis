(function () {
  'use strict';
  window.CastrejonIncidentLayer={init({map,closeParcel,setPanelOpen,compact}){
    const A=window.CastrejonAverias, $=id=>document.getElementById(id);
    const base='https://comregantescastrejonmd.net/wp-json/castrejon/v1/';
    const source=new ol.source.Vector(), colors={pendiente:['#ce562c','#f2c7b7'],en_reparacion:['#246dae','#c7ddee'],resuelta:['#357c45','#cbe2ce']}, styles={};
    // One small, cached vector icon per state; no external image requests.
    const iconSvg=(edge,fill)=>`<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
      <path d="M28.5 7.5Q32 1.5 35.5 7.5L60 51Q64 58 56 58H8Q0 58 4 51Z" fill="${fill}" stroke="white" stroke-width="5" stroke-linejoin="round"/>
      <path d="M28.5 7.5Q32 1.5 35.5 7.5L60 51Q64 58 56 58H8Q0 58 4 51Z" fill="${fill}" stroke="${edge}" stroke-width="3" stroke-linejoin="round"/>
      <g transform="translate(9.6 17) scale(.7)"><g fill="#344955" stroke="white" stroke-width="1.4" stroke-linejoin="round">
        <path d="M18 28L22 24L47 49Q49 52 46 54Q44 55 42 53Z"/>
        <path d="M12 40Q13 23 36 21Q27 25 23 31L19 33Q15 35 12 40Z"/>
        <path d="M18 49L39 28L37 25L43 19Q47 16 51 20L54 23L51 29L48 27L49 24L46 23L43 26L46 29L43 34L40 33L24 54Q21 56 18 53Z"/>
      </g>
      <path d="M40 29L45 33M41 28L46 32" stroke="white" stroke-width="1"/></g>
    </svg>`;
    for(const [status,[edge,fill]] of Object.entries(colors)){
      const src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(iconSvg(edge,fill));
      styles[status]=new ol.style.Style({image:new ol.style.Icon({src,width:24,height:24,anchor:[.5,.5]})});
      const key=$('incidentKey-'+status);
      if(key)key.style.backgroundImage=`url("${src}")`;
    }
    const layer=new ol.layer.Vector({source,zIndex:40,style:feature=>styles[feature.get('status')]});map.addLayer(layer);
    let items=[],selected=null,loading=false,refreshId=0;
    const card=$('incidentCard');
    function close(){if(card.contains(document.activeElement))$('map').focus({preventScroll:true});card.hidden=true;selected=null;map.updateSize();}
    function show(feature){
      closeParcel();selected=feature;const p=feature.getProperties();
      $('incidentTitle').textContent=`${A.labels[p.kind]} · ${p.id.slice(0,8)}`;
      $('incidentState').textContent=A.labels[p.status];$('incidentState').className=`incident-state ${p.status}`;
      $('incidentDescription').textContent=p.description;
      $('incidentDetails').replaceChildren();
      const date=value=>value?new Date(value).toLocaleString('es-ES'):'—';
      for(const [label,value] of [['Prioridad',A.labels[p.priority]],['Elemento',p.element||'Sin referencia'],['Observada',date(p.observed_at)],['Actualizada',date(p.updated_at)],['Cierre',date(p.closed_at)],['Ubicación',p.location_source==='gps'?`GPS · ±${Math.round(p.accuracy_m)} m`:'Marcada manualmente']]){
        const div=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;div.append(dt,dd);$('incidentDetails').append(div);
      }
      $('incidentPhotoError').hidden=true;$('incidentPhoto').hidden=false;$('incidentPhoto').src=new URL(p.photo_path,base);
      card.hidden=false;card.scrollTop=0;if(compact.matches){setPanelOpen(false);$('navMore').open=false;}map.updateSize();
    }
    $('incidentPhoto').addEventListener('error',()=>{$('incidentPhoto').hidden=true;$('incidentPhotoError').hidden=false;});
    $('incidentPhotoRetry').addEventListener('click',()=>{if(selected)show(selected);});
    $('incidentClose').addEventListener('click',close);
    $('appShell').addEventListener('keydown',event=>{if(event.key==='Escape'&&!card.hidden)close();});
    function render(){
      close();source.clear();$('incidentList').replaceChildren();
      const visible=items.filter(f=>!$('incidentFilter').value||f.properties.status===$('incidentFilter').value);
      const features=new ol.format.GeoJSON().readFeatures({type:'FeatureCollection',features:visible},{dataProjection:'EPSG:4326',featureProjection:'EPSG:3857'});
      source.addFeatures(features);
      for(const feature of features){const p=feature.getProperties(),button=document.createElement('button');button.type='button';button.className='incident-list-item';button.textContent=`${A.labels[p.status]} · ${A.labels[p.kind]} · ${p.element||p.id.slice(0,8)}`;
        button.addEventListener('click',()=>{layer.setVisible(true);$('incidentToggle').checked=true;map.getView().animate({center:feature.getGeometry().getCoordinates(),zoom:17,duration:300});show(feature);});$('incidentList').append(button);}
      $('incidentCount').textContent=String(visible.length);
    }
    async function refresh(){
      if(loading)return;loading=true;const id=++refreshId;$('incidentRefresh').disabled=true;$('incidentStatus').textContent='Consultando averías…';
      try{const result=await A.list(base);if(id!==refreshId)return;items=result;render();$('incidentStatus').textContent=items.length?`${items.length} averías · actualizado ${new Date().toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit'})}`:'No hay averías publicadas.';}
      catch{if(id!==refreshId)return;items=[];render();$('incidentStatus').textContent='Averías no disponibles. Comprueba que el servicio de WordPress está activo y pulsa Actualizar.';}
      finally{loading=false;$('incidentRefresh').disabled=false;}
    }
    $('incidentToggle').addEventListener('change',()=>{layer.setVisible($('incidentToggle').checked);if(!layer.getVisible())close();});
    $('incidentFilter').addEventListener('change',render);$('incidentRefresh').addEventListener('click',refresh);
    $('incidentKmz').addEventListener('click',async()=>{
      if(!selected)return;const feature=selected,p=feature.getProperties();$('incidentKmz').disabled=true;
      try{const response=await fetch(new URL(p.photo_path,base),{credentials:'omit',signal:AbortSignal.timeout(30000)});if(!response.ok)throw new Error();const [longitude,latitude]=ol.proj.toLonLat(feature.getGeometry().getCoordinates());A.download(await A.kmz({...p,longitude,latitude},await response.blob()),`averia-${p.id}.kmz`);}
      catch{$('incidentPhotoError').hidden=false;}
      finally{$('incidentKmz').disabled=false;}
    });
    refresh();
    return {selectAtPixel(pixel){if(!layer.getVisible()){close();return false;}const feature=map.forEachFeatureAtPixel(pixel,f=>f,{layerFilter:candidate=>candidate===layer,hitTolerance:10});if(feature){show(feature);return true;}close();return false;},close};
  }};
})();
