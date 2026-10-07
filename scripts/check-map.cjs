'use strict';
// Dobles mínimos de DOM/OpenLayers: comprueban configuración, no renderizado.
// vm NO es una frontera de seguridad: se ejecuta código del repositorio en el job
// de sólo lectura, sin secretos. No se ofrece fetch, process ni require al visor.
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const check = (ok, message) => { if (!ok) throw new Error(message); };
const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const maps = [];
class Events {
  constructor(options = {}) { this.options = options; this.events = {}; }
  on(name, callback) { (this.events[name] ??= []).push(callback); }
  once(name, callback) { this.on(name, callback); }
  addEventListener(name, callback) { this.on(name, callback); }
  setGeometry(geometry) { this.options.geometry = geometry; }
}
class Source extends Events {}
class XYZ extends Source {}
class TileWMS extends Source {}
class ImageWMS extends Source {}
class VectorSource extends Source {}
const geoJSONReads = [];
class GeoJSON {
  readFeatures(data, options) {
    geoJSONReads.push({data, options});
    return data.features;
  }
}
class Layer extends Events {
  getVisible() { return this.options.visible ?? true; }
  getOpacity() { return this.options.opacity ?? 1; }
  setVisible(value) { this.options.visible = value; this.events['change:visible']?.forEach(fn => fn()); }
  setOpacity(value) { this.options.opacity = value; this.events['change:opacity']?.forEach(fn => fn()); }
}
class Tile extends Layer {}
class Image extends Layer {}
class VectorLayer extends Layer {}
class View extends Events {
  getCenter() { return this.options.center; }
  getZoom() { return this.options.zoom; }
  calculateExtent() { return [0, 0, 1280, 720]; }
  animate(options, callback) { Object.assign(this.options, options); callback?.(); }
}
class MapView extends Events {
  constructor(options) { super(options); maps.push(this); }
  getViewport() { return new Events(); }
  getSize() { return [1280, 720]; }
  getView() { return this.options.view; }
  updateSize() {}
}
const elements = Object.fromEntries(Object.entries(input.ids).map(([id, attrs]) => {
  const element = new Events();
  const classes = new Set();
  Object.assign(element, {style: {}, value: attrs.value, checked: 'checked' in attrs,
    classList: {toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); },
      contains(name) { return classes.has(name); }},
    setAttribute(name, value) { attrs[name] = value; },
    contains() { return false; }, focus() {}});
  return [id, element];
}));
const document = {
  addEventListener() {},
  fullscreenEnabled: false,
  getElementById(id) { check(elements[id], 'DOM: id solicitado inexistente'); return elements[id]; },
  querySelector() { throw new Error('DOM: selector nuevo; adaptar el doble de prueba'); }
};
// Marcador de transformación, no implementación geodésica ni de OpenLayers.
const fromLonLat = (coords, target = 'EPSG:3857') => ({from: 'EPSG:4326', to: target, coords});
const homeCenter = fromLonLat([-4.371848, 39.834749]);
const context = vm.createContext({
  fetch: () => new Promise(() => {}),
  document, window: {devicePixelRatio: 1,
    addEventListener() {},
    matchMedia: () => Object.assign(new Events(), {matches: false})},
  ol: {
    source: {XYZ, TileWMS, ImageWMS, Vector: VectorSource},
    layer: {Tile, Image, Vector: VectorLayer}, View, Map: MapView,
    format: {GeoJSON}, style: {Style: Events, Stroke: Events, Fill: Events, RegularShape: Events},
    geom: {MultiPoint: class {constructor(coordinates) {this.coordinates=coordinates;}}},
    proj: {fromLonLat, toLonLat: point => point.coords},
    control: {
      defaults: {defaults: options => ({extend: controls => ({options, controls})})},
      ScaleLine: class extends Events {}
    },
    interaction: {defaults: {defaults: options => options}}
  }
});
try {
  // Compilar todo antes de ejecutar, incluidos manejadores HTML si se incorporan.
  let scripts;
  try {
    scripts = input.scripts.map((code, i) => new vm.Script(code, {filename: `inline-${i + 1}.js`}));
    input.handlers.forEach(code => new vm.Script(`(function(event){${code}\n})`));
  } catch {
    throw new Error('Sintaxis JavaScript inválida (inline o atributo de evento)');
  }
  check(scripts.length > 0, 'Falta JavaScript inline del visor');
  try { scripts.forEach(script => script.runInContext(context, {timeout: 1000})); }
  catch { throw new Error('Inicialización offline inválida; revisar JS/ids o actualizar dobles si cambia la API'); }
  console.log('OK: sintaxis JavaScript e inicialización con dobles locales');
  check(maps.length === 1, 'Debe crearse un único mapa');
  const map = maps[0].options;
  check(map.target === 'map', 'Destino del mapa incorrecto');
  check(map.layers.length === 5, 'Esperadas capas base, Sentinel y Zona regable');
  const [pnoa, sentinel, sigpac, catastro, zonaRegable] = map.layers;
  check(sentinel instanceof Image && !sentinel.getVisible() && sentinel.options.properties.id === 'sentinel',
    'Sentinel: oculto hasta elegir un producto disponible');
  check(zonaRegable instanceof VectorLayer && zonaRegable.options.source instanceof VectorSource &&
    zonaRegable.options.properties.id === 'zonaRegable', 'Zona regable: tipo/identidad incorrectos');
  check(geoJSONReads.length === 1 && equal(geoJSONReads[0].options,
    {dataProjection:'EPSG:4326', featureProjection:'EPSG:3857'}), 'Zona regable: declarar reproyección 4326 a 3857');
  const reference = geoJSONReads[0].data;
  check(reference.type === 'FeatureCollection' && reference.features.length === 1 &&
    reference.features[0].id === 'ZR.0' && reference.features[0].geometry.type === 'Polygon' &&
    reference.features[0].properties.status === 'pending_adjustment', 'Zona regable: referencia incompleta');
  const ring = reference.features[0].geometry.coordinates[0];
  check(ring.length >= 4 && equal(ring[0], ring.at(-1)) &&
    ring.every(([lon, lat]) => lon > -4.49 && lon < -4.30 && lat > 39.79 && lat < 39.87),
    'Zona regable: anillo cerrado y coordenadas lon/lat de Castrejón');
  check(typeof zonaRegable.options.style === 'function', 'Zona regable: estilo adaptativo obligatorio');
  const testFeature = {getGeometry:()=>({getExtent:()=>[0,0,1000,500],
    getCoordinates:()=>[[[0,0],[1000,0],[1000,500],[0,500],[0,0]]]})};
  const overview = zonaRegable.options.style(testFeature, 2);
  const detail = zonaRegable.options.style(testFeature, .01);
  check(overview[1].options.fill && !detail[1].options.fill,
    'Perímetro: superficie general y sin relleno en detalle');
  check(overview[1].options.stroke.options.color.startsWith('rgba(255,230,0,') &&
    detail[1].options.stroke.options.color.startsWith('rgba(255,230,0,'), 'Perímetro: conservar tono amarillo');
  check(detail[1].options.stroke.options.width <= 1.2 && detail[1].options.stroke.options.lineDash &&
    detail[2].options.image.options.points === 4 && detail[2].options.geometry.coordinates.length <= 500,
    'Perímetro: línea discreta, cruces y densidad acotada');
  const toggle = elements.zonaRegableToggle;
  check(toggle.checked && zonaRegable.options.visible && toggle.events.change.length === 1,
    'Zona regable: visible inicialmente y con interruptor');
  for (const checked of [false, true]) {
    toggle.events.change[0]({target:{checked}});
    check(zonaRegable.options.visible === checked, 'Zona regable: interruptor no cambia visibilidad');
  }
  console.log('OK: Zona regable, geometría incorporada, reproyección declarada y visibilidad');
  check(sigpac.options.opacity === 0.33, 'SIGPAC: opacidad inicial definitiva 0,33');
  for (const [layer, id] of [[sigpac, 'sigpacOpacity'], [catastro, 'catOpacity']]) {
    const attrs = input.ids[id];
    check(Number(attrs.value) === layer.options.opacity && attrs.step === '0.01',
      'Opacidad: valor inicial del slider y paso deben representar la opacidad real');
  }
  for (const [layer, id, LayerType, SourceType] of [
    [pnoa, 'pnoa', Tile, XYZ], [sigpac, 'sigpac', Tile, TileWMS],
    [catastro, 'catastro', Image, ImageWMS]
  ]) {
    check(layer instanceof LayerType && layer.options.source instanceof SourceType,
      `Tipo de capa/fuente incorrecto: ${id}`);
    check(layer.options.properties.id === id, `Orden/identidad de capa incorrectos: ${id}`);
    check(layer.options.source.options.projection === 'EPSG:3857', `CRS de fuente incorrecto: ${id}`);
  }
  const p = pnoa.options.source.options;
  const s = sigpac.options.source.options;
  const c = catastro.options.source.options;
  check(p.url === 'https://tms-pnoa-ma.idee.es/1.0.0/pnoa-ma/{z}/{x}/{-y}.jpeg',
    'PNOA: mantener XYZ/TMS oficial con Y invertida');
  check(p.tileSize === 256 && p.maxZoom === 19, 'PNOA: pirámide 256px hasta nivel 19');
  for (const [source, id] of [[p, 'PNOA'], [s, 'SIGPAC'], [c, 'Catastro']]) {
    check(!Object.prototype.hasOwnProperty.call(source, 'crossOrigin'),
      `${id}: no forzar crossOrigin/CORS en M0.2`);
  }
  check(s.url === 'https://sigpac-hubcloud.es/wms' &&
    s.params.LAYERS === 'AU.Sigpac:recinto' && s.params.VERSION === '1.3.0',
    'SIGPAC: endpoint/capa/versión incorrectos');
  check(c.url === 'https://ovc.catastro.meh.es/cartografia/INSPIRE/spadgcwms.aspx' &&
    c.params.LAYERS === 'CP.CadastralParcel' &&
    c.params.STYLES === 'CP.CadastralParcel.BoundariesOnly' && c.params.VERSION === '1.1.1' &&
    c.params.TILED !== true && c.params.TILED !== 'true', 'Catastro: contrato ImageWMS INSPIRE incorrecto');
  for (const source of [s, c]) {
    check(source.params.FORMAT === 'image/png' && source.params.TRANSPARENT === true,
      'WMS: se requiere PNG transparente');
  }
  console.log('OK: PNOA XYZ/TMS, SIGPAC TileWMS y Catastro ImageWMS/INSPIRE');
  const view = map.view;
  check(view instanceof View && view.options.projection === 'EPSG:3857', 'View debe usar EPSG:3857');
  check(equal(view.getCenter(), homeCenter) && view.getZoom() === 13.27,
    'Centro/zoom inicial bloqueados o transformación 4326 → 3857 incorrecta');
  check(elements.homeBtn?.events.click?.length === 1, 'Inicio: falta manejador único');
  view.options.center = [0, 0];
  view.options.zoom = 6;
  context.__home = () => elements.homeBtn.events.click[0]();
  try { vm.runInContext('__home()', context, {timeout: 1000}); }
  catch { throw new Error('Inicio: error al ejecutar el manejador'); }
  check(equal(view.getCenter(), homeCenter) && view.getZoom() === 13.27,
    'Inicio no restaura centro transformado y zoom bloqueados');
  console.log('OK: centro/zoom iniciales y acción Inicio');
  for (const [source, words] of [[p, ['PNOA', 'IGN', 'CNIG']],
    [s, ['SIGPAC', 'FEGA', 'MAPA', 'CC BY 4.0']], [c, ['Dirección General del Catastro', 'INSPIRE']]]) {
    check(typeof source.attributions === 'string' && words.every(word => source.attributions.includes(word)),
      'Falta atribución contractual de una fuente');
  }
  check(map.controls?.options.attribution === true, 'Control de atribuciones desactivado');
  check(map.controls.options.attributionOptions?.collapsible === false &&
    map.controls.options.attributionOptions?.target === 'attributionTarget',
    'Atribuciones: mantener expandidas en el pie dedicado');
  console.log('OK: atribuciones configuradas y control habilitado (visibilidad real: manual)');
  check(!elements.legendZona.hidden && !elements.legendSigpac.hidden &&
    elements.legendCatastro.hidden && !elements.legendPnoa.hidden && elements.legendEmpty.hidden,
    'Leyenda: estado inicial incorrecto');
  for (const [layer, toggleId, legendId] of [
    [zonaRegable, 'zonaRegableToggle', 'legendZona'], [pnoa, 'pnoaToggle', 'legendPnoa'],
    [sigpac, 'sigpacToggle', 'legendSigpac'], [catastro, 'catToggle', 'legendCatastro']
  ]) {
    for (const checked of [true, false]) {
      elements[toggleId].events.change[0]({target:{checked}});
      check(elements[legendId].hidden === !checked, 'Leyenda: no sigue el interruptor');
    }
  }
  check(!elements.legendEmpty.hidden, 'Leyenda: falta estado sin capas');
  for (const [layer, sliderId, legendId] of [[sigpac, 'sigpacOpacity', 'legendSigpac'],
    [catastro, 'catOpacity', 'legendCatastro']]) {
    layer.setVisible(true);
    for (const value of [0, 0.5]) {
      elements[sliderId].events.input[0]({target:{value:String(value)}});
      check(elements[legendId].hidden === (value === 0), 'Leyenda: no sigue opacidad cero/restauración');
    }
    layer.setVisible(false);
  }
  console.log('OK: leyenda dinámica, interruptores, opacidad cero y estado vacío');
} catch (error) {
  // Sólo mensajes propios; nunca volcar código, valores ni stack que puedan incluir secretos.
  console.error(`FAIL: ${error.message}`);
  process.exitCode = 1;
}
