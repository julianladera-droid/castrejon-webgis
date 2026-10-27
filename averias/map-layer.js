(function () {
  'use strict';
  window.CastrejonIncidentLayer={init({map,closeParcel,setPanelOpen,compact}){
    const A=window.CastrejonAverias, $=id=>document.getElementById(id);
    const base='https://comregantescastrejonmd.net/wp-json/castrejon/v1/';
    const source=new ol.source.Vector(), colors={pendiente:'#ce562c',en_reparacion:'#246dae',resuelta:'#357c45'}, styles={};
    for(const [status,color] of Object.entries(colors))styles[status]=new ol.style.Style({image:new ol.style.Circle({radius:9,fill:new ol.style.Fill({color}),stroke:new ol.style.Stroke({color:'#fff',width:3})})});
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
