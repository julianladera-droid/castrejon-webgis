# castrejon-webgis

Visor de control de la **C.R. Canal de Castrejón Margen Derecha**.

## Estado
M0.2 + M4 — visor cartográfico con índices Sentinel y publicación automática.

Capas actuales:
- Averías públicas: fotografía, formulario, estado y descarga KMZ; plugin WordPress instalado y activo el 27/10/2026.
- PNOA Máxima Actualidad (IGN/CNIG), XYZ/TMS.
- Recintos SIGPAC (FEGA/MAPA), WMS.
- Catastro INSPIRE, límites de parcela.
- Zona regable: perímetro de referencia aportado en `ZR.gml`, pendiente de ajuste.

## Averías: aplicación móvil y WordPress

El usuario ha elegido aprovechar el WordPress existente para datos, fotografías y
acceso del personal. `wordpress/castrejon-averias` es el plugin y `averias/` contiene
los archivos canónicos del formulario y de la capa pública. El paquete se genera con
`python scripts/package-incidents.py` en `artifacts/castrejon-averias-1.1.0.zip`.
No se necesita FastAPI ni un servidor adicional para este módulo.

La aplicación se sirve en `/averias-campo/` desde WordPress, fuera de la maquetación
del tema. El visor sigue en GitHub Pages y consulta
`https://comregantescastrejonmd.net/wp-json/castrejon/v1/incidents` sin credenciales.
La configuración inicial del visor señala ese origen confirmado; si el plugin no
está activo se muestra «Averías no disponibles», nunca una lista vacía engañosa.

### Instalación

1. Generar el ZIP y subirlo en **WordPress → Plugins → Añadir plugin → Subir plugin**.
   Activar **Castrejón · Averías**. Requiere WordPress 6.6+, PHP 8.1+ y GD.
2. La activación crea las tablas `castrejon_incidents` y
   `castrejon_incident_events` con el prefijo de la instalación, y el rol
   **Operario de averías**. Los administradores pueden publicar; ningún otro rol
   obtiene permisos automáticamente. Asignar el rol al personal desde Usuarios.
3. Abrir **Averías** en el menú de administración o `/averias-campo/` desde el móvil.
   Opcionalmente añadir ese enlace al menú del portal. No se necesita una página
   con un shortcode ni incrustar el visor en WordPress.
4. Excluir `/averias-campo/`, `/averias-campo/session/` y la API del caché de páginas
   si hay un plugin de caché adicional. El código envía cabeceras para impedir
   almacenar sesiones. Comprobar que el dominio sirve los assets del plugin sin
   reescritura hacia otro CDN: su CSP admite esos archivos del mismo origen.
5. Desplegar el cambio del visor mediante el workflow Pages y comprobar desde el
   dominio público que la lectura REST y la foto no fallan por CORS.
6. Prueba de aceptación: publicar una incidencia real autorizada con foto/GPS,
   consultarla sin sesión y actualizarla a «En reparación» y «Resuelta».
   No se han insertado incidencias de prueba en producción.

El conector WordPress permite instalar plugins del catálogo, pero no subir este ZIP
propio. La carga requiere la interfaz de administración o un acceso de despliegue
del alojamiento. El código local y las pruebas no equivalen a esa instalación.

### Uso y datos

- Campos: foto, tipo, elemento/referencia libre opcional, descripción, prioridad,
  fecha de observación, ubicación y precisión GPS. No se inventa una relación con
  un hidrante o parcela. La posición puede corregirse tocando el mapa o escribiendo
  coordenadas; una corrección manual retira la precisión GPS.
- **Guardar borrador** conserva datos y foto en IndexedDB del dispositivo. No los
  publica ni sincroniza automáticamente. Tras un intento de envío, la copia queda
  bloqueada para repetir exactamente el mismo UUID y contenido si la respuesta se
  pierde. Una colisión con contenido diferente se rechaza. No borrar los datos del
  navegador sin exportar antes los borradores importantes.
- **Publicar** exige sesión WordPress y nonce REST válido, más la capacidad
  `manage_castrejon_incidents`. El usuario confirma en pantalla que la foto y los
  campos serán públicos. **Comprobar acceso** obtiene un nonce nuevo si caduca.
- Lectura pública paginada de 250 en 250. El visor valida el contrato, ofrece
  filtros por estado, listado accesible y actualización manual. La ficha de avería
  tiene prioridad sobre la parcela en el mismo píxel. Una sola ficha abierta.
- Actualizar estado usa una versión para rechazar ediciones concurrentes. Se
  registra fecha de cierre y auditoría privada con el usuario; reabrir retira la
  fecha de cierre. No hay borrado público de averías.
- Fotos: el móvil convierte a JPEG de hasta 1600 px y el servidor vuelve a
  decodificar/redimensionar, retirando metadatos. Máximo 2 MB de foto de entrada,
  16 megapíxeles al decodificar en servidor y 3 MB de solicitud de publicación.
  Foto y datos se guardan en la misma fila InnoDB, con auditoría transaccional.
  No se usa la biblioteca de medios ni se expone el autor en la API pública.
- KMZ: ZIP con `doc.kml`, campos `ExtendedData` y `files/foto.jpg` incluida; funciona
  sin conexión para borradores. Es intercambio/copia, no un mecanismo de importación.
- Las coordenadas de campo se conservan en EPSG:4326, con fuente GPS/manual. Son
  observaciones operativas, no el maestro técnico. La futura incorporación al
  inventario requiere normalizar a EPSG:25830; aquí no se calculan metros o áreas.
- La PWA prepara formulario y recursos locales tras una primera visita con red.
  El fondo PNOA requiere conexión. No guarda sesiones ni respuestas de la API en
  caché. GPS/cámara dependen de HTTPS y de los permisos del dispositivo.
- La desactivación/desinstalación conserva las tablas para evitar perder el
  histórico. Incluir ambas tablas en las copias de seguridad de WordPress. Esta
  primera versión no incluye edición de texto/foto ya publicados ni importación KMZ.

### Calidad de ubicación (plugin 1.1.0)

Antes del primer envío, la ficha y cada borrador muestran una revisión espacial.
La confirmación repite las coordenadas y los avisos calculados por WordPress en
`POST /castrejon/v1/location-check` (mismos permisos/nonce, sin guardar ni cachear).
Cancelar conserva el borrador editable y no envía la foto ni la incidencia.

- Se rechazan coordenadas imposibles, no numéricas o no finitas en WGS 84:
  longitud ±180°, latitud ±90°. No se corrigen automáticamente ejes ni signos.
- Se comprueba la pertenencia al polígono de referencia simplificado que ya muestra
  el visor, incluidos sus bordes. Fuera se avisa de que puede tratarse de una
  infraestructura del canal situada fuera de las parcelas.
- Fuera de la envolvente de referencia ampliada **0,15° por cada eje** se muestra
  un aviso destacado de punto muy alejado. Es un umbral provisional de anomalía,
  no un límite territorial, un buffer métrico ni un ámbito autorizado. Se señalan
  además posibles intercambios de ejes o signo de longitud.
- El perímetro sigue pendiente de ajuste. **Todos los avisos territoriales permiten
  publicar tras revisarlos y confirmar**. Estar dentro tampoco acredita exactitud,
  pertenencia a una parcela o vínculo con una infraestructura.
- GPS con precisión peor de **50 m** requiere revisión; 50 m exactos no activan el
  aviso. Precisión cero se señala como desconocida, nunca como posición exacta.
  Se puede repetir el GPS o corregir el punto. Su incertidumbre no se utiliza para
  declarar que una posición está dentro. Los valores negativos, ausentes/no finitos
  o superiores a 100.000 m son inválidos en origen GPS.
- Las entradas manuales admiten coma o punto decimal, sin miles ni grados/minutos.
  Al guardar o exportar se aplican también las coordenadas escritas aunque no se
  haya pulsado «Usar estas coordenadas». Se retira la precisión GPS anterior.

La política y su procedencia se empaquetan en el plugin y en la caché móvil, sin
consultar servicios GIS externos. Tras cambiar la referencia, ejecutar
`python scripts/build-location-policy.py`; `--check` detecta copias desactualizadas.
Son comprobaciones de pertenencia angular, sin calcular áreas o distancias.

Actualización: desplegar primero la lectura del visor de este cambio y después
sustituir el plugin por el ZIP **1.1.0**. El job WordPress de Actions ofrece el ZIP
como artefacto tras superar las pruebas. Pages no instala plugins en WordPress.
No se migran tablas ni borradores. Los registros anteriores siguen consultándose;
los borradores sin enviar se revisan con la política actual. Los ya intentados
conservan exactamente UUID/contenido/foto y su reintento idempotente. El endpoint
original no exige campos de revisión nuevos a clientes anteriores.

Los recursos de captura llevan versión y el service worker cambia de caché para
impedir que una página nueva use JavaScript de captura de 1.0.0. Tras actualizar
el plugin, reabrir el formulario. No borrar los datos del navegador.

### Verificación

`node scripts/test-location.cjs` comprueba interior/borde/exterior, lejanía, ejes,
signo, precisión y entrada decimal. `node scripts/test-incidents-form.cjs` ejecuta
los manejadores reales con dobles locales: edición manual pendiente, GPS/mapa,
borrador anterior, cancelación y reintentos idénticos.
`node scripts/test-incidents.cjs` comprueba validación, KMZ con imagen, paginación,
fallos de red y exclusión de sesiones/API del service worker.
`node scripts/test-incidents-map.cjs` verifica selección, cierre, filtros y fallos
sin confundirlos con ausencia de incidencias.
Para IndexedDB y WordPress desechable:

```sh
npm install --prefix artifacts/qa @wp-playground/cli@3.1.61 fake-indexeddb@6.2.6
python scripts/package-incidents.py
node scripts/test-drafts.cjs
node scripts/verify-wordpress.mjs
```

El último comando instala el ZIP en WordPress Playground (PHP 8.3, WordPress 6.9),
prueba paridad espacial PHP/JS, ubicaciones exteriores admitidas, roles, REST pública,
cookie/nonce por HTTP, fotos, colisiones, reintentos,
versiones y auditoría. Usa SQLite de Playground; no sustituye la comprobación final
en MySQL/WordPress.com. `--preview` mantiene un entorno local con datos sintéticos.
No ejecutar `test-wordpress-incidents.php` en producción.

Verificación del cambio 1.1.0 (30/10/2026): suites JS y gate aprobados;
WordPress 6.9/PHP 8.3 desechable con paridad de 11 casos PHP/JS, endpoint protegido,
ubicaciones exteriores admitidas e idempotencia. Python: 16 pruebas, 5 omisiones
por ausencia de GDAL. Chromium con GPS simulado ±120 m, coma decimal sin pulsar
«Usar estas coordenadas», IndexedDB, cancelación antes del envío y reapertura sin
conexión; sin desbordamiento horizontal a 320×568, 390×844 y 844×390. PNOA bloqueado
en esa prueba de navegador; no certifica disponibilidad de servicios remotos.
Pendientes: GPS/cámara en teléfono físico e instalación de 1.1.0 en producción.

Validado localmente: suites anteriores, regresiones JS del visor y gate; Python
15 pruebas con 5 omisiones por faltar GDAL en ese entorno. Navegador a 390×844:
foto local, coordenadas, guardado y KMZ descargado con CRC/XML/JPEG comprobados.
Instalación real verificada el 27/10/2026 en `comregantescastrejonmd.net`: plugin
1.0.0 activo, acceso autorizado con la cuenta administradora, API anónima 200 sin
registros ficticios, CORS para Pages, sesión anónima sin permisos y service worker
servido correctamente. Pendientes: GPS/cámara en teléfono físico y primera avería
real. El envío completo se ha probado en WordPress local, sin crear datos de prueba
en producción.

## Arquitectura de esta fase
GitHub Pages sirve únicamente el frontend estático. WordPress actúa como portal y enlaza al visor. Los servicios cartográficos se consumen directamente desde sus proveedores oficiales.

Incluye el perímetro de referencia y parcelas catastrales públicas recortadas; no contiene datos personales, telemetría ni simulaciones.

## Comparación entre imágenes

En **Capas del mapa → Comparar dos imágenes**, seleccionar el índice y las fechas
A (anterior) y B (posterior). El separador muestra A a la izquierda y B a la derecha,
con la misma paleta y opacidad. La primera pareja disponible es 24/09/2026 → 14/10/2026.
Al pulsar una parcela, la ficha muestra medias A/B, diferencia B−A y cobertura común
para NDVI, EVI2 y NDMI. Desactivar la comparación recupera la ficha individual.

Las medias comparadas usan exactamente los mismos centros de píxel válidos en ambas
fechas; pueden diferir de las medias individuales. Se exige 80% de cobertura común.
La diferencia está en unidades del índice, no en porcentaje, y se calcula antes de
redondear. Nodata y cobertura insuficiente se muestran como ausencia de datos, nunca cero.
Se conservan las rejillas originales EPSG:25830 (10 m NDVI/EVI2, 20 m NDMI); una pareja
desalineada impide publicar. No se remuestrean los datos para calcular cambios.

`scripts/parcel_grid.py` centraliza muestreo, máscaras parcelarias y validez;
`scripts/parcel_comparison.py` genera una tabla compacta con procedencia y hashes.
El navegador reutiliza dos PNG y una tabla JSON por pareja (unos 121 kB para las
919 parcelas actuales), sin descargar TIFF ni ejecutar cálculos geográficos.
Las peticiones antiguas no sobrescriben la selección actual. Si falla una imagen,
se oculta la pareja; desactivar/reactivar reintenta. Si falla la tabla, volver a
pulsar la parcela reintenta sin mostrar valores anteriores.

Pages recupera productos propios validados, verifica el SHA-256 del ZIP y evita
fechas duplicadas. Requiere dos adquisiciones no caducadas; si faltan, conserva el
sitio publicado. No es todavía un archivo histórico permanente: la retención de
90 días se aplica sólo a los nuevos artefactos.

Base para la siguiente fase: SCL de 20 m conservado junto a índices, fechas y hashes.
[NDMI indica contenido de agua en la vegetación](https://www.usgs.gov/landsat-missions/normalized-difference-moisture-index);
[SCL clasifica la escena](https://sentiwiki.copernicus.eu/web/s2-processing), incluida agua,
pero ninguno confirma por sí solo encharcamiento. La siguiente implementación deberá
validar una regla con bandas/índices de agua y observación de campo, distinguir agua
persistente y nubes/sombras, informar superficie desconocida y tratar fraccionalmente
los píxeles de borde al calcular porcentaje por superficie métrica de parcela.
Los centros de píxel actuales no equivalen al área catastral exacta. La primera estimación exploratoria de agua nueva se describe a continuación.

Pruebas: `node scripts/test-comparison.cjs`, `python scripts/test_collect_sentinel_products.py`
y, con GDAL/NumPy, `python scripts/test_parcel_comparison.py`.

## Agua superficial nueva: posible encharcamiento

La capa **Posible encharcamiento**, activada inicialmente, dibuja en azul el agua
superficial nueva dentro de las parcelas. Usa la fecha seleccionada como B y la
anterior disponible como A. Con comparación activa, corresponde a B sobre todo el
mapa; no sigue el separador. La ficha muestra porcentaje sobre la parcela completa,
superficie en m², fechas, agua en ambas imágenes y superficie sin evaluar.
Ocultar la capa mantiene los datos de la ficha; seleccionar una fecha sin referencia
anterior retira los resultados anteriores.

Método exploratorio `scl_new_surface_water_v1`, sin validación de campo para estas
fechas: SCL B=6 y A=4/5. A=B=6 es agua en ambas imágenes y se contabiliza aparte,
sin llamarla permanente. Sólo SCL 4,5,6 en ambas fechas permite evaluar el cambio;
las demás clases, nodata y exterior del raster son desconocidos. No se infiere
agua por NDMI. Puede incluir variaciones de cauces/balsas y omitir agua oculta por
vegetación o zonas pequeñas. No detecta toda saturación del suelo ni confirma daños.
El usuario conoce casos de otras fechas, pendientes de incorporar para contrastar
este criterio y decidir si añadir bandas de agua, radar o una máscara agrícola.

`scripts/parcel_water.py` poligoniza las celdas originales a 20 m EPSG:25830 y las
interseca con cada geometría maestra, conservando bordes, huecos y fragmentos.
El denominador es el área total del recorte parcelario, nunca sólo la parte válida.
Este tratamiento geométrico no proporciona resolución física subpíxel. Con menos
del 80% de área evaluable, el resultado es «No concluyente» y se distingue el agua
observada de lo desconocido. Cero no implica ausencia confirmada de encharcamiento.

Pages genera `parcel-water.json` y `water-zones.geojson` por pareja, con hashes,
fechas, método, procedencia SCL y vínculo al parcelario. Los resultados actuales
ocupan 42,6 kB y 16,3 kB: 51 fragmentos de agua nueva en 18 parcelas, de 919; seis
parcelas no alcanzan la cobertura mínima. El navegador descarga sólo esos resultados,
los verifica y reutiliza durante la sesión; sin TIFF ni GIS en el dispositivo.
Errores de red/integridad no se representan como cero y permiten reintentar.

Pruebas: `python scripts/test_parcel_water.py` con GDAL/NumPy y
`node scripts/test-water.cjs`, junto con las regresiones del comparador y las fichas.
La definición oficial de SCL está en [Copernicus SentiWiki](https://sentiwiki.copernicus.eu/web/s2-processing);
la regla temporal y sus porcentajes son estimaciones de este proyecto, no un
producto de inundación validado por Copernicus.

## Perímetro y área Sentinel (M4)

Al pulsar dentro de una parcela visible se abre una ficha inferior con referencia
catastral y superficie recortada en m² y ha. La superficie procede del maestro
EPSG:25830: no acredita superficie regada. Una sola parcela se resalta; se puede
cambiar pulsando otra, cerrar con «Cerrar» o Escape, o pulsar fuera. Al ocultar
parcelas o alejarse hasta zoom 14, la ficha se cierra. Con foco en el mapa, Enter
consulta la parcela del centro y las flechas desplazan la vista.

La ficha reutiliza el GeoJSON y su índice espacial, sin descargas ni dependencias
adicionales. Sólo consulta en pulsación simple; no durante arrastre, doble clic
de zoom o movimiento del cursor. En móvil pliega el panel de capas y reserva una
franja inferior desplazable para no cubrir atribuciones ni controles.

La ficha incluye NDVI, EVI2 y NDMI medios y una fecha común de la adquisición
seleccionada, incluso con «Sin índice». Pages calcula una única tabla compacta
por adquisición a partir de los índices originales validados: NDVI/EVI2 a 10 m,
NDMI a 20 m, y geometrías maestras EPSG:25830 de `data/parcel-master.json`.
Ese archivo técnico no se copia al sitio: sólo se publica la tabla de resultados.
Regenerar el maestro con `scripts/prepare_parcel_master.py ruta/al/zip` usando
Python de QGIS; se comprueban los hashes de la entrega y de la capa pública.

La media usa los centros de píxel dentro del recorte parcelario, sin ponderar
bordes. Excluye nodata, valores no finitos y NDVI/NDMI fuera de [-1,1], sin saturarlos.
EVI2 conserva valores finitos fuera de la escala visual 0–1. Exige al menos 80%
de centros válidos para cada índice; las parcelas sin centros a su resolución
o con cobertura insuficiente muestran «Sin datos suficientes». El porcentaje
describe píxeles muestreados, no superficie regada. Se indica la fecha real y se
marca una imagen de más de 30 días como antigua. No es diagnóstico agronómico.

La tabla se descarga sólo al consultar una parcela y se reutiliza durante la
sesión. La tabla v2 usa columnas [media, píxeles válidos, píxeles totales] y metadatos
de resolución y procedencia por índice. Se verifican hash, adquisición, fecha y correspondencia con el parcelario
cargado. No se descargan TIFF ni se calculan estadísticas en el dispositivo.
Pruebas: `node scripts/test-parcel-ndvi.cjs` y, con GDAL/NumPy,
`python scripts/test_parcel_ndvi.py` (obligatoria antes de publicar).

Parcelario incorporado: 919 parcelas de la entrega del 14/10/2026, recortadas a
ZR y con la exclusión de códigos 09000–09999 aplicada en origen. La capa aparece
gradualmente entre zoom 14 y 16, con líneas amarillas finas sin relleno. Se carga
una vez al acercarse y dispone de interruptor y reintento ante errores.
`data/parcels/parcelas.geojson` contiene sólo geometría, `refcat` e identificador
idénticos y superficie recortada en m²; no contiene titulares. La superficie no
acredita riego. Se mantienen las coordenadas sin suavizar para respetar límites
compartidos y fragmentos pequeños. El original EPSG:25830 se conserva localmente
en `sentinel-output/parcel-master/`; regenerar con QGIS/GDAL Python y
`scripts/prepare_parcels.py ruta/al/zip`. Esa geometría original y REFCAT serán
la base de los índices medios parcelarios calculados antes de publicar.
La copia web EPSG:4326 se representa en EPSG:3857 y no es el maestro de cálculo.
Validación: `node scripts/test-parcels.cjs` y comprobación visual con Sentinel.

«Zona regable» mantiene un único tono amarillo: superficie pastel cuando cabe el conjunto y línea fina discontinua +--+ al acercarse, sin relleno en detalle. Cambian progresivamente la opacidad y la representación según el tamaño de la ventana; las cruces mantienen separación de 80 píxeles. La leyenda acompaña al cambio. Está visible inicialmente y se puede ocultar. Su copia web se simplifica a 15 m y suaviza las esquinas, conservando el GML original. La geometría cargada pasa de 956 a 487 puntos y ocupa unos 10,9 kB; sustituye a la anterior.
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
una medida directa de humedad del suelo. La ficha ofrece las medias parcelarias
de los tres índices; los porcentajes del panel Sentinel describen el rectángulo.

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
Las nuevas ejecuciones conservan artefactos 90 días; no constituye un archivo histórico
permanente. Una caché por adquisición, código y AOI evita reprocesar mientras
esté disponible. Tras una ejecución correcta, Pages valida y publica las dos adquisiciones distintas más recientes disponibles automáticamente.
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
