# castrejon-webgis

Visor de control de la **C.R. Canal de Castrejón Margen Derecha**.

## Estado
M0.2 — visor cartográfico estático para pruebas.

Capas actuales:
- PNOA Máxima Actualidad (IGN/CNIG), XYZ/TMS.
- Recintos SIGPAC (FEGA/MAPA), WMS.
- Catastro INSPIRE, límites de parcela.

## Arquitectura de esta fase
GitHub Pages sirve únicamente el frontend estático. WordPress actúa como portal y enlaza al visor. Los servicios cartográficos se consumen directamente desde sus proveedores oficiales.

No contiene todavía cartografía interna, datos personales, telemetría ni simulaciones.

## CRS
- EPSG:25830: CRS maestro técnico de datos internos futuros.
- EPSG:3857: visualización web.
- EPSG:4326: coordenadas e intercambio.

## Desarrollo
En esta fase `index.html` es autocontenido salvo OpenLayers y los servicios cartográficos externos. La evolución futura prevista es React + TypeScript + OpenLayers con API FastAPI y PostgreSQL/PostGIS.

## Despliegue con GitHub Pages
El workflow `.github/workflows/pages.yml` valida el visor y publica los archivos públicos como sitio estático.

En el repositorio de GitHub, activar una vez **Settings → Pages → Build and deployment → Source: GitHub Actions**. Después, cada push a `main` despliega automáticamente sólo si supera la puerta CI.

## Regla del proyecto
Antes de introducir cambios estructurales, consultar y actualizar `SKILL_CASTREJON_WEBGIS.md`.
## Puerta CI mínima (offline)

Requisitos de desarrollo: Python 3.12, Node 24 y Git; sin paquetes npm/pip.
Desde la raíz del repositorio:

```sh
python3 scripts/check_webgis.py
```

El gate comprueba el contenido actual de los archivos versionados (añadir los
nuevos al índice con `git add` antes de la prueba local):

- HTML básico: doctype, cierres explícitos ordenados, elementos principales,
  ids únicos, etiquetas y scripts/CSS previstos de OpenLayers.
- Sintaxis de todos los scripts inline y manejadores HTML. Inicialización del
  visor con dobles mínimos de DOM/OpenLayers, sin navegador, CDN ni peticiones.
- Las fuentes conectadas al mapa: PNOA XYZ/TMS oficial con `{-y}`, SIGPAC
  TileWMS y Catastro ImageWMS INSPIRE, sus endpoints, capas, versiones y CRS.
- Centro `[-4.371848, 39.834749]` transformado de EPSG:4326 a EPSG:3857,
  zoom `13.27` y restablecimiento mediante Inicio.
- Atribuciones de las tres fuentes, control habilitado y ocultación CSS directa
  reconocible. La ausencia de recorte, superposición u ocultación indirecta se
  comprueba manualmente.
- Patrones de secretos evidentes: claves privadas, tokens conocidos,
  credenciales en URL y asignaciones literales habituales. Sólo informa del
  archivo y categoría; no imprime el secreto. No analiza historial, secretos
  codificados ni garantiza ausencia de toda credencial.

No equivale a un validador HTML completo ni a ejecutar OpenLayers en navegador.
Si cambia el formato de scripts, la versión CDN o la API usada por el visor,
actualizar los dobles y el contrato de forma explícita; no silenciar el fallo.
El centro se verifica como transformación solicitada a OpenLayers, no como
prueba de su algoritmo geodésico. No se bloquea el desplazamiento/zoom del usuario.

En PR a `main` sólo se valida. En push a `main` o ejecución manual sobre `main`,
`deploy` requiere el éxito de `gate`; un fallo o cancelación impide Setup Pages,
empaquetado y despliegue. El checkout de ambos jobs corresponde al mismo SHA del
evento. Los PR tienen grupo de concurrencia propio y no cancelan producción.
Los permisos Pages/OIDC se conceden sólo al job de despliegue.
El artefacto público contiene únicamente `index.html` y `.nojekyll`; si se añaden
recursos locales al visor, incorporarlos explícitamente al empaquetado y al gate.

Reversión: revertir el commit de esta puerta restaura el flujo previo. No se
requiere migración ni modificación del visor. Mientras exista este workflow,
no usar `continue-on-error`, `always()` ni retirar `needs: gate` para sortearlo.
No se cambian las reglas de protección de ramas del repositorio.

## Checklist manual por cambio

Registrar SHA, fecha, navegador, tamaño de pantalla y resultado (OK/FALLO/NO
PROBADO), con evidencia o incidencia. Casillas sin marcar = pendientes, nunca
aprobadas por el mero éxito de CI. Ejecutar lo aplicable localmente antes del
push y repetir sobre Pages tras la publicación; CI no impone aprobación humana.

| Nº skill | Comprobación manual pendiente | Cobertura automática parcial |
| --- | --- | --- |
| 1 | [ ] Arranque real y consola sin errores (incluido CDN OpenLayers). | Sintaxis e inicialización con dobles. |
| 2 | [ ] PNOA carga y cubre el área piloto. | Tipo XYZ/TMS y endpoint. |
| 3 | [ ] SIGPAC Recintos carga; campaña/capa en GetCapabilities en revisiones mayores. | TileWMS y parámetros previstos. |
| 4 | [ ] Catastro INSPIRE carga sólo al activarlo. | ImageWMS y parámetros previstos. |
| 5 | [ ] Centro y encuadre iniciales correctos, zoom 13,27. | Centro, transformación solicitada y zoom. |
| 6 | [ ] Zoom +/− funciona. | — |
| 7 | [ ] Inicio restaura el encuadre con animación correcta. | Manejador restaura centro/zoom con dobles. |
| 8 | [ ] Atrás/adelante sin bucles ni entradas falsas al cambiar capas. | — |
| 9 | [ ] Activación/desactivación de las tres capas. | — |
| 10 | [ ] Opacidades SIGPAC/Catastro y sus indicadores coherentes. | — |
| 11 | [ ] Coordenadas del cursor en EPSG:4326. | — |
| 12 | [ ] Escala gráfica dinámica coherente. | — |
| 13 | [ ] Responsive móvil: paneles y controles sin solapes. | — |
| 14 | [ ] Teclado, foco visible y acceso a controles. | — |
| 15 | [ ] Fallo de servicio: mensaje comprensible y no bloqueante. | — |
| 16 | [ ] Error aislado de tesela tras cargas válidas no deja servicio caído. | — |
| 17 | [ ] Red del navegador: PNOA usa teselas, sin GetMap durante zoom. | Fuente XYZ/TMS efectiva. |
| 18 | [ ] Continuidad de teselas en transición y precarga sin saturación. | — |
| 19 | [ ] Red: Catastro usa imagen WMS completa, sin mosaico teselado. | Fuente ImageWMS INSPIRE efectiva. |
| 20 | [ ] Atribuciones legibles con cada capa activa, sin recortes ni ocultación, en escritorio/móvil. | Textos/control y ocultación CSS directa. |

Tras publicar: [ ] enlace WordPress → Pages; [ ] CORS/CSP desde origen remoto;
[ ] pantalla completa. Las incidencias remotas se registran como tales y no se
convierten en pruebas CI inestables.

## Adaptación móvil (0.1.6)

SIGPAC queda definitivamente en **0,33**, según decisión del usuario; Catastro
mantiene **0,62**. Los sliders usan paso 0,01 y el gate comprueba su coherencia
con la capa, además de la opacidad inicial SIGPAC.

- Panel de capas plegado al entrar en un tamaño compacto; se abre pulsando
  «Capas del mapa», se desplaza internamente si falta altura y se cierra con
  el mismo botón o Escape. Comunica su estado mediante `aria-expanded`.
- Navegación táctil inferior, botones de al menos 44 px y foco visible.
- Altura dinámica del navegador y márgenes de áreas seguras. Se conserva el
  encuadre cuando cambia el tamaño del mapa.
- Pie propio para coordenadas, escala gráfica y atribuciones siempre
  expandidas; los paneles no cubren esta franja.
- En móvil, la cruz central señala las coordenadas del centro; en escritorio
  se muestran las del cursor. Las lecturas siguen en EPSG:4326.
- Pantalla completa sólo aparece si el navegador la admite; un rechazo muestra
  un aviso y las animaciones respetan la preferencia de movimiento reducido.

Verificación manual adicional: 320×568, 390×844, móvil horizontal, escritorio,
abrir/cerrar/desplazar panel, cambiar orientación con el panel abierto, sliders
33/62 %, atribuciones con Catastro activo y navegador con barras visibles.
La simulación de tamaños no sustituye la prueba en un dispositivo físico.


## Seguridad de red y diagnóstico (0.1.7)

El visor no necesita acceso a la red local del usuario. El código y el gate prohíben
`localhost`, IP privadas/loopback/link-local, dominios `.local`,
`targetAddressSpace` y HTTP no seguro. La CSP limita las conexiones del M0.2 a
OpenLayers/jsDelivr y a los servicios HTTPS oficiales de PNOA, SIGPAC y Catastro.

Los WMS no fuerzan `crossOrigin: anonymous`: M0.2 no exporta el canvas ni lee
píxeles, y exigir CORS sin necesidad puede provocar errores de carga en servicios
cartográficos que no publiquen cabeceras CORS compatibles.

Prueba manual de seguridad:
1. Abrir Pages en una ventana privada de Chrome.
2. Si Chrome pregunta por acceso a dispositivos/red local, elegir **No permitir**.
3. El visor debe seguir funcionando sin ese permiso.
4. En DevTools > Network, los únicos hosts remotos esperados son
   `cdn.jsdelivr.net`, `tms-pnoa-ma.idee.es`, `sigpac-hubcloud.es` y
   `ovc.catastro.meh.es`.
5. Si vuelve a aparecer el aviso, guardar captura del permiso y de la petición que
   coincide en ese instante; no conceder el permiso para diagnosticarla.
