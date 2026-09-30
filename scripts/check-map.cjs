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
}
class Source extends Events {}
class XYZ extends Source {}
class TileWMS extends Source {}
class ImageWMS extends Source {}
class Layer extends Events {
  setVisible(value) { this.options.visible = value; }
  setOpacity(value) { this.options.opacity = value; }
}
class Tile extends Layer {}
class Image extends Layer {}
class View extends Events {
  getCenter() { return this.options.center; }
  getZoom() { return this.options.zoom; }
  animate(options, callback) { Object.assign(this.options, options); callback?.(); }
}
class MapView extends Events {
  constructor(options) { super(options); maps.push(this); }
  getViewport() { return new Events(); }
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
  document, window: {devicePixelRatio: 1,
    matchMedia: () => Object.assign(new Events(), {matches: false})},
  ol: {
    source: {XYZ, TileWMS, ImageWMS}, layer: {Tile, Image}, View, Map: MapView,
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
  check(map.layers.length === 3, 'Esperadas tres capas M0.2');
  const [pnoa, sigpac, catastro] = map.layers;
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
} catch (error) {
  // Sólo mensajes propios; nunca volcar código, valores ni stack que puedan incluir secretos.
  console.error(`FAIL: ${error.message}`);
  process.exitCode = 1;
}
