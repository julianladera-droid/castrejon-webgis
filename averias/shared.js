(function (root) {
  'use strict';
  const labels = {fuga:'Fuga de agua', rotura:'Rotura', obstruccion:'Obstrucción', electrica:'Avería eléctrica', otra:'Otra',
    pendiente:'Pendiente', en_reparacion:'En reparación', resuelta:'Resuelta', normal:'Normal', alta:'Alta', urgente:'Urgente'};
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  function validate(record) {
    if (!uuid.test(record.id) || !['fuga','rotura','obstruccion','electrica','otra'].includes(record.kind) ||
        !['normal','alta','urgente'].includes(record.priority)) throw new Error('Revisa el tipo y la prioridad.');
    if (typeof record.description !== 'string' || record.description.trim().length < 5 || record.description.length > 2000 ||
        typeof record.element !== 'string' || record.element.length > 120) throw new Error('Escribe una descripción entre 5 y 2000 caracteres.');
    if (!Number.isFinite(record.longitude) || !Number.isFinite(record.latitude) || Math.abs(record.longitude)>180 || Math.abs(record.latitude)>90)
      throw new Error('Obtén la ubicación GPS o marca un punto del mapa.');
    if (!['gps','manual'].includes(record.location_source) || (record.location_source === 'gps' && (!Number.isFinite(record.accuracy_m) || record.accuracy_m < 0 || record.accuracy_m > 100000)))
      throw new Error('Revisa la ubicación y su precisión.');
    const time = Date.parse(record.observed_at);
    if (!Number.isFinite(time) || time > Date.now() + 300000 || time < Date.UTC(2000,0,1)) throw new Error('Revisa la fecha de observación.');
    return record;
  }
  function publicFeature(feature) {
    const p = feature?.properties, c = feature?.geometry?.coordinates;
    if (feature?.type !== 'Feature' || feature.geometry?.type !== 'Point' || !Array.isArray(c) || c.length !== 2 ||
        !p || feature.id !== p.id || !uuid.test(p.id) || !['pendiente','en_reparacion','resuelta'].includes(p.status) ||
        !Number.isInteger(p.version) || p.version < 1 || p.photo_path !== `incidents/${p.id}/photo`)
      throw new Error('Respuesta de averías no válida.');
    validate({...p, longitude:c[0], latitude:c[1]});
    return feature;
  }
  async function request(url, options = {}) {
    const response = await fetch(url, {...options, cache:'no-store', signal:options.signal || AbortSignal.timeout(30000)});
    if (!response.ok) {
      let message = `No se pudo completar la operación (${response.status}).`;
      try { const data = await response.json(); message = data.message || data.detail || message; } catch {}
      throw new Error(message);
    }
    return response.json();
  }
  async function list(base) {
    const features = [], ids = new Set(), cursors = new Set();
    let next = null, snapshot;
    do {
      const url = new URL('incidents', base);
      if (next) { url.searchParams.set('after', next); url.searchParams.set('as_of', snapshot); }
      const page = await request(url, {credentials:'omit'});
      if (page.type !== 'FeatureCollection' || !Array.isArray(page.features) || page.coordinate_reference_system !== 'EPSG:4326' ||
          typeof page.as_of !== 'string' || (snapshot && snapshot !== page.as_of) || page.features.length > 250)
        throw new Error('Respuesta de averías no válida.');
      snapshot = page.as_of;
      for (const f of page.features) { publicFeature(f); if (ids.has(f.id)) throw new Error('Página repetida.'); ids.add(f.id); features.push(f); }
      next = page.next;
      if (next != null && (!uuid.test(next) || cursors.has(next) || !page.features.length)) throw new Error('Paginación incorrecta.');
      cursors.add(next);
      if (next && features.length >= 10000) throw new Error('Demasiadas averías para esta vista. Solicita un filtro al administrador.');
    } while (next);
    return features;
  }
  const xml = text => String(text ?? '').replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g,'').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[char]));
  function crc32(bytes) {
    let crc = -1;
    for (const byte of bytes) { crc ^= byte; for (let b=0; b<8; b++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1)); }
    return (crc ^ -1) >>> 0;
  }
  // ZIP STORE: two small files, UTF-8 names, CRC-32. No external scripts needed offline.
  function zip(files) {
    const chunks=[], directory=[]; let offset=0;
    const bytes=(size)=>{const data=new Uint8Array(size);return [data,new DataView(data.buffer)];};
    for (const [name, data] of files) {
      const filename=new TextEncoder().encode(name), crc=crc32(data), [local,l]=bytes(30);
      l.setUint32(0,0x04034b50,true); l.setUint16(4,20,true); l.setUint16(6,0x800,true); l.setUint16(12,33,true);
      l.setUint32(14,crc,true); l.setUint32(18,data.length,true); l.setUint32(22,data.length,true); l.setUint16(26,filename.length,true);
      const [central,c]=bytes(46); c.setUint32(0,0x02014b50,true); c.setUint16(4,20,true); c.setUint16(6,20,true);
      c.setUint16(8,0x800,true); c.setUint16(14,33,true); c.setUint32(16,crc,true); c.setUint32(20,data.length,true);
      c.setUint32(24,data.length,true); c.setUint16(28,filename.length,true); c.setUint32(42,offset,true);
      chunks.push(local,filename,data); directory.push(central,filename); offset+=30+filename.length+data.length;
    }
    const length=directory.reduce((sum,x)=>sum+x.length,0), [end,e]=bytes(22);
    e.setUint32(0,0x06054b50,true); e.setUint16(8,files.length,true); e.setUint16(10,files.length,true);
    e.setUint32(12,length,true); e.setUint32(16,offset,true);
    return new Blob([...chunks,...directory,end],{type:'application/vnd.google-earth.kmz'});
  }
  async function kmz(record, photo) {
    validate(record);
    if (!(photo instanceof Blob) || !photo.size) throw new Error('Falta la fotografía.');
    const keys=['id','kind','element','description','priority','status','observed_at','location_source','accuracy_m'];
    const description=`<p>${xml(record.description)}</p><p>${xml(labels[record.status] || 'Borrador sin publicar')}</p><img src="files/foto.jpg" width="600" alt="Foto de la avería">`;
    const kml=`<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>${xml(labels[record.kind])} · ${xml(record.id)}</name><description>${xml(description)}</description><ExtendedData>${keys.map(key=>`<Data name="${key}"><value>${xml(record[key])}</value></Data>`).join('')}</ExtendedData><Point><coordinates>${record.longitude},${record.latitude},0</coordinates></Point></Placemark></Document></kml>`;
    return zip([['doc.kml',new TextEncoder().encode(kml)],['files/foto.jpg',new Uint8Array(await photo.arrayBuffer())]]);
  }
  function download(blob, name) {
    const url=URL.createObjectURL(blob), link=document.createElement('a'); link.href=url; link.download=name;
    document.body.append(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),60000);
  }
  async function photoFromFile(file) {
    if (!file || file.size > 25000000 || !/^image\/(jpeg|png|webp)$/.test(file.type)) throw new Error('Usa una foto JPEG, PNG o WebP de menos de 25 MB.');
    const bitmap=await createImageBitmap(file, {imageOrientation:'from-image'});
    try {
      if (bitmap.width*bitmap.height > 50000000) throw new Error('La fotografía tiene demasiados píxeles.');
      const scale=Math.min(1,1600/Math.max(bitmap.width,bitmap.height)), canvas=document.createElement('canvas');
      canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));
      const context=canvas.getContext('2d'); context.fillStyle='white';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(bitmap,0,0,canvas.width,canvas.height);
      const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.82));
      if (!blob || blob.size > 2000000) throw new Error('Reduce el tamaño de la foto.');
      return blob;
    } finally { bitmap.close(); }
  }
  async function base64(blob) {
    return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(blob);});
  }
  function drafts() {
    let opening;
    function open() {
      return opening ||= new Promise((resolve,reject)=>{
        const request=indexedDB.open('castrejon-averias',1);
        request.onupgradeneeded=()=>request.result.createObjectStore('drafts',{keyPath:'id'});
        request.onsuccess=()=>resolve(request.result);request.onerror=()=>{opening=null;reject(new Error('No se puede guardar en este navegador.'));};
      });
    }
    async function transact(mode, action) {
      const db=await open();return new Promise((resolve,reject)=>{
        const tx=db.transaction('drafts',mode), req=action(tx.objectStore('drafts'));
        tx.oncomplete=()=>resolve(req.result);tx.onerror=tx.onabort=()=>reject(new Error('No se pudo guardar. Comprueba el espacio del dispositivo.'));
      });
    }
    return {all:()=>transact('readonly',s=>s.getAll()), get:id=>transact('readonly',s=>s.get(id)),
      put:record=>transact('readwrite',s=>s.put(record)), remove:id=>transact('readwrite',s=>s.delete(id))};
  }
  const api={labels,validate,publicFeature,request,list,kmz,download,photoFromFile,base64,drafts};
  if (typeof module !== 'undefined') module.exports=api; else root.CastrejonAverias=api;
})(globalThis);
