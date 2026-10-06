# castrejon-webgis

Visor de control de la **C.R. Canal de Castrejón Margen Derecha**.

## Estado
M0.2 + M4 — visor cartográfico con índices Sentinel y publicación automática.

Capas actuales:
- PNOA Máxima Actualidad (IGN/CNIG), XYZ/TMS.
- Recintos SIGPAC (FEGA/MAPA), WMS.
- Catastro INSPIRE, límites de parcela.
- Zona regable: perímetro de referencia aportado en `ZR.gml`, pendiente de ajuste.

## Arquitectura de esta fase
GitHub Pages sirve únicamente el frontend estático. WordPress actúa como portal y enlaza al visor. Los servicios cartográficos se consumen directamente desde sus proveedores oficiales.

Incluye el perímetro de referencia; no contiene parcelas internas, datos personales, telemetría ni simulaciones.

## Perímetro y área Sentinel (M4)

El contorno azul de «Zona regable» está visible inicialmente y se puede ocultar.
Se incorpora al HTML sin nuevas peticiones. Se conserva el encuadre de Inicio.
La geometría original permanece en EPSG:25830; su copia de visualización pasa
a EPSG:4326 y OpenLayers la representa en EPSG:3857.

`ZR.gml` contiene un polígono válido de **2.416,93 ha**, pendiente de ajuste.
`data/sentinel-aoi.json` separa ese perímetro del rectángulo envolvente para
procesamiento: **9.521,73 ha** en EPSG:25830. Esta última cifra no es superficie
regable. El archivo incluye una bbox conservadora en EPSG:4326 para buscar
Sentinel-2 L2A y un borrador de consulta STAC, aún sin periodo seleccionado.
La bbox filtra el catálogo; descargar un asset completo puede incluir toda
la tesela. El futuro recorte/procesamiento usará el rectángulo, ajustando la
rejilla hacia fuera según la resolución, y mantendrá el perímetro separado.
Primera descarga Sentinel completada y verificada el 6 de octubre de 2026.

Regeneración reproducible, con Python de QGIS y GDAL/OGR instalados:

```sh
python scripts/prepare_reference.py /ruta/ZR.gml
```

El script valida CRS y geometría, registra el SHA-256 del original y actualiza
el contorno incorporado y los metadatos del área. No repara ni modifica el GML.
Los archivos técnicos no forman parte del paquete Pages; la capa sí va dentro
de `index.html`. El flujo Pages publica estos cambios junto con los índices Sentinel.

## Índices en el visor (M4)

En «Capas del mapa → Sentinel», elegir NDVI, EVI2 o NDMI. «Sin índice» permite
volver a la cartografía habitual. Se ofrece la última adquisición válida, su fecha
real, antigüedad y porcentaje válido del rectángulo; no se presenta como imagen
en tiempo real. El selector admite sólo fechas publicadas (actualmente una).
La opacidad controla la superposición y la leyenda se oculta al llegar a cero.
Las zonas sin calidad suficiente son transparentes.

Las escalas de color son fijas: NDVI y NDMI de -1 a 1, EVI2 de 0 a 1. EVI2 fuera
de ese rango satura el color, pero conserva sus valores en el GeoTIFF técnico.
NDMI representa una estimación relacionada con humedad de la vegetación, no
una medida directa de humedad del suelo. No son estadísticas por parcela.

Pages genera PNG RGBA EPSG:3857 a partir de los GeoTIFF EPSG:25830 validados.
El navegador sólo solicita la imagen del índice elegido y el catálogo al mismo
origen; los GeoTIFF originales se descargan bajo demanda. No se consulta a
Copernicus desde el navegador. Los artefactos no se ejecutan como código.

El despliegue se activa con cambios de main o al terminar Sentinel correctamente.
Selecciona un artefacto no caducado de sentinel.yml/main del mismo repositorio,
comprueba SHA-256, CRS, rejilla y calidad antes de reemplazar la publicación.
Si falla, el sitio anterior se conserva. Se publica la última adquisición válida;
esta fase no mantiene un archivo histórico permanente. La imagen ya publicada
sigue disponible aunque caduque el artefacto, hasta el siguiente despliegue.

Pruebas de publicación: `python scripts/test_sentinel_web.py` (GDAL/NumPy) y
`node scripts/test-sentinel-ui.cjs`, además del gate cartográfico existente.

## CRS
- EPSG:25830: CRS maestro técnico de datos internos futuros.
- EPSG:3857: visualización web.
- EPSG:4326: coordenadas e intercambio.

## Desarrollo
### Descarga automática Sentinel desde GitHub

`.github/workflows/sentinel.yml` busca productos **Sentinel-2 L2A ya disponibles**
en Copernicus **cada tres días de febrero a septiembre**, ambos inclusive,
contando desde el 1 de febrero sin reiniciar la cuenta al cambiar de mes.
En **enero, octubre, noviembre y diciembre se ejecuta el día 15**.
Hora: 05:30 UTC (07:30 en Madrid en verano, 06:30 en invierno).
GitHub comprueba el calendario diariamente durante la temporada, pero los días
intermedios no consulta ni descarga nada de Copernicus. También permite ejecución
manual en Actions. No depende de una sesión de navegador.
Busca en los últimos 30 días una adquisición con cobertura completa del rectángulo
y nubosidad de tesela <=20%. Después exige al menos 80% de píxeles válidos dentro
del rectángulo para cada índice. Son umbrales iniciales revisables, no garantías
de ausencia de nubes; SCL puede contener errores.

Se leen por S3 las bandas necesarias del producto L2A y se recortan con GDAL.
Los JP2 originales pueden requerir transferir más datos que el recorte final.
La reflectancia usa escala y offset de cada asset STAC, excluyendo nodata.
La máscara conservadora admite SCL 4, 5 y 6; excluye sombras, nubes, nieve,
datos inválidos y clases ambiguas. No aplica una máscara de usos del suelo.

Salidas GeoTIFF EPSG:25830: NDVI/EVI2 a 10 m, NDMI y SCL a 20 m, más manifiesto
con procedencia, consulta, porcentaje válido y hashes. NDMI no es humedad del
suelo medida. Las estadísticas corresponden al rectángulo, no al perímetro.
Cada ejecución conserva artefactos 30 días; no constituye un archivo histórico
permanente. Una caché por adquisición, código y AOI evita reprocesar mientras
esté disponible. Tras una ejecución correcta, Pages valida y publica el último producto automáticamente.
Las bandas se leen secuencialmente, sin ejecuciones simultáneas. La clasificación
SCL se reutiliza localmente para ambas resoluciones; los reintentos de transferencia
son limitados y esperan 30 segundos para no insistir continuamente ante errores.

Activado en `main` el 6 de octubre de 2026; ambos secretos S3 están configurados.
[Primera ejecución verificada](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/37518084581):
producto del 24/09/2026, NDVI/EVI2 a 10 m y NDMI/SCL a 20 m, EPSG:25830.
Los cuatro GeoTIFF se abrieron con GDAL y se verificaron rejillas y hashes.
El 99,07% del rectángulo supera el filtro SCL. Próxima fecha programada:
15/10/2026, 05:30 UTC. Los índices se pueden seleccionar en el panel Sentinel del visor.

No pegar claves en el chat ni guardarlas en archivos del repositorio.
Guía oficial: https://documentation.dataspace.copernicus.eu/APIs/S3.html

Prueba local sin autenticación (Python de QGIS con GDAL y NumPy):

```sh
python scripts/test_sentinel.py
python scripts/sentinel_pipeline.py --catalogue-only --catalogue-file data/sentinel-catalogue.json
```

Se ha validado la selección con el catálogo real del 6 de octubre de 2026.
La descarga S3 y los GeoTIFF finales también se verificaron en la ejecución indicada.

La leyenda del pie muestra sólo las capas activas con opacidad mayor que cero.
Se actualiza al cambiar visibilidad u opacidad, también en móvil, y muestra
«Sin capas visibles» cuando todas están ocultas. Sustituye el bloque explicativo.

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
python3 -m unittest discover -s scripts -p 'test_*.py'
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
| 9 | [ ] Activación/desactivación de las cuatro capas. | Interruptor Zona regable probado con dobles. |
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
- Navegación táctil superior derecha, botones de al menos 44 px y foco visible. El panel de capas queda alineado a la derecha, debajo de los botones, también en escritorio.
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

Corrección 0.1.8: el gate ejecuta ahora `check_network_policy`; se corrigen los
patrones sobreescapados y se comparan las directivas y fuentes de la CSP con el
contrato M0.2. CI también ejecuta pruebas de mutación para destinos prohibidos,
CSP ausente/duplicada/permisiva y CORS anónimo, incluida la llamada desde `main`.
Son comprobaciones estáticas de literales: no analizan todos los posibles
destinos construidos dinámicamente ni sustituyen la inspección de red real.

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
