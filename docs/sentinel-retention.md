# Retención acotada de Sentinel y continuidad de Pages

Propuesta sobre `main` **07ad34999da36e1b2b849b6fd909e40f2d55528f**,
revisado el 16/11/2026. Preparar esta PR no ejecuta Sentinel, no publica Pages
ni elimina artefactos, cachés, Releases o adquisiciones existentes.

## Política operativa

`data/sentinel-retention.json` fija un **máximo de 8, 6 o 4 días de observación**.
El valor inicial es 8; tener menos adquisiciones válidas no impide publicar.
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

El cambio es explícito y versionado: editar únicamente `max_acquisitions`, pasar
CI y revisar la PR. No se infiere el plan de GitHub ni se cambia de modo por una
consulta fallida a métricas. El límite de tamaño del sitio completo es
**400.000.000 bytes**; sobrepasarlo detiene la preparación antes de subir Pages.
No se publica una colección parcialmente validada para ajustarse a ese límite.

Al desplegar posteriormente un cambio 8→6→4, el nuevo paquete contendrá sólo
esas fechas, sus comparaciones y sus paquetes de recuperación. Los excedentes
dejarán de estar disponibles en el sitio tras ese despliegue. No se llama a
ninguna API de borrado. Volver a 8 no recupera por sí solo fechas ya ausentes
tanto del sitio como de Actions; requerirán una copia externa o Sentinel manual.

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

| Modo | Sitio con paquetes, estimación | Recuperación desde Pages por construcción, estimación |
| --- | ---: | ---: |
| 8 | ≈286 MB | ≤144 MB |
| 6 | ≈214 MB | ≤108 MB |
| 4 | ≈143 MB | ≤72 MB |

Son extrapolaciones de aquellos cuatro AOI, no mediciones de un despliegue de
esta PR ni límites garantizados. El empaquetado depurado puede variar. Los ZIP
de recuperación no se cargan al abrir el visor; sólo se transfieren al solicitarlos
o al reconstruir el sitio. Hay que sumar artefactos nuevos/no reconocidos,
upload del sitio y tráfico de usuarios. Veinte reconstrucciones con ocho
paquetes supondrían alrededor de 2,9 GB de descarga de recuperación.

El disco temporal contiene candidatos seleccionados, originales, copias migradas,
sitio y empaquetado de Pages: orden de 1–2 GB para ocho AOI como los observados,
sin contar sistema, dependencias y checkout. La memoria máxima y duración del
nuevo empaquetado no se han perfilado con adquisiciones reales; las pruebas usan
rásteres pequeños. No se presentan los tamaños de JP2 completos como transferencia
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

Se mantienen las pruebas de calendario y publicación de PR #10, las nueve suites
Node, gate WebGIS, política de ubicación, integración WordPress y actionlint.
CI de la PR valida código y fixtures; omite el despliegue. No acredita todavía
un upload o recuperación real del nuevo formato en producción.

Después de una eventual autorización para integrar/desplegar: verificar las
cuatro fechas actuales, hashes del índice, tamaños, comparación entre fechas y
descarga de un paquete. Probar restauración en un directorio aparte sin caché,
registrando duración y pico de memoria/disco. No borrar los artefactos existentes
para simular caducidad. Mantenerlos hasta comprobar el primer sitio con recuperación.
