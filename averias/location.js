(function(root){
  'use strict';
  const policy=typeof module!=='undefined'?require('./location-policy.js'):root.CastrejonLocationPolicy;
  function validateLocation(value){
    for(const [key,max] of [['longitude',180],['latitude',90]])
      if(!Number.isFinite(value?.[key]) || Math.abs(value[key])>max)
        throw new Error('Coordenadas imposibles. Usa longitud y latitud WGS 84 en grados decimales.');
    if(!['gps','manual'].includes(value.location_source) || (value.location_source==='gps' &&
      (!Number.isFinite(value.accuracy_m)||value.accuracy_m<0||value.accuracy_m>100000)))
      throw new Error('Revisa la ubicación y su precisión.');
    return value;
  }
  function manualLocation(latitude,longitude){
    function decimal(text){
      if(typeof text!=='string'||!/^[-+]?(?:\d+(?:[.,]\d+)?|[.,]\d+)$/.test(text.trim()))
        throw new Error('Introduce latitud y longitud en grados decimales, con coma o punto y sin separador de miles.');
      return Number(text.trim().replace(',','.'));
    }
    return validateLocation({latitude:decimal(latitude),longitude:decimal(longitude),location_source:'manual',accuracy_m:null});
  }
  // Angular containment only. No distance, area, parcel link or geographic permission.
  function inRing(x,y,ring){
    let inside=false;
    for(let i=0,j=ring.length-1;i<ring.length;j=i++){
      const [ax,ay]=ring[j],[bx,by]=ring[i];
      if(Math.abs((x-ax)*(by-ay)-(y-ay)*(bx-ax))<=1e-12 &&
        x>=Math.min(ax,bx)-1e-12&&x<=Math.max(ax,bx)+1e-12&&y>=Math.min(ay,by)-1e-12&&y<=Math.max(ay,by)+1e-12)return {inside:true,boundary:true};
      if((ay>y)!==(by>y)&&x<(bx-ax)*(y-ay)/(by-ay)+ax)inside=!inside;
    }
    return {inside,boundary:false};
  }
  function inReference(x,y){
    const rings=policy.geometry.coordinates,outer=inRing(x,y,rings[0]);
    if(outer.boundary)return true;
    if(!outer.inside)return false;
    for(const hole of rings.slice(1)){const hit=inRing(x,y,hole);if(hit.boundary)return true;if(hit.inside)return false;}
    return true;
  }
  function inEnvelope(x,y){const [w,s,e,n]=policy.bbox,m=policy.far_margin_degrees;return x>=w-m&&x<=e+m&&y>=s-m&&y<=n+m;}
  function locationQuality(value){
    validateLocation(value);
    const x=value.longitude,y=value.latitude,warnings=[];
    let severity='ok',status='inside_reference';
    const add=(code,message)=>warnings.push({code,message});
    if(!inEnvelope(x,y)){
      status='far_from_reference';severity='danger';
      add('far_from_reference','Punto muy alejado del ámbito de referencia de Castrejón. Revisa el GPS, los ejes y el signo de las coordenadas antes de publicar.');
      if(inEnvelope(y,x))add('possible_axis_swap','Posible intercambio de latitud y longitud. No se han corregido automáticamente.');
      if(inEnvelope(-x,y))add('possible_longitude_sign','Posible signo incorrecto de la longitud. En Castrejón la longitud es negativa.');
    }else if(!inReference(x,y)){
      status='outside_reference';severity='warning';
      add('outside_reference','Punto fuera del perímetro regable de referencia, pendiente de ajuste. Puede corresponder a una infraestructura del canal: comprueba el lugar y confirma si es correcto.');
    }
    if(value.location_source==='manual'){
      if(severity==='ok')severity='notice';
      add('manual_location','Ubicación manual, sin precisión GPS. Comprueba el punto del mapa y las coordenadas.');
    }else if(value.accuracy_m===0||value.accuracy_m>policy.gps_warning_m){
      if(severity!=='danger')severity='warning';
      add(value.accuracy_m===0?'gps_accuracy_unknown':'gps_low_accuracy',value.accuracy_m===0?
        'El GPS informa de precisión cero; no se considera una posición exacta. Repite el GPS o sitúa el punto manualmente.':
        `Precisión GPS insuficiente (±${Math.round(value.accuracy_m)} m; aviso por encima de ${policy.gps_warning_m} m). Repite el GPS a cielo abierto o corrige el punto manualmente.`);
    }
    return {policy_version:policy.version,reference_status:policy.status,status,severity,warnings};
  }
  function publicationPrompt(record,quality=locationQuality(record)){
    return [`Ubicación a publicar: latitud ${record.latitude}, longitud ${record.longitude}.`,
      ...quality.warnings.map(w=>'• '+w.message),
      quality.warnings.length?'Confirma que has revisado esta ubicación. Los avisos territoriales son orientativos.':'',
      'Se publicarán la ubicación, la foto y los datos para cualquier visitante. ¿Publicar?'].filter(Boolean).join('\n\n');
  }
  const api={validateLocation,manualLocation,locationQuality,publicationPrompt};
  if(typeof module!=='undefined')module.exports=api;else root.CastrejonLocation=api;
})(globalThis);
