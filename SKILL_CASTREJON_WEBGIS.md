# SKILL · Castrejón WebGIS — Contrato de arquitectura y evolución
Version: 0.1.17
Fecha base: 2026-09-30
Estado: ACTIVO · se actualiza tras cada ciclo de pruebas

## 0. Propósito
Este archivo es el contrato operativo del WebGIS de la Comunidad de Regantes del Canal de Castrejón Margen Derecha.
Su función es evitar que la aplicación se descomponga por cambios parciales, mantener una línea técnica coherente y registrar
las decisiones que sólo pueden cambiarse de forma consciente y documentada.

Regla principal: cualquier corrección derivada de pruebas actualiza primero este contrato (versión, causa, cambio y regresión)
y después el código. No se modifica una parte de la aplicación sin comprobar sus relaciones con el resto.

## 1. Alcance general
Portal institucional: WordPress.
Aplicación técnica: WebGIS independiente, servida fuera de WordPress y enlazada desde «Área de riego». WordPress no ejecuta ni incrusta el visor operativo.
Sector piloto inicial: SECTOR IV.
Primera fase cartográfica: visor funcional sin datos internos; PNOA mediante teselas pregeneradas XYZ/TMS oficiales, Recintos SIGPAC mediante WMS oficial y Catastro mediante WMS INSPIRE de imagen completa.
Fases posteriores: cartografía interna, parcelas, hidrantes, red, incidencias, telemetría, NDVI y simulación hidráulica.

## 2. Arquitectura objetivo
- Frontend: React + TypeScript + OpenLayers.
- API: Python + FastAPI.
- Base geoespacial maestra: PostgreSQL + PostGIS.
- Mantenimiento/edición técnica: QGIS.
- Hidráulica: EPANET 2.2, integrado mediante WNTR/Python.
- Teledetección: Copernicus Data Space / Sentinel-2.
- Portal: WordPress, separado del WebGIS.
- Despliegue: la aplicación WebGIS se sirve como aplicación estática/técnica independiente y WordPress actúa como portal, no como motor GIS.
- Desarrollo y control de versiones: Git/GitHub. Repositorio canónico previsto: `castrejon-webgis`.
- Frontend estático de pruebas/producción temprana: GitHub Pages; WordPress sólo enlaza a la URL publicada.

No se ejecutarán procesos GIS pesados, Python, QGIS Server o simulaciones dentro del hosting de WordPress.

## 2.1 Arquitectura CRS de tres niveles — REGLA BLOQUEADA

La aplicación utiliza tres sistemas de referencia con funciones distintas. Ninguno sustituye a los otros.

### Nivel A · CRS maestro técnico: EPSG:25830 — ETRS89 / UTM zona 30N
Uso obligatorio para:
- almacenamiento maestro de geometrías internas en PostGIS;
- edición y control de calidad en QGIS;
- parcelas, sectores, hidrantes, nudos, tuberías, válvulas, captaciones y demás elementos propios;
- cálculos métricos: longitudes, superficies, distancias, buffers y relaciones espaciales;
- preparación de geometría/topología para hidráulica y EPANET;
- operaciones que requieran unidades métricas coherentes.

Regla: NO calcular longitudes, superficies o distancias técnicas en EPSG:3857 ni en EPSG:4326.

### Nivel B · CRS de visualización web: EPSG:3857 — Web Mercator
Uso obligatorio para:
- `ol.View` de OpenLayers;
- PNOA XYZ/WMTS y demás fondos web compatibles con GoogleMapsCompatible;
- pirámides de teselas, caché y navegación del mapa;
- renderizado de capas en cliente cuando la fuente esté preparada para 3857.

Regla: EPSG:3857 es un CRS de PRESENTACIÓN, no el CRS maestro del inventario ni de cálculo técnico.

### Nivel C · CRS de coordenadas e intercambio: EPSG:4326 — WGS 84
Uso para:
- centro inicial legible del visor;
- visualización de longitud/latitud al usuario;
- enlaces y servicios externos que trabajen en lon/lat;
- intercambio GeoJSON/API cuando el contrato de interfaz lo requiera;
- parámetros de navegación compartidos con sistemas externos.

Regla: EPSG:4326 se usa para INTERCAMBIO y lectura humana; no para cálculos métricos de red.

### Transformaciones permitidas
Flujo canónico:
`EPSG:25830 (maestro) -> API/servicio -> EPSG:3857 (mapa)`
`EPSG:25830 (maestro) -> API/servicio -> EPSG:4326 (intercambio/coords)`
`EPSG:4326 (entrada usuario) -> EPSG:3857 (vista OpenLayers)`

Toda transformación debe:
- declarar CRS de origen y destino;
- conservar el identificador del objeto;
- no alterar la geometría maestra almacenada;
- ejecutarse en servidor cuando afecte a consultas espaciales, permisos o cálculo;
- evitar reproyecciones encadenadas innecesarias.

### Contrato por componente
- PostGIS: geometrías internas maestras en EPSG:25830.
- QGIS: proyecto técnico preferente en EPSG:25830.
- FastAPI: consulta/transforma desde 25830; documenta CRS de salida por endpoint.
- OpenLayers: vista en EPSG:3857.
- PNOA XYZ/TMS: EPSG:3857.
- Catastro: se solicita/renderiza en CRS compatible con el visor; no define el CRS maestro interno.
- Cursor: se transforma a EPSG:4326 para mostrar lon/lat.
- EPANET/WNTR: geometría de soporte y distancias derivadas desde EPSG:25830; sus variables hidráulicas no dependen del CRS de pantalla.
- NDVI: geometrías de parcela se conservan en 25830; las fuentes ráster se reproyectan o consultan según su CRS nativo sin reemplazar la geometría maestra.

### Centro inicial bloqueado
Referencia humana/intercambio: EPSG:4326 `lon=-4.371848, lat=39.834749`.
La vista de OpenLayers transforma ese punto a EPSG:3857 al inicializarse.
Zoom inicial: 13.27. Escala de referencia: 1:43 526.

### Regresiones CRS obligatorias
Se considera fallo de arquitectura si ocurre cualquiera de estos casos:
1. Una capa interna maestra se almacena en 3857 o 4326 sin justificación documentada.
2. Se calculan metros/hectáreas directamente sobre geometrías 4326 o 3857.
3. El visor cambia su `View` fuera de EPSG:3857 y rompe la pirámide PNOA.
5. Una reproyección modifica/sobrescribe la geometría maestra.
6. Un endpoint devuelve geometrías sin declarar el CRS contractual.
7. Se mezclan coordenadas 25830/3857/4326 sin transformación explícita.
8. La selección espacial o los permisos geográficos se aplican sobre geometrías reproyectadas de presentación en lugar de las maestras.

## 3. Invariantes de datos
1. Identificadores estables e inmutables para todas las entidades internas.
2. Nunca inferir relaciones por proximidad si existe o debe existir una relación explícita.
3. Toda cifra técnica debe almacenar origen, instante/periodo, unidad, estado y calidad.
4. Distinguir siempre:
   - MEDIDO: lectura de equipo/sensor.
   - SIMULADO: resultado de un modelo y escenario identificados.
   - ESTIMADO: valor derivado de un método documentado.
   - OBSERVADO/EDITADO: dato incorporado o validado por personal autorizado.
5. Un dato ausente no se sustituye por cero.
6. Un dato desactualizado debe mostrarse como desactualizado, no como actual.
7. La capa visual nunca es la autoridad de permisos: la autorización se decide en servidor/API.
9. No exponer nombres de comuneros ni relaciones privadas en capas públicas.

## 4. Entidades básicas y relaciones
### 4.1 Territorio
SECTOR
- sector_id
- nombre
- geometría
- superficie
- fuente
- fecha_revision
- estado_dato

PARCELA
- parcela_id interno
- geometría
- superficie
- referencia_externa/catastral cuando proceda
- sector_id
- fuente
- fecha_revision
- estado_dato

Relación: SECTOR 1 ── N PARCELA.

### 4.2 Red hidráulica
HIDRANTE
- hidrante_id
- punto/geometría
- sector_id
- estado_operativo
- fuente
- fecha_revision

NUDO
- nudo_id
- punto
- cota
- tipo
- fuente

TUBERIA
- tuberia_id
- línea
- nudo_inicio_id
- nudo_fin_id
- diámetro
- material
- longitud
- estado
- fuente

VALVULA / ELEMENTO_RED
- elemento_id
- tipo
- geometría
- relación con nudo/tubería
- estado

CAPTACION / ASPIRACION
- captacion_id
- geometría
- sector_id
- referencia técnica
- estado

Relaciones:
SECTOR 1 ── N HIDRANTE.
PARCELA N ── M HIDRANTE mediante tabla PARCELA_HIDRANTE (nunca por «más cercano»).
NUDO 1 ── N TUBERIA como origen/destino.
TUBERIA 1 ── N ELEMENTO_RED cuando corresponda.
La topología de red debe validarse antes de simulación.

### 4.3 Operación y mantenimiento
INCIDENCIA
- incidencia_id
- fecha_apertura/cierre
- tipo
- estado
- prioridad
- descripción
- geometría opcional
- elemento_red_id opcional
- hidrante_id opcional
- sector_id
- fuente

ACTUACION
- actuacion_id
- incidencia_id
- fecha
- tipo
- observaciones
- responsable/rol (privado si procede)

Relación: INCIDENCIA 1 ── N ACTUACION.
Una incidencia puede apuntar a un elemento físico concreto; no se obliga a inventar ese vínculo.

### 4.4 Telemetría
SENSOR
- sensor_id
- tipo
- unidad
- elemento_red_id/nudo_id/hidrante_id
- proveedor
- estado

MEDICION
- sensor_id
- timestamp
- valor
- unidad
- calidad
- origen = MEDIDO

Relación: SENSOR 1 ── N MEDICION.

### 4.5 Simulación
MODELO
- modelo_id
- versión
- fecha
- fuente_topologia
- estado_validacion

ESCENARIO
- escenario_id
- modelo_id
- condiciones
- fecha_ejecucion

RESULTADO_SIMULADO
- escenario_id
- elemento_id
- variable
- valor
- unidad
- origen = SIMULADO

No mezclar visualmente mediciones con simulaciones sin identificación explícita.

### 4.6 Cultivos y teledetección
OBSERVACION_SATELITE
- parcela_id
- fecha
- producto
- indicador (p.ej. NDVI)
- valor/estadística
- máscara_calidad
- porcentaje_valido
- origen = ESTIMADO/OBSERVADO según proceso

No colorear una parcela como dato válido cuando la cobertura útil no supera el umbral definido.

## 5. Flujo funcional de la aplicación
Entrada -> mapa -> búsqueda/selección -> ficha de objeto -> relaciones -> módulo contextual.

M1 Inventario:
Mapa -> Sector -> Parcela/Hidrante/Red -> Ficha -> Relaciones.

M2 Incidencias:
Seleccionar elemento -> crear/consultar incidencia -> actuaciones -> cierre/histórico.

M3 Telemetría:
Elemento -> sensor -> serie temporal -> estado de comunicación -> comparación (sin confundir con simulación).

M4 NDVI:
Parcela -> fechas -> calidad -> serie -> comparación.

M5 Hidráulica:
Modelo validado -> escenario -> ejecutar -> resultados SIMULADOS -> comparar con MEDIDOS.

## 6. Interfaz común que no debe romperse
- Nombre funcional bloqueado: **Visor de control C.R. Canal de Castrejón Margen Derecha**.
- Los sectores son ámbitos de datos/filtros; nunca sustituyen el nombre general del visor.
- Cabecera compacta con identidad «Visor de control C.R. Canal de Castrejón Margen Derecha». Sector IV es el primer ámbito piloto de datos, no el nombre del visor.
- Área cartográfica central dominante.
- Barra de herramientas de navegación.
- Selector de capas.
- Control de opacidad.
- Leyenda/estado de servicios.
- Coordenadas del puntero.
- Escala.
- Ficha lateral reutilizable.
- Mensajes de carga/error visibles y no bloqueantes.
- Diseño responsive: panel de capas plegado al entrar en móvil, controles táctiles de al menos 44 px y soporte vertical/horizontal.
- Atribuciones y escala en una franja propia, fuera de las superposiciones del mapa; atribuciones siempre expandidas.
- Altura dinámica y áreas seguras del dispositivo. Coordenadas del centro en móvil y del cursor en escritorio.
- Navegación por teclado donde sea aplicable.
- Los módulos futuros se añaden al marco; no crean visores independientes.

## 7. Marco M0/M0.2 — configuración bloqueada inicial
Centro EPSG:4326: longitud -4.371848; latitud 39.834749.
Vista web: OpenLayers en EPSG:3857, centro transformado desde EPSG:4326.
Zoom inicial solicitado: 13.27.
Escala de referencia solicitada: 1:43 526.
Nota: la escala física exacta en pantalla depende de densidad de píxel/DPI; se conserva zoom 13.27 y se muestra una escala gráfica dinámica.

Servicios iniciales:
A) PNOA Máxima Actualidad (IGN)
- Producción M0.1: XYZ/TMS oficial de teselas pregeneradas: https://tms-pnoa-ma.idee.es/1.0.0/pnoa-ma/{z}/{x}/{-y}.jpeg
- Proyección: EPSG:3857 / GoogleMapsCompatible.
- Formato: JPEG 256×256.
- Niveles: hasta 19 según servicio oficial.
- WMS de referencia/capacidades: https://www.ign.es/wms-inspire/pnoa-ma
- WMTS de referencia: https://www.ign.es/wmts/pnoa-ma
- Regla: el fondo operativo NO debe volver a ImageWMS salvo diagnóstico explícito. El objetivo es reutilizar pirámide y caché de teselas pregeneradas.
- Uso: fondo visible.

B) Recintos SIGPAC (FEGA/MAPA)
- WMS oficial: https://sigpac-hubcloud.es/wms
- Capa de campaña vigente: AU.Sigpac:recinto
- Cliente M0.2: TileWMS, conforme al ejemplo oficial OpenLayers del propio servicio.
- Versión WMS: 1.3.0.
- Formato: image/png transparente.
- Proyección de visualización: EPSG:3857.
- Estado inicial: visible, opacidad 0,33 (decisión definitiva del usuario, 2026-09-29).
- Licencia/atribución: CC BY 4.0; mantener atribución SIGPAC · FEGA/MAPA.
- Regla: el WMS es una representación de los recintos, no la geometría maestra interna de la comunidad.
- Regla: la campaña vigente puede cambiar; verificar GetCapabilities/nombre de capa en cada revisión mayor.

C) Dirección General del Catastro
- Servicio operativo M0.2: WMS INSPIRE de la D.G. del Catastro: https://ovc.catastro.meh.es/cartografia/INSPIRE/spadgcwms.aspx
- Capa: CP.CadastralParcel
- Estilo: CP.CadastralParcel.BoundariesOnly
- Cliente M0.2: ImageWMS, petición de imagen completa.
- Versión WMS: 1.1.1.
- Estado inicial: oculto; se activa a demanda para evitar solape visual con SIGPAC.
- Opacidad inicial al activar: 0,62.
- Motivo: la propia D.G. del Catastro desaconseja peticiones teseladas contra su WMS clásico porque multiplican consultas concurrentes y pueden degradar el servicio.
- Marca/atribución: NO eliminar, recortar ni ocultar artificialmente una marca o atribución devuelta por el servicio. Para una representación limpia, usar el servicio INSPIRE y el estilo oficial BoundariesOnly, manteniendo la atribución visible en el control del mapa.
- Restricción: consulta normal; no automatizar descargas masivas mediante sucesivas peticiones WMS.

Durante M0 no se cargan geometrías internas ni datos personales.

## 8. Estado y navegación del mapa
Controles mínimos:
- Zoom + / -
- Inicio (restablece centro y zoom 13.27)
- Vista anterior / siguiente
- Pantalla completa
- Selector de capas
- Opacidad SIGPAC y Catastro
- Estado de carga/error por servicio
- Coordenadas EPSG:4326 del cursor
- Escala gráfica dinámica
- Indicador de zoom

Historial de vista:
- Sólo se registra tras movimientos finalizados.
- Cambiar capas no altera el historial.
- «Inicio» también entra en historial.
- Evitar bucles cuando se navega atrás/adelante.

## 9. Seguridad y privacidad
- El visor público no solicita ni necesita acceso a dispositivos de la red local.
- Quedan prohibidos en frontend: `localhost`, IP privadas/loopback/link-local, dominios `.local` y `targetAddressSpace: local/private`.
- Todo destino remoto del M0.2 debe ser HTTPS y pertenecer a la lista explícita: jsDelivr/OpenLayers, PNOA IGN, SIGPAC FEGA/MAPA y Catastro.
- Mantener CSP restrictiva en `index.html`; cualquier nuevo origen debe justificarse, añadirse a la skill y al gate antes de desplegar.
- No forzar `crossOrigin: anonymous` en WMS mientras no exista una función que necesite lectura de píxeles/exportación de canvas; revisarlo si se añade esa función.
- WordPress y WebGIS son capas separadas.
- No subir datos reservados a la biblioteca multimedia ordinaria como mecanismo de protección.
- Toda API privada valida autorización en cada petición.
- Los filtros del frontend no son controles de seguridad.
- Permisos geográficos futuros: usuario/rol -> ámbito autorizado -> recurso.
- No exponer endpoints, credenciales, tokens o claves privadas en JavaScript.
- Telemetría inicialmente sólo lectura.
- Simulación no envía órdenes a la red.
- El piloto documental 0.1.1 no autoriza aún documentos reales.

## 10. Pruebas obligatorias por cambio
La puerta CI local (`python3 scripts/check_webgis.py`, Python 3.12 + Node 24)
automatiza sólo estructura básica HTML, sintaxis JavaScript, configuración efectiva
de fuentes/centro/zoom/atribuciones y patrones de secretos evidentes. No consulta
servicios remotos ni certifica renderizado o disponibilidad. Conservar las 20
comprobaciones siguientes: las partes visuales, de interacción real y de servicios
se registran manualmente con el checklist del README, sin darlas por superadas por CI.
Pages sólo empaqueta y despliega desde `main` tras superar el job `gate`.

Cada cambio debe comprobar:
1. Arranque sin errores de JavaScript.
2. Carga PNOA.
3. Carga SIGPAC Recintos.
4. Carga Catastro INSPIRE al activarlo.
5. Centro inicial y zoom.
6. Zoom +/-.
7. Inicio.
8. Atrás/adelante de extensión.
9. Activación/desactivación de capas.
10. Opacidad SIGPAC y Catastro.
11. Coordenadas.
12. Escala.
13. Responsive móvil.
14. Teclado/foco básico.
15. Mensaje comprensible si un servicio cartográfico falla.
16. En zoom repetido, un error aislado de tesela no debe bloquear ni marcar permanentemente el servicio como caído.
17. El PNOA debe usar la pirámide XYZ/TMS oficial; comprobar que no se generan peticiones GetMap WMS durante el zoom.
18. Mantener teselas intermedias durante la transición y limitar la precarga para no saturar red/servidor.
19. Catastro debe usar ImageWMS/INSPIRE en M0.2; no generar mosaicos de TileWMS contra el servicio catastral.
20. Mantener visibles las atribuciones de PNOA, SIGPAC y Catastro; no ocultar marcas/atribuciones oficiales mediante CSS, recorte o superposición.

Para módulos con datos internos se añaden:
- permisos,
- integridad referencial,
- topología,
- unidades,
- fechas,
- calidad,
- diferenciación MEDIDO/SIMULADO/ESTIMADO.

## 11. Regla de evolución de esta skill
Formato de cada cambio:
- Versión
- Fecha
- Fallo observado
- Reproducción
- Causa
- Corrección
- Regresión añadida
- Archivos afectados
- Compatibilidad hacia atrás

No borrar una regla por comodidad. Si una regla cambia, conservar el motivo en el historial.

## 12. Registro de cambios
### 0.1.17 — 2026-10-06
- Petición: aligerar y suavizar el perímetro, sustituir el anterior y usar amarillo–rojo–amarillo.
- Sólo representación: simplificación topológica a 15 m en EPSG:25830 y redondeo local de esquinas con recorte máximo de 40 m. Validar geometría, desviación del contorno <=30 m y variación de área <1%; coordenadas web a seis decimales.
- Sustituir la única geometría incorporada, sin cargar la antigua ni añadir otra capa. GML original y AOI Sentinel se conservan. Tres trazos concéntricos con uniones redondas, sin relleno; leyenda coherente.
- Regresión: geometría válida y ligera, CRS, contorno único, colores y comprobación visual. El contorno continúa siendo provisional y no sirve como límite técnico de cálculo.

### 0.1.16 — 2026-10-06
- Petición: situar el cuadro de capas a la derecha, debajo de los botones de navegación.
- Corrección: panel alineado al margen derecho con espacio para la barra superior; también en móvil, donde los botones pasan arriba y el panel sigue plegado inicialmente.
- Regresión: comprobar separación vertical, alineación derecha, desplazamiento del contenido y acceso al mapa en escritorio y móvil. Sin cambios en capas ni procesamiento Sentinel.

### 0.1.15 — 2026-10-06
- Petición: publicar el visor actualizado e incorporar NDVI, EVI2 y NDMI. Incorporar también el perímetro y la leyenda dinámica preparados localmente.
- Publicación: Pages consume exclusivamente artefactos de ejecuciones satisfactorias de sentinel.yml en main de este repositorio. Validar manifiesto, hashes, CRS, rejillas y calidad antes de publicar. Sin candidato válido no reemplazar el sitio existente.
- Representación: GeoTIFF maestro EPSG:25830 descargable; PNG RGBA ligero reproyectado directamente a EPSG:3857 para ImageStatic. Transparencia en nodata; escala de color fija y explícita, sin normalización por escena. NDVI/NDMI de -1 a 1; EVI2 visualizado de 0 a 1 (saturación fuera del rango sólo en color).
- Interfaz: un índice visible cada vez, selector de adquisición disponible, opacidad, fecha real y antigüedad, calidad del rectángulo y descarga técnica. NDMI no se presenta como medida de humedad del suelo. No ofrecer fechas sin productos ni ocultar la antigüedad.
- Red: productos públicos en el mismo origen Pages; sin nuevos destinos CSP ni claves en cliente. El flujo Pages se activa también al terminar Sentinel y conserva el calendario autorizado de consultas Copernicus.
- Regresión: nodata/colores/reproyección, rechazo de artefactos incoherentes, selección de índice/fecha, errores de carga y respuestas tardías, opacidad/leyenda; escritorio y móvil más regresiones cartográficas existentes.

### 0.1.14 — 2026-10-06
- Activado Sentinel en main, commit e5304d80677fa031a5e4e96c4a3eed93f3466822. Primera ejecución real 37518084581 completada correctamente con secretos S3 configurados por el usuario.
- Producto del 24/09/2026; NDVI/EVI2 10 m y NDMI/SCL 20 m en EPSG:25830. Artefacto descargado y abierto con GDAL; rejillas y SHA-256 verificados. Calidad válida del rectángulo: 99,0663% NDVI/EVI2 y 99,0684% NDMI.
- Próxima fecha programada: 15/10/2026 a las 05:30 UTC. Artefactos retenidos 30 días; integración de índices en el visor pendiente. Frontend local no publicado en esta activación.

### 0.1.13 — 2026-10-06
- Calendario solicitado: cada tres días de febrero a septiembre inclusive, contando desde el 1 de febrero sin reiniciar al cambiar de mes; enero, octubre, noviembre y diciembre sólo el día 15.
- GitHub comprueba el calendario antes de consultar Copernicus. Los días intermedios no ejecutan el trabajo de descarga. Hora conservada: 05:30 UTC. Ejecución manual disponible.
- Evitar cargas innecesarias: conservar caché por adquisición/AOI/código, concurrencia única y bandas secuenciales; reutilizar SCL ya recortada para la rejilla de 10 m en vez de leerla otra vez por S3. Reintentos limitados con espera de 30 segundos.
- Regresión: intervalo exacto de tres días en años normales/bisiestos y exclusividad del día 15 fuera de temporada.

### 0.1.12 — 2026-10-06
- Petición: utilizar productos existentes y automatizar desde GitHub Actions.
- Fuente: productos oficiales Sentinel-2 L2A ya corregidos atmosféricamente; recorte de bandas por S3 y GDAL, sin exportación manual de Browser ni credenciales en el visor.
- Ejecución diaria y manual, permisos de repositorio de lectura; secretos CDSE_S3_ACCESS_KEY y CDSE_S3_SECRET_KEY. Salidas como artefactos de Actions, sin publicación automática en Pages.
- Selección: producto reciente con cobertura completa del AOI y nubosidad de tesela <=20%; validar después calidad SCL local (clases 4,5,6), sin excluir usos del suelo. Fallar claramente si no hay candidato o calidad suficiente.
- Rejillas EPSG:25830 de 10/20 m alineadas hacia fuera; remuestreo nearest para conservar categorías y coherencia; reflectancia por escala/offset STAC. NDVI/EVI2 10 m; NDMI 20 m.
- Descarga programada depende de configurar secretos y llevar el workflow a la rama predeterminada; no se considera activa por crear archivos locales.

### 0.1.11 — 2026-10-06
- M4: consulta real del catálogo STAC público de Copernicus para el rectángulo envolvente. Periodo inicial de exploración: 2026-09-06 a 2026-10-06 (UTC, inicio del día).
- Preparar manifiesto reproducible de escena candidata y bandas; nubosidad de tesela sólo para preselección, nunca como porcentaje válido de la zona regable.
- NDVI/EVI2: B04/B08 a 10 m; NDMI: B8A/B11 a 20 m. NDMI no mide directamente humedad del suelo. SCL para calidad, sin máscara de usos ni Catastro.
- Convertir DN a reflectancia con escala/offset publicados en cada asset; excluir nodata antes de índices. No mezclar adquisiciones silenciosamente.
- Descarga autenticada pendiente de acceso del usuario. Credenciales fuera del repositorio y del frontend; no añadir servicios Sentinel a la CSP hasta integrar productos procesados.

### 0.1.10 — 2026-10-06
- Petición: simplificar la leyenda y hacerla dinámica.
- Cambio: sustituir el bloque explicativo por una leyenda compacta en el pie, disponible también en móvil. Mostrar sólo capas activas con opacidad mayor que cero; sincronizar con eventos de visibilidad/opacidad de OpenLayers. Nombres breves en el selector, conservando atribuciones.
- Regresión: estado inicial, conmutadores, opacidad cero y restauración, y ausencia de capas visibles. Pruebas offline; revisión visual independiente.

### 0.1.9 — 2026-10-06
- Decisión del usuario: ZR.gml es el perímetro de referencia de la zona regable, pendiente de ajustes; no representa parcelas ni limita por sí solo la superficie efectivamente regada.
- M4: consultas, descarga y procesamiento Sentinel usarán el rectángulo envolvente, separado del perímetro de referencia. El área rectangular no se presentará como superficie regable.
- Fuente: ZR.gml, SHA-256 986a472fb53d8bd05b732c650c5a18906cde07c0ba4dec526876e3788e0d608c. Polígono válido GEOS, 2.416,931684 ha en EPSG:25830; la estimación anterior de 1.800 ha no sustituye esta geometría.
- Cambio: capa vectorial visible y desactivable «Zona regable · referencia», sin relleno, derivada a EPSG:4326 y renderizada en EPSG:3857. Centro e Inicio conservados.
- Rectángulo técnico: minX=373395.542, minY=4406452.368, maxX=388258.243536932, maxY=4412858.8251707 en EPSG:25830. Consulta STAC con bbox conservadora en EPSG:4326.
- Regresión: cuarta capa, identidad, reproyección declarada, visibilidad y conmutador; gate cartográfico existente conservado. Sin descarga Sentinel ni publicación automática.

### 0.1.8 — 2026-10-06
- Fallo observado: el PASS offline no ejecutaba la política de red/CSP.
- Reproducción: introducir un destino prohibido no era rechazado por esa comprobación.
- Causa: falta la llamada desde main(), patrones regex sobreescapados y CSP comprobada mediante subcadenas.
- Corrección: ejecutar la comprobación en el gate, corregir patrones y validar las directivas y fuentes CSP del M0.2 por separado.
- Regresión añadida: pruebas offline del HTML vigente y mutaciones de destinos, CSP y CORS; comprobar que main rechaza una infracción antes de ejecutar Node. Ejecutarlas también en CI.
- Archivos afectados: scripts/check_webgis.py, scripts/test_network_policy.py, .github/workflows/pages.yml, README.md y SKILL_CASTREJON_WEBGIS.md.
- Compatibilidad hacia atrás: sin cambios en index.html, capas, navegación ni servicios. Validación estática de literales; no demuestra ausencia de destinos construidos dinámicamente ni sustituye pruebas de navegador.

### 0.1.7 — 2026-09-30
- Fallo observado: el usuario informa de errores esporádicos y Chrome muestra una solicitud para buscar/conectarse a dispositivos de la red local al abrir el visor.
- Reproducción: revisión de `main`, servicios y último despliegue; no se encuentran `localhost`, IP privadas, dominios `.local`, WebSocket/WebRTC ni `targetAddressSpace`. El visor sólo declara cuatro orígenes HTTPS públicos.
- Causa confirmada en código: ninguna solicitud local intencionada. Riesgo corregible detectado: los WMS forzaban CORS anónimo sin necesitar lectura de píxeles, lo que puede convertir servidores WMS sin CORS suficiente en errores de carga.
- Corrección: retirar `crossOrigin: anonymous` de las fuentes cartográficas; CSP cerrada a los orígenes previstos; aviso de error de runtime no bloqueante.
- Regresión añadida: CI rechaza localhost, IP privadas/link-local, dominios `.local`, `targetAddressSpace`, HTTP no seguro, orígenes remotos no autorizados, ausencia de CSP o reintroducción de CORS anónimo.
- Archivos afectados: index.html, scripts/check_webgis.py, scripts/check-map.cjs, README.md y SKILL_CASTREJON_WEBGIS.md.
- Compatibilidad hacia atrás: capas, CRS, centro/zoom, opacidades e interfaz se conservan. Si Chrome vuelve a pedir acceso local tras este cambio, capturar la petición que lo dispara: no debe concederse el permiso para usar el visor.

### 0.1.6 — 2026-09-29
- Fallo observado: el panel ocupa el ancho móvil al inicio; controles pequeños y elementos inferiores pueden competir con escala/atribuciones. Los sliders usan pasos 0,05 incompatibles con los valores 0,33/0,62.
- Reproducción: abrir el visor con ancho móvil o girar a horizontal; comparar panel, botones y pie.
- Causa: adaptación móvil basada en posiciones absolutas y opacidad SIGPAC sin sincronizar en el contrato.
- Corrección: fijar SIGPAC 0,33 por decisión expresa del usuario; panel plegable accesible, zonas táctiles, pie independiente para lecturas/escala/atribuciones, altura dinámica y áreas seguras. Sliders con paso 0,01.
- Regresión añadida: gate comprueba opacidad SIGPAC 0,33 y coherencia inicial de ambos sliders; revisión visual/manual de tamaños móviles, giro, panel, foco y atribuciones.
- Archivos afectados: index.html, SKILL_CASTREJON_WEBGIS.md, README.md, scripts/check-map.cjs.
- Compatibilidad hacia atrás: servicios, fuentes, CRS, centro/zoom e historial conservados. Sin dependencias nuevas ni cambios de workflow. Reversible mediante revert.

### 0.1.5 — 2026-09-29
- Fallo observado: el workflow empaquetaba y desplegaba sin comprobar regresiones locales.
- Reproducción: un push a main alcanzaba Upload/Deploy sin validación de index.html.
- Causa: las 20 comprobaciones existían sólo como contrato manual.
- Corrección: añadir gate sin dependencias npm/pip, ejecutado en PR, push y ejecución manual; deploy depende de gate y sólo acepta main. Publicar únicamente index.html y .nojekyll.
- Regresión añadida: HTML/JS básico, PNOA XYZ/TMS, SIGPAC TileWMS, Catastro ImageWMS/INSPIRE, vista e Inicio bloqueados, atribuciones configuradas y secretos evidentes en archivos versionados.
- Archivos afectados: SKILL_CASTREJON_WEBGIS.md, README.md, .github/workflows/pages.yml, scripts/check_webgis.py, scripts/check-map.cjs.
- Compatibilidad hacia atrás: index.html y sus valores actuales permanecen intactos; Node/Python sólo se usan en CI/desarrollo. Revertir el commit restaura el workflow previo.
- Observación en 0.1.5: SIGPAC usaba 0,33 en index.html frente a 0,88 en §7; resuelto en 0.1.6 por decisión del usuario a favor de 0,33.

### 0.1.3 — 2026-09-29
- Prueba previa: M0.1 validado por el usuario sin fallos funcionales en navegación, PNOA, Catastro y controles.
- Nueva función: se incorpora Recintos SIGPAC de campaña vigente mediante el WMS oficial `https://sigpac-hubcloud.es/wms`, capa `AU.Sigpac:recinto`, visible por defecto.
- Catastro: se revierte la decisión de 0.1.1 de usar TileWMS. La D.G. del Catastro indica que su WMS clásico no está concebido para peticiones teseladas y recomienda adecuar los visores para peticiones de página completa.
- Corrección: Catastro pasa a ImageWMS sobre el servicio oficial INSPIRE `CP.CadastralParcel`, estilo `CP.CadastralParcel.BoundariesOnly`, para una representación menos intrusiva.
- Marca de agua/atribución: queda prohibido eliminar, recortar o tapar artificialmente marcas o atribuciones suministradas por servicios oficiales. La estrategia permitida es elegir estilos oficiales más limpios y mantener atribución visible.
- Orden de capas M0.2: PNOA (fondo) -> SIGPAC Recintos -> Catastro INSPIRE.
- Estado inicial: SIGPAC visible (0,88); Catastro oculto (0,62 al activar) para reducir solapes.
- Regresión añadida: comprobar carga SIGPAC, opacidad/visibilidad, superposición con PNOA, carga Catastro sólo al activarlo y ausencia de peticiones TileWMS al Catastro.
- Archivos afectados: SKILL_CASTREJON_WEBGIS.md, castrejon_sector4_webgis_m0.html.

### 0.1.2 — 2026-09-29
- Decisión arquitectónica: se formaliza un modelo CRS de tres niveles.
- EPSG:25830 queda fijado como CRS maestro técnico para PostGIS, QGIS, red, parcelas y cálculos métricos.
- EPSG:3857 queda fijado como CRS de visualización web y pirámides de teselas.
- EPSG:4326 queda fijado como CRS de coordenadas de usuario e intercambio.
- Se definen transformaciones canónicas, contrato por componente y regresiones obligatorias.
- Compatibilidad: M0.1 ya usa OpenLayers/PNOA en EPSG:3857 y mantiene el centro inicial expresado en EPSG:4326; no requiere cambio visual.
- Alcance futuro: M1 deberá importar/normalizar la cartografía del Sector IV a EPSG:25830 antes de incorporarla como dato maestro.

### 0.1.1 — 2026-09-29
- Fallo observado: PNOA funcional pero con numerosos errores/recargas durante cada cambio de zoom y sensación de lentitud.
- Reproducción: navegación continua y zoom fraccional sobre M0 con PNOA servido mediante ImageWMS; cada cambio de vista solicitaba una imagen WMS completa nueva.
- Causa: ImageWMS no reutiliza una pirámide de teselas pregeneradas como fondo de navegación; el IGN publica expresamente WMTS/XYZ pregenerado para este producto y recomienda teselas para rendimiento/estabilidad.
- Corrección: PNOA cambia a XYZ/TMS oficial en EPSG:3857; Catastro cambia de ImageWMS a TileWMS.
- Optimización: preload PNOA=2, Catastro=1, teselas intermedias ante error, transición corta y pixelRatio limitado a 2.
- Estado de servicio: eventos tileloadstart/end/error; un fallo aislado no invalida un servicio que ya entrega teselas correctas.
- Regresión añadida: comprobar ausencia de GetMap PNOA durante zoom, continuidad visual con errores aislados y caché efectiva al volver a una vista.
- Compatibilidad: centro, zoom 13.27, escala de referencia, botones, historial y selector permanecen.
- Archivos afectados: SKILL_CASTREJON_WEBGIS.md, castrejon_sector4_webgis_m0.html.

### 0.1.0 — 2026-09-29
- Se consolida la arquitectura acordada.
- Sector IV se fija como piloto.
- Se define el modelo de entidades y relaciones.
- Se define M0 como marco WMS únicamente.
- Se fijan centro, zoom y servicios oficiales iniciales.
- Se adopta este documento como contrato previo a cambios de código.


## 12. Flujo de desarrollo y despliegue — REGLA BLOQUEADA

### 12.1 Separación de responsabilidades
1. **WordPress** = portal institucional, navegación, contenidos y acceso al Área de riego.
2. **castrejon-webgis** = repositorio canónico del frontend cartográfico.
3. **GitHub Pages** = alojamiento estático del visor mientras no exista backend propio.
4. **Servicios externos oficiales** = PNOA, SIGPAC y Catastro se consumen directamente desde sus servicios publicados.
5. **Backend futuro** = FastAPI + PostgreSQL/PostGIS; no se simula ni se sustituye con WordPress o GitHub Pages.

### 12.2 Flujo obligatorio de una modificación
`incidencia/necesidad -> actualizar skill si cambia una regla -> modificar código local -> prueba local -> commit Git -> despliegue Pages -> prueba remota -> enlazar/validar desde WordPress -> registrar regresión si falla`.

No se editará el visor operativo directamente dentro de WordPress. La fuente canónica es el repositorio.

### 12.3 Estructura mínima del repositorio
- `index.html`: visor M0.x durante la fase estática.
- `.nojekyll`: evita tratamiento Jekyll innecesario.
- `.github/workflows/pages.yml`: despliegue reproducible a GitHub Pages.
- `README.md`: estado, capas y pasos de despliegue.
- `SKILL_CASTREJON_WEBGIS.md`: contrato de arquitectura y registro de decisiones.

Cuando el frontend migre a React/TypeScript, `index.html` dejará de ser la fuente de edición y se generará mediante build; la URL pública debe mantenerse siempre que sea posible.

### 12.4 GitHub Pages
- Rama canónica: `main`.
- Despliegue: GitHub Actions -> Pages.
- Cada push validado a `main` genera una nueva publicación.
- WordPress enlaza a la URL pública; no copia el JavaScript ni los WMS.
- GitHub Pages sólo aloja frontend estático. No alojará PostGIS, FastAPI, GeoServer, telemetría ni procesos hidráulicos.

### 12.5 Capas propias durante las primeras pruebas
Para pruebas pequeñas puede incorporarse GeoJSON estático versionado en el repositorio. SHP/GML/GPKG son formatos de entrada, no el formato web definitivo. Antes de publicar una capa interna:
`SHP/GML/GPKG -> validar QGIS -> comprobar CRS -> normalizar maestro EPSG:25830 -> validar atributos/topología -> exportación de prueba GeoJSON/MVT o carga futura en PostGIS`.

Nunca subir a un repositorio público datos personales, credenciales, telemetría sensible o cartografía interna que deba quedar restringida.

### 12.6 Prueba de despliegue
Tras cada publicación remota comprobar como mínimo:
- carga inicial del visor;
- PNOA;
- SIGPAC;
- Catastro;
- zoom/pan/historial;
- consola del navegador sin errores bloqueantes;
- móvil;
- enlace WordPress -> visor;
- que el origen remoto no rompe CORS/CSP.

### 12.7 Criterio de regresión
Se considera regresión cualquier cambio que haga funcionar una capa localmente pero no en Pages, que obligue a volver a incrustar el visor en WordPress, que altere la arquitectura CRS, o que mezcle frontend estático con datos/secretos que exijan backend.

### Registro 2026-09-29 · v0.1.4
- Decisión: separar definitivamente el visor operativo de WordPress.
- Motivo: los WMS no se visualizaron de forma fiable al ejecutar el visor dentro del contexto de WordPress.
- Solución: repositorio canónico `castrejon-webgis` + GitHub Pages; WordPress sólo enlaza.
- M0.2 se prepara como `index.html` estático y se añade workflow reproducible de Pages.
