# Retención acotada de Sentinel y continuidad de Pages

**Cierre verificado el 16/11/2026 de las PR #12 y #13.** El SHA desplegado es
[`009105ddf226c38dddabb79c9109a7820c36f075`](https://github.com/julianladera-droid/castrejon-webgis/commit/009105ddf226c38dddabb79c9109a7820c36f075).
La retención configurada sigue en **8**; hay **cuatro adquisiciones y tres
comparaciones**. La propuesta original partió de `07ad34999da36e1b2b849b6fd909e40f2d55528f`.
Este cierre sólo actualiza documentación y evidencia JSON: no cambia configuración,
código ni workflows, no genera otro despliegue y no borra artefactos ni cachés.

## Cierre de las PR y despliegue

| Hito | Evidencia y resultado |
| --- | --- |
| [PR #12](https://github.com/julianladera-droid/castrejon-webgis/pull/12) | Fusionada el 16/11/2026 a las 20:23:43 UTC en `ee2700943fc83e584ef97555fe3c219eb7c6a659`. [CI correcta](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/43946762025): 116 pruebas Python y controles WebGIS/WordPress; deploy omitido por ser PR. |
| [Primer despliegue](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/43949328931) | Falló **antes del upload** con `Unexpected public band source`: agosto de 2023 usa el prefijo histórico CDSE `L2A_N0500/`. El HTML, catálogo y registro publicados conservaron sus bytes. |
| [PR #13](https://github.com/julianladera-droid/castrejon-webgis/pull/13) | Corrección mínima del prefijo histórico, manteniendo las restricciones de URL. Fusionada a las 20:30:53 UTC en `009105ddf226c38dddabb79c9109a7820c36f075`. [CI correcta](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/43950164441): 117 pruebas Python, WebGIS y WordPress; deploy omitido. |
| [Despliegue final de Pages](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/43950559764) | Correcto sobre `009105ddf226c38dddabb79c9109a7820c36f075`: cuatro observaciones, tres comparaciones y retención `4/8`. Sitio de **142.802.154 / 400.000.000 bytes**. Artefacto Pages `14267602459`, de 140.979.842 bytes. |

El [visor](https://julianladera-droid.github.io/castrejon-webgis/),
[catálogo](https://julianladera-droid.github.io/castrejon-webgis/sentinel/catalog.json),
[registro](https://julianladera-droid.github.io/castrejon-webgis/sentinel/publication.json)
e [índice de recuperación](https://julianladera-droid.github.io/castrejon-webgis/sentinel/recovery.json)
son URLs vivas y pueden cambiar en publicaciones futuras. La
[evidencia versionada del cierre](sentinel-evidence/closure-20261116.json)
fija los IDs, fechas UTC, versiones, tamaños, SHA-256, procedencia y resultados
comprobados entonces, sin incluir ZIP, rásteres, credenciales ni rutas locales.

## Recuperación comprobada de las cuatro adquisiciones

| Observación UTC | Producto | Versión original → validada | ZIP de recuperación (bytes) |
| --- | --- | --- | ---: |
| 16/08/2023 | `S2A_MSIL2A_20230816T105631_N0510_R094_T30TUK_20241021T044404` | 2 → 3 | 17.507.379 |
| 14/10/2026 | `S2A_MSIL2A_20261014T110941_N0513_R137_T30TUK_20261014T173008` | 2 → 3 | 18.119.802 |
| 31/10/2026 | `S2A_MSIL2A_20261031T110121_N0513_R094_T30TUK_20261031T173605` | 2 → 3 | 17.999.349 |
| 06/11/2026 | `S2B_MSIL2A_20261106T111149_N0513_R137_T30TUK_20261106T132030` | 3 → 3 | 17.987.696 |

La restauración y validación local quedó registrada el **16/11/2026 a las 20:34:58 UTC**. El colector
de producción restauró los cuatro paquetes desde Pages en un directorio aparte,
simulando una lista de artefactos vacía. No se usó caché ni se consultó CDSE;
no se borraron artefactos para simular caducidad. Se conservaron las huellas
originales de los cuatro productos y se verificaron las **24 bandas DN**,
su identidad, rejilla y CRS EPSG:25830.

Los **20 índices originales recuperados** coinciden por SHA-256 con los del
catálogo publicado. Los tres productos v2 se migraron localmente a v3:
sus **15 índices recalculados** conservan exactamente los píxeles, rejillas y
nodata; los cinco índices del producto v3 se conservaron. Las huellas binarias
de los GeoTIFF regenerados difieren entre los entornos GDAL local **3.10.2**
y Pages **3.12.2**. No se acredita reproducción binaria entre entornos ni se
comprobó igualdad píxel a píxel de `WATER` regenerado frente al publicado.

También se verificaron por SHA-256 **15 recursos públicos**: tres comparaciones
y, para cada fecha, índices parcelarios, tabla de agua y geometrías de agua.
En el navegador cargaron las cuatro fechas y la comparación NDVI
16/08/2023 → 14/10/2026, sin errores de consola. La captura de pantalla agotó
el tiempo disponible; no se conserva evidencia gráfica de esa comprobación.

Los inventarios de la comprobación conservaron los **30 artefactos previos**
con las mismas caducidades; pasaron a 34 por los controles y el nuevo paquete
Pages. La caché siguió siendo `10554333159`, de **18.021.251 bytes**.
Estas cifras son evidencia fechada del cierre, no una promesa sobre inventarios
futuros sujetos a su caducidad normal. No se solicitó una nueva escena Sentinel:
se reconstruyó desde los DN ya conservados.

## Política operativa

[`data/sentinel-retention.json`](../data/sentinel-retention.json) fija un **máximo
de 8, 6 o 4 días de observación**. El valor **activo y mantenido en este cierre
es 8**; no implica que deban existir ocho productos. Tener menos adquisiciones
válidas no impide publicar.
No hay vencimiento por antigüedad del último conjunto útil. La fecha de ejecución
de un backfill no convierte una observación antigua en reciente.

Por cada día UTC se elige el instante de observación más reciente; a igualdad
de instante, mayor baseline `N####`, versión de producto e ID. Sólo para revisiones
del mismo producto interviene después la fecha de creación del artefacto.
La selección es independiente del orden de respuesta de la API.

| Modo | Observaciones máximas | Comparaciones adyacentes máximas | Uso sugerido |
| --- | ---: | ---: | --- |
| Normal | 8 | 7 | Margen disponible y necesidad de contexto temporal |
| Reducido | 6 | 5 | Menor almacenamiento o transferencia |
| Mínimo | 4 | 3 | Priorizar continuidad con el menor histórico solicitado |

### Cómo bajar a 6 o 4 en una operación futura

La configuración actual, que **esta PR no modifica**, es:

```json
{
  "version": 1,
  "max_acquisitions": 8,
  "max_site_bytes": 400000000
}
```

1. En una rama nueva desde `main` actualizado, cambiar **sólo**
   `max_acquisitions` a **6** o **4**. Mantener `version: 1` y
   `max_site_bytes: 400000000`.
2. Abrir una PR de configuración y superar las pruebas de retención/recuperación
   y los controles habituales de CI. La transición 8→6→4 ya tiene regresiones
   sintéticas; no simularla borrando datos de producción ni saltarse CI.
3. **Fusionar sólo cuando se autorice su publicación.** El workflow actual de
   Pages se activa con un `push` a `main`: construye, valida y, si todo pasa,
   despliega automáticamente. Una PR sin fusionar no cambia el sitio ni el límite
   activo. No hace falta ejecutar Sentinel ni crear una adquisición para cambiar
   la política.
4. Tras ese despliegue autorizado, comprobar que `recovery.json.retention`
   coincide con el valor elegido, que catálogo, registro y paquetes contienen
   las mismas fechas y que hay como máximo N observaciones y N−1 comparaciones.
   Si falla cualquier validación o el presupuesto, conservar el sitio anterior.

No se infiere el plan de GitHub ni se cambia de modo por una consulta fallida a
métricas. El límite de tamaño del sitio completo es
**400.000.000 bytes**; sobrepasarlo detiene la preparación antes de subir Pages.
No se publica una colección parcialmente validada para ajustarse a ese límite.

Al desplegar posteriormente un cambio 8→6→4, el nuevo paquete contendrá sólo
esas fechas, sus comparaciones y sus paquetes de recuperación. Los excedentes
dejarán de estar disponibles en el sitio tras ese despliegue. No se llama a
ninguna API de borrado. Volver a 8 no recupera por sí solo fechas ya ausentes
tanto del sitio como de Actions; requerirán una copia externa o Sentinel manual.
Con las **cuatro fechas actuales**, pasar a 6 o 4 no retiraría ninguna de ellas;
sí limitaría el crecimiento posterior. La retención por número de adquisiciones
es distinta de los 14 días de los nuevos artefactos intermedios: cambiar una no
reescribe la caducidad de los artefactos existentes ni elimina cachés.

## Flujo y garantías

1. La selección STAC se escribe en `sentinel-selection/`, fuera de la caché.
2. La clave incluye las dependencias Python locales, AOI, Python, NumPy y GDAL.
   El recorrido de imports incluye `field_water.py` y `water_sharpening.py`.
   Se comprueban ID, observación, AOI, parámetros, calibración, huellas y rásteres
   antes de aceptar una entrada. Caché inválida o ausente: recalcular.
   Restaurar y guardar son pasos separados; sólo se guarda tras validar.
   La clave por intento permite sustituir en la práctica una entrada corrupta
   inmutable, sin borrarla. No se crea otra caché si la restaurada es válida.
3. El producto validado se sube como `sentinel-<run_id>-<attempt>`, con 14 días
   de retención. El lector sigue aceptando los nombres históricos sin intento.
   Los artefactos existentes conservan su vencimiento actual. Los diagnósticos
   siguen separados y nunca son candidatos de publicación.
4. El colector pagina **artefactos del repositorio**, sin depender del límite de
   1.000 resultados de ejecuciones filtradas. Verifica repositorio, rama main,
   workflow, evento y éxito del run, SHA-256 del ZIP y archivos permitidos.
   Ignora versiones no migrables; un producto compatible corrupto detiene el proceso.
5. Mezcla los candidatos de Actions con el índice del sitio publicado. Sólo
   descarga de Pages los paquetes que finalmente quedan seleccionados; los
   artefactos ya representados por su ID no se vuelven a descargar de Actions.
   La selección de fechas precede a la migración y a la construcción del catálogo.
6. Migra v2→v3 desde DN cuando corresponde, aplica la validación geoespacial
   existente y construye hasta N−1 comparaciones. No se mezcla el detector v2
   con el v3 publicado, ni se genera una matriz de N² comparaciones.
7. Genera `publication.json` con las huellas de los productos originales y
   `recovery.json` con hashes del catálogo, registro y paquetes. Comprueba
   pertenencia exacta, orden, retención, integridad y tamaño antes del upload.
8. Catálogo, imágenes, tablas, registro y recuperación viajan en el **mismo
   despliegue de Pages**. Un fallo de preparación no sustituye el sitio anterior.
   Se conserva la serialización y la segunda comprobación del cambio de producto.

Los eventos de calendario sin procesamiento siguen omitiendo los trabajos
costosos. Un histórico anterior a una ventana ya llena también omite la
reconstrucción. PRs nunca entran en `deploy`; no se añaden permisos de escritura
en contenidos ni Releases.

## Qué se conserva y cómo se restaura

Cada paquete `sentinel/recovery/<sha256>.zip` contiene los seis recortes DN
B03/B04/B08 a 10 m, B8A/B11/SCL a 20 m, cinco índices, SCL, WATER,
WATER_QUALITY y un manifiesto técnico depurado. Incluye escala, offset, nodata,
CRS, AOI, parámetros, hashes e identificación de los objetos CDSE originales.
No es el SAFE completo: no incorpora todas las bandas, teselas, XML SAFE ni
catálogo del proveedor. No habilita análisis fuera del AOI o con bandas ausentes.

Los paquetes son **públicos**, como los índices del visor. Se excluyen consulta,
auditoría privada y catálogo completo. La identidad de contenido original se
mantiene después de depurar el manifiesto. El índice conserva run, artefacto,
SHA del código y fecha de creación del artefacto; esta última es fecha de
empaquetado y puede proceder de una reutilización de caché, no necesariamente
del cálculo inicial. Los nuevos productos incluyen además huella de dependencias
y versiones del entorno; ese dato es desconocido para los históricos que no lo
registraron. El código queda referenciado por commit, no duplicado en cada ZIP.

Sin artefactos ni caché, el colector restaura desde Pages y verifica cada paquete
antes de extraer exclusivamente los archivos permitidos. No consulta Copernicus
para esta restauración. ZIP ≤100 MB, manifiesto ≤1 MB y producto expandido
≤200 MB; ni rutas externas ni miembros duplicados son aceptados.

Durante la primera instalación, un `recovery.json` inexistente exige recuperar
de Actions las fechas del registro publicado que entren en la política elegida.
Si falta una de ellas, falla antes de desplegar: no convierte una caducidad
parcial en una reducción silenciosa del catálogo. HTTP 403/429/5xx, errores de
red, JSON inválido o hashes distintos también detienen el intento. Un fallo de
Actions puede impedir una actualización, pero el sitio anterior sigue servido.

Esta solución evita la dependencia exclusiva de artefactos caducables, **no es
una copia de seguridad independiente de Pages**. Si desaparece todo el sitio y
también sus artefactos, habrá que recuperar del proveedor o de una copia externa.
Es una limitación deliberada para mantener pequeño el sistema y su histórico.

## Recursos: mediciones y estimaciones

En la auditoría del 16/11/2026 había cuatro productos recuperables v2/v3:
16/08/2023, 14/10/2026, 31/10/2026 y 06/11/2026. Sus ZIP de Actions sumaban
71.671.520 bytes; cada producto expandido ocupaba 17,75–18,36 MB, con
5,95–6,37 MB de DN. El contenido del sitio observado rondaba 71,18 MB.
La descarga/cálculo real del 15/11 duró 174 s en sus logs. No se repite aquí.

Mediciones de la aceptación posterior, con **retención 8 y cuatro productos**:

| Recurso | Medición y alcance |
| --- | ---: |
| Sitio completo en el runner | 142.802.154 bytes, frente al guard de 400.000.000 |
| Cuatro ZIP descargados desde Pages | 71.614.226 bytes |
| Descarga de restauración total, incluidos tres JSON | 71.644.668 bytes |
| Restauración local | 9,186 s |
| Restauración más validación/migración local | 13,694 s |
| Pico de memoria del proceso local | 198.254.592 bytes |
| Originales restaurados más productos v3 locales | 143.697.484 bytes de disco |

Los tiempos, memoria y disco locales no son máximos del runner de Actions ni
mediciones de todo el despliegue. No incluyen el navegador, sistema, checkout,
dependencias ni empaquetado de Pages. La descarga total no incluye el tráfico
de la comprobación independiente de tablas ni el de usuarios.

| Modo | Sitio con paquetes, estimación | Recuperación desde Pages por construcción, estimación |
| --- | ---: | ---: |
| 8 | ≈286 MB | ≤144 MB |
| 6 | ≈214 MB | ≤108 MB |
| 4 | ≈143 MB | ≤72 MB |

Son extrapolaciones para **llenar cada ventana**, no mediciones de colecciones
reales de seis u ocho productos ni límites garantizados. El valor medido de
142,8 MB corresponde a cuatro productos con la configuración aún en 8; no se
probó el modo 4 en producción. El empaquetado depurado puede variar. Los ZIP
de recuperación no se cargan al abrir el visor; sólo se transfieren al solicitarlos
o al reconstruir el sitio. Hay que sumar artefactos nuevos/no reconocidos,
upload del sitio y tráfico de usuarios. Veinte reconstrucciones con ocho
paquetes supondrían alrededor de 2,9 GB de descarga de recuperación.

El disco temporal contiene candidatos seleccionados, originales, copias migradas,
sitio y empaquetado de Pages: orden de 1–2 GB para ocho AOI como los observados,
sin contar sistema, dependencias y checkout. La memoria máxima y duración del
empaquetado en Actions no se han perfilado; las cifras locales anteriores sólo
cubren la restauración y validación de cuatro productos. No se presentan los
tamaños de JP2 completos como transferencia
S3 medida: las lecturas de recortes usan rangos y no se midió su tráfico real.

GitHub documenta [1 GB por sitio, timeout de despliegue de 10 minutos y límite
blando de transferencia de 100 GB/mes](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).
El guard de 400 MB reserva margen pero no comprueba consumo mensual. El plan
real, la facturación y el tráfico mensual del propietario no fueron accesibles;
no se afirma que sean cero ni que el almacenamiento restante esté garantizado.
Si aparecen costes o presión de recursos, revisar los tamaños registrados y
pasar primero a 6, después a 4; no activar una limpieza automática de datos.

## Pruebas y aceptación

La suite Python ejecuta fixtures sintéticos sin credenciales, STAC ni descarga
real: caducidad total/parcial, primer arranque incompleto, 1.100 artefactos
irrelevantes antes del histórico, baselines, backfills, 8→6→4, una sola adquisición
antigua, caché ausente/corrupta/incompatible, dependencias, parámetros, calibración,
manifiestos depurados, ZIP duplicado/corrupto, presupuesto excedido y fallos de red.
Una integración restaura DN v2, recalcula v3 y reproduce el catálogo. Otra construye
rásteres, agua temporal y comparaciones reales para 8/6/4 fechas con una parcela
sintética; sustituye sólo la tabla parcelaria completa, validada por otras pruebas.
También comprueba igualdad de catálogo/registro/paquetes, hashes de comparaciones
y que el sitio anterior conserva sus bytes cuando falla la preparación.

Se mantuvieron las pruebas de calendario y publicación de PR #10, las nueve
suites Node, gate WebGIS, política de ubicación, integración WordPress y
actionlint. PR #12 aprobó 116 pruebas Python; la regresión del prefijo histórico
en PR #13 elevó el total a 117. La CI de ambas PR omitió `deploy`; el despliegue
autorizado y la recuperación real se verificaron después, según las evidencias
de este cierre. No se confunden los fixtures sintéticos con esa aceptación real.

Esta PR documental conserva los resultados de aquella comprobación; no repite
el procesamiento, las descargas ni el despliegue. Para una aceptación futura,
restaurar en un directorio aparte y verificar el índice antes de sustituir el
sitio. No borrar artefactos ni cachés para simular su ausencia.
