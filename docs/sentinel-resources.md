# Recursos Sentinel: retención en 4 y cierre de PR #15

**Estado verificado el 18/11/2026:** retención activa **4**, cuatro adquisiciones y
tres comparaciones. SHA desplegado:
[`196ff99757a37a17260d4c62c05317b6ab89a149`](https://github.com/julianladera-droid/castrejon-webgis/commit/196ff99757a37a17260d4c62c05317b6ab89a149).
La [PR #15](https://github.com/julianladera-droid/castrejon-webgis/pull/15) está fusionada;
este cambio sólo documenta su aceptación. No modifica configuración, código ni
workflows, ni autoriza otra publicación o una limpieza.

La [PR #14](https://github.com/julianladera-droid/castrejon-webgis/pull/14) queda
sustituida por este cierre, **sin fusionar su texto de retención activa en 8**.
Se incorpora sin cambios su [evidencia del 16/11](sentinel-evidence/closure-20261116.json)
y se conserva el [cierre histórico de #12/#13](sentinel-retention.md). Los valores
8 y el SHA `009105d…` describen aquella etapa, no la configuración vigente.

## Despliegue y recuperación comprobados

| Hito | Evidencia y resultado |
| --- | --- |
| PR #15 | Fusionada el **17/11/2026 a las 21:17:07 UTC** en `196ff99757a37a17260d4c62c05317b6ab89a149`. [CI de la PR](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/44171789503) correcta: 136 pruebas Python, WebGIS y WordPress; deploy omitido por ser PR. |
| [Pages, intento 1](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/44178192078/attempts/1) | `TimeoutError` al leer un paquete de Pages tras 60 s. Falló **antes del upload**; el índice anterior conservó exactamente su SHA-256. No hubo cambio de código ni borrados para reintentar. |
| [Pages, intento 2](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/44178192078/attempts/2) | Correcto sobre el SHA fusionado. Publicó **4/4**, tres comparaciones y un sitio de **142.802.734 / 400.000.000 bytes**. |
| Aceptación | Recuperación real registrada el **17/11 a las 21:23:01 UTC**; cierre de comprobaciones a las **21:23:38 UTC**. [Evidencia versionada](sentinel-evidence/closure-20261117.json). |

Se restauraron desde Pages las fechas **16/08/2023, 14/10/2026, 31/10/2026 y
06/11/2026**, usando el colector con inventario de artefactos simulado vacío,
sin caché ni CDSE. No se borraron datos para simular esa ausencia. Se verificaron
cuatro huellas originales, **24 bandas DN** (identidad, rejilla y EPSG:25830),
**20 índices originales por SHA-256** y **15 recursos públicos** por hash
(tres comparaciones y las tablas/zonas por adquisición).

Los tres productos v2 se migraron localmente desde DN: sus **15 índices
recalculados** coincidieron exactamente en píxeles, rejilla y nodata. Los cinco
índices del producto v3 se copiaron y validaron. Los GeoTIFF regenerados tienen
hashes binarios diferentes entre GDAL local 3.10.2 y Pages 3.12.2; no se afirma
reproducción binaria entre entornos. La igualdad píxel a píxel del WATER regenerado
no se comprobó. En navegador cargaron las cuatro fechas, NDVI y la comparación
16/08/2023 → 14/10/2026, sin errores de consola; no se adjunta una captura gráfica.

Los **29 artefactos previos** mantuvieron presencia y caducidades; el inventario
pasó a 33 por los resultados de los jobs. La caché `10554333159` conservó clave,
versión y tamaño de **18.021.251 bytes**. No se invocó la limpieza; el workflow
tenía cero ejecuciones y no existía registro de bajas. Son mediciones fechadas,
no promesas sobre la caducidad normal posterior.

| Medida del cierre #15 | Valor y alcance |
| --- | ---: |
| Cuatro ZIP de recuperación | 71.614.226 bytes |
| Descarga local, incluidos los tres JSON | 71.645.026 bytes |
| Restauración local / con validación y migración | 10,380 s / 15,606 s |
| Pico de memoria del proceso local | 196.423.680 bytes |
| Originales y productos v3 locales | 143.700.127 bytes de disco |
| Etapas del runner: colección / migración / construcción / recuperación | 6,576 / 2,554 / 33,499 / 2,537 s |
| Máximo RSS muestreado entre esas etapas | 260.374.528 bytes |
| Máximo disco de trabajo muestreado entre esas etapas | 269.033.902 bytes |

Los picos del runner se muestrean cada 0,5 s: no son máximos absolutos del job,
ni incluyen necesariamente checkout, dependencias y empaquetado. La construcción
incluye las comparaciones; no se midió su tiempo aislado. Las cifras locales
corresponden a otro entorno y no se intercambian con las del runner.

El **18/11 a las 20:11:59 UTC** se releyeron sólo los tres JSON públicos: catálogo,
recibo e índice siguen byte a byte iguales a la aceptación y anuncian retención 4.
El historial de limpieza sigue vacío. La ejecución programada
[44324222136](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/44324222136)
fue satisfactoria con `sentinel` omitido; el workflow derivado
[44324279328](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/44324279328)
también omitió `deploy`. **Queda pendiente observar el ciclo completo con una
adquisición nueva**; una comprobación de calendario no demuestra ese procesamiento.

## Auditoría y simulación anteriores a la fusión (17/11)

Este apartado conserva las cifras de la propuesta, sobre base
`009105ddf226c38dddabb79c9109a7820c36f075`, cuando la retención aún era 8. No son
inventarios actuales ni una limpieza ejecutada. El estado posterior figura arriba.

Inventario paginado consultado el **17/11/2026 a las 20:21:45 UTC**:
[respuesta API y catálogo](sentinel-evidence/resource-inventory-20261117.json),
[plan exacto reproducible](sentinel-evidence/resource-plan-20261117.json),
[tiempos y recuperación anterior](sentinel-evidence/resource-runtime-20261117.json).
Las cinco revisiones históricas se identifican en
[`data/sentinel-legacy-products.json`](../data/sentinel-legacy-products.json):
sus ZIP locales, descargados durante la auditoría anterior, tienen el mismo SHA256
que el inventario de aquella auditoría. Para este cierre documental no se han
vuelto a descargar rásteres ni repetido procesamientos.

| Observación UTC | Esquema original | Artefacto recuperable / bytes | Paquete Pages / bytes | DN del AOI / bytes |
| --- | ---: | --- | ---: | ---: |
| 2023-08-16 10:56:31 | 2 | 13091783958 / 17.521.763 | 17.507.379 | 5.950.633 |
| 2026-10-14 11:09:41 | 2 | 13091469469 / 18.134.025 | 18.119.802 | 6.371.358 |
| 2026-10-31 11:01:21 | 2 | 13091902423 / 18.013.574 | 17.999.349 | 6.257.884 |
| 2026-11-06 11:11:49 | 3 | 14161964706 / 18.002.158 | 17.987.696 | 6.258.202 |

Los IDs SAFE completos, huellas, hashes ZIP, localizaciones, caducidades y SHA de
origen están en los JSON enlazados. Las cuatro contienen B03/B04/B08 a 10 m y
B8A/B11/SCL a 20 m, calibración escala/offset/nodata, identidad y rejilla.
El visor usa v3; los tres originales v2 se migran desde DN. La revisión antigua
13081044459 del 31/10 ocupa 7.620.037 bytes, carece de DN y no es restaurable bajo
el contrato actual. Su identificador de revisión es el SHA256 del ZIP, no una
huella del contrato v3. Los originales expandidos ocupan 17,75–18,36 MB cada uno.

La simulación conservaba exactamente esas cuatro fechas, incluidas agosto de
2023 y octubre de 2026. Son también las cuatro verificadas después del despliegue.
No se selecciona por fecha de ejecución ni por antigüedad administrativa.

| Servicio | Medido en la auditoría previa | Eliminación propuesta | Ahorro simulado |
| --- | ---: | --- | ---: |
| Actions, todos los artefactos | 29 / 226.483.635 B | Sólo `sentinel-41301408957`, ID 13081044459, revisión antigua del 31/10 | 7.620.037 B |
| Cachés | 1 / 18.021.251 B | ID 10554333159, clave `sentinel-v2-…-S2B_MSIL2A_20261106…`, rama main | 18.021.251 B |
| Releases | 0 | Ninguna | 0 B |
| Pages | 142.802.154 B preparados en el despliegue verificado | Ninguna fecha del conjunto actual | 0 B |

Total recuperable estimado entonces en los dos servicios de Actions: **25.641.288 bytes**. No es
ahorro de transferencia ni de minutos ya consumidos. Tras ese plan quedarían
218.863.598 B de artefactos y cero bytes en esa caché. Los otros artefactos,
incluidos WordPress y `github-pages`, quedan protegidos. La variación respecto al
inventario del día 16 no demuestra un borrado manual: sólo acredita el estado
visible en cada consulta. No se borró ninguno. Antes de cualquier baja futura
debe regenerarse el plan: esta simulación no refleja cambios ni caducidades posteriores.

Las cuatro copias independientes en Actions suman 71.671.520 B y sus paquetes
Pages 71.614.226 B. No tienen una retención indefinida: Actions conserva las
caducidades indicadas por la API; Pages conserva sus paquetes mientras esa
generación siga publicada. Los nuevos productos e índices de selección caducan
a los 14 días; métricas y planes, a los 7 días. La caché sigue siendo prescindible.

Último Sentinel programado observado en aquella auditoría:
[44106648670](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/44106648670),
17/11 a las 14:45:42 UTC, satisfactorio; `calendar` terminó y `sentinel` quedó
`skipped`. Es una comprobación sin procesamiento, no una adquisición nueva.
El cron solicita revisión diaria a las 05:30 UTC; la hora efectiva puede diferir.
El calendario mantiene el ciclo ya definido (15 y cada tres días).

Despliegue anterior, correspondiente al cierre #12/#13:
[43950559764](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/43950559764),
16/11: colección 9 s, instalación 14 s, preparación conjunta 32 s, subida 5 s,
deploy 7 s. Los 32 s incluyen pruebas, migración, comparación y empaquetado;
no permiten atribuir tiempos individuales fiables. El artefacto Pages ocupó
140.979.842 B. Observación más reciente: **06/11**; procesamiento de esa adquisición:
**15/11**; publicación de esta generación: **16/11**. Son fechas distintas.

La recuperación real del 16/11, sin caché/Actions/CDSE, midió 71.644.668 B de
descarga incluidos tres JSON, 9,186 s de restauración y 13,694 s con migración;
198.254.592 B de máximo de memoria del proceso local y 143.697.484 B de archivos
locales originales más migrados. No equivalen al pico de RAM/disco del runner.
Los 24 DN y 20 índices originales se verificaron por hash; los 15 índices v2
recalculados coincidieron en píxeles/rejilla/nodata. GDAL local 3.10.2 frente a
3.12.2 en Pages puede producir GeoTIFF binariamente distintos. No se afirma
igualdad píxel a píxel del WATER regenerado. La comprobación posterior de #15
se documenta por separado al principio de esta guía.

**Desconocido:** plan real/facturación del propietario, consumo de otros repositorios
y Packages, transferencia mensual de Pages, bytes reales de lecturas S3 por rango,
picos anteriores a la instrumentación del runner y tiempo aislado de comparación. Las cuotas no se
deducen de una consulta fallida ni de que el repositorio sea público.

## Presupuestos vigentes tras #15

Configuración versionada: [`sentinel-retention.json`](../data/sentinel-retention.json).
Las unidades son bytes decimales, segundos y cuentas, no GB-hora facturados.

| Recurso | Valor | Aplicación |
| --- | ---: | --- |
| Observaciones | 4, ampliables a 6 u 8 | Una variante por día UTC; mínimo cuatro o todas si hay menos |
| Pages completo | 400 MB, objetivo 80% | Estimación antes de descargar, medida real antes de subir |
| Base pública estimada | 30 MB | Margen para cartografía estática, catálogo y tablas |
| Adquisición sin medida pública | 40 MB | Estimación conservadora; la generación publicada ya registra `public_bytes` |
| Actions artefactos del repositorio | 450 MB | Incluye contenidos ajenos protegidos y próxima subida; éstos nunca se borran |
| Caché | 200 MB | Se omite guardar el acelerador si no cabe; no bloquea por sí solo la publicación |
| Releases opcionales | 200 MB | Referencia de revisión; no existe productor de Releases ni baja automática de assets desconocidos |
| Transferencia de paquetes por colección | 300 MB, objetivo 80% | Antes de GET de rásteres; generación previa sólo si queda margen |
| Trabajo temporal | 2 GB | Reserva previa y muestreo durante etapas; se suma 1 GB libre de seguridad |
| RSS de grupo de procesos | 1,5 GB | Muestreo Linux cada 0,5 s; termina la etapa si supera el límite |
| Etapa de cálculo/preparación | 420 s | Más timeout de job: Sentinel 30 min; Pages/limpieza 10 min |

Son límites operativos conservadores, **no cuotas garantizadas de la cuenta**.
450 MB deja 50 MB respecto a los 500 MB de artefactos de Free, pero otros
repositorios/Packages podrían consumir ese margen: ajustar tras consultar Billing.
Los límites de cuenta no se pueden asegurar con el inventario de este repositorio.

Referencias oficiales consultadas el 17/11/2026:

- [Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits):
  sitio máximo 1 GB, ancho de banda blando 100 GB/mes y timeout de deploy 10 min.
  El límite blando de 10 builds/h no se aplica al workflow Actions personalizado.
- [Facturación de Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions):
  runners estándar públicos gratuitos; almacenamiento de artefactos compartido
  con Packages, cachés separadas con 10 GB/repositorio. El consumo acumulado no
  desaparece al borrar. La tabla actual expresa cómputo incluido en dinero, no
  debe copiarse sin verificar una antigua cifra fija de minutos de Free.
- [Runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners):
  Linux estándar público, 4 CPU, 16 GB RAM y 14 GB SSD; el espacio libre real se
  comprueba porque imagen y dependencias ya ocupan disco.
- [Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases):
  límites propios, separados de Pages/Actions. La implementación no crea un archivo
  en Releases ni presupone que exista; los assets desconocidos quedan protegidos.

## Flujo y orden de presión

1. Deduplicar contenido (huella), admitir sólo v2 migrable/v3 y excluir bajas.
   Un nuevo `run_id` no cuenta como otra revisión. Se prefiere la copia publicada
   del mismo contenido. Baseline, esquema y observación deciden antes del run.
2. Leer índices pequeños `sentinel-index-RUN-ATTEMPT`, ligados a una ejecución
   confiable y verificados por digest. Los artefactos anteriores sin índice sólo
   se admiten por el inventario histórico de hashes revisado; otros quedan en
   cuarentena sin descargar. La paginación incompleta falla, no parece vacía.
3. Elegir antes de GET de paquetes. 8→6→4 según sitio, transferencia, trabajo y
   espacio restante de Actions para el próximo sitio. Comprobar disco antes del
   GET, expansión, caché, construcción y tar de upload. Si el mínimo no cabe,
   parar y conservar el despliegue. Una estimación insuficiente también falla
   al medir el sitio real; no se reconstruye repetidamente en el mismo job.
4. Bajo presión, revisar primero el plan de copias redundantes/temporales/cachés.
   Esas bajas necesitan ejecución explícita; no se presupone espacio liberado
   mientras sólo exista un plan. Reducir fechas no libera Actions por sí solo.
5. Mantener selección, DN/metadatos, productos visibles y temporales separados.
   El cálculo y migración son secuenciales; hasta N−1 parejas adyacentes, incluso
   con productos fijados. La interfaz no precisa una matriz N². Los temporales
   locales propios se retiran sólo después de validar las referencias del sitio.
6. Mantener una generación de paquetes anterior, adicional a los seleccionados,
   si cabe en sitio y transferencia; el solapamiento no se duplica. No se arrastra
   indefinidamente `previous`. Estos paquetes no vuelven al catálogo por sí solos.
7. Validar rejillas, hashes, catálogo, índices, parcelas, agua y comparaciones;
   subir una única generación atómica. Un fallo de red, hash, cálculo, presupuesto,
   validación o deployment no adelanta el recibo ni habilita bajas para la nueva
   generación. El borrado remoto exige el catálogo realmente publicado.

Se preservan los umbrales científicos, float32 y resoluciones. El AOI contiene
aproximadamente 955.000 celdas a 10 m; el procesamiento usa vecindades y estadísticas
globales. Con las medidas actuales no se justifica reescribirlo por bloques: podría
alterar bordes sin un beneficio demostrado. GDAL limita su caché a 128 MB y sus
reintentos a dos (5 s, timeout 60 s). El supervisor registra tiempos y picos
**muestreados**, que son cotas inferiores del pico real, no métricas de facturación.

## Supervisar y cambiar la política (sin ejecutar limpieza)

1. La política ya está desplegada por #15. Este cierre documental no necesita
   otra publicación. Se deja su PR abierta, con `[skip ci]` en el commit y título;
   una eventual fusión documental sin despliegue debe conservar ese marcador
   en el mensaje final. Un push ordinario a main activaría Pages. Véase la
   [documentación oficial de omisión de workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs):
   se omiten `push`/`pull_request`, no los eventos programados o manuales independientes;
   los checks pueden quedar pendientes, lo que no significa CI ejecutada.
2. Mantener **`version: 2`, `max_acquisitions: 4` y `pinned_products: []`**.
   Para ampliar a 6 u 8, usar una PR de configuración separada, sus pruebas y
   autorización de publicación; no restaurar la configuración v1 documentada
   en el antecedente #14. El objetivo al 80% puede
   reducir ese máximo automáticamente. `pinned_products` admite hasta cuatro IDs
   exactos, de días distintos; se completan los huecos con los más recientes. Un
   ID ausente/retirado falla explícitamente. El catálogo registra selección
   experimental y última observación disponible; el visor rotula «Experimento» y
   conserva fecha/antigüedad, nunca llama actual a una selección histórica.
3. La limpieza sigue pendiente y no se ejecuta con este cierre. Si se solicita
   otra simulación, lanzar manualmente **Sentinel explicit resource
   cleanup**, `mode=plan`, sobre main. Descargar `sentinel-cleanup-plan.json`;
   revisar todos los objetos, motivos, bytes y SHA256. Regenerar si cambió el sitio.
4. Sólo con autorización concreta: ejecutar el mismo workflow con `mode=execute`,
   `plan_run` y `plan_sha256`. El código debe coincidir con el del plan. No hay
   disparador programado de bajas. El ejecutor vuelve a inventariar, restaura y
   valida los DN retenidos, compara generación publicada y revisiones del estado.
5. La ejecución de limpieza crearía o actualizaría la rama Git `sentinel-state`, archivo `sentinel-state.json`,
   como registro ligero con actualización CAS; no es servicio ni base de datos.
   Conserva producto/fecha/huella, motivo, baja pendiente y momento confirmado.
   Una interrupción después del DELETE se reanuda con el mismo plan: 404 confirma
   ausencia y no provoca una baja adicional. No se pierde la baja pendiente.
6. Procesamiento, deploy y limpieza comparten `sentinel-resources`. El calendario
   vacío no ocupa ese grupo. Sólo el job manual de ejecución tiene `actions:write`
   y `contents:write`; nunca tiene permisos de Pages. Nunca borra una Release
   completa, ni assets sin contrato de propiedad, ni cartografía/código/WordPress.
7. Revisar `sentinel-metrics.jsonl` (artefacto de siete días), resumen de admisión,
   inventario y tamaño real. Bajas de artefactos/cachés no reducen transferencia
   consumida, minutos anteriores ni el coste ya acumulado. Si falla una consulta,
   corregir acceso/servicio; no tratarla como cero. El plan offline adjunto es una
   **simulación**, no autorización utilizable como plan de un run de producción.

Reproducción local de la simulación, sin red ni DELETE:

```sh
python3 scripts/sentinel_cleanup.py --inventory docs/sentinel-evidence/resource-inventory-20261117.json --plan /tmp/sentinel-plan.json
```

## Recuperación y límites

Mientras la adquisición esté seleccionada, su paquete Pages conserva seis DN,
calibración y metadatos necesarios para recalcular; Actions ofrece un respaldo
adicional mientras no caduque. No conserva el SAFE completo: faltan otras bandas,
teselas, footprint completo y XML auxiliares. Fuente SAFE/S3 no equivale a posesión
de todos esos bytes. Los scripts y versiones están en Git; el manifiesto registra
procedencia de cálculo cuando existía, sin inventarla para versiones históricas.

Para recuperar: verificar hashes de `recovery.json`/catálogo/recibo; usar
`sentinel_recovery.restore`, después `upgrade_sentinel_products.py` si es v2;
reconstruir y validar antes de autorizar Pages. `previous` permite rescatar la
generación inmediata si seguía dentro del presupuesto, pero no se incorpora
automáticamente a la selección. Si no queda copia, consultar CDSE por el ID y
fecha exactos, comprobar disponibilidad/licencia/acceso, descargar los recortes
con credenciales y recalcular. La disponibilidad futura del proveedor no está
garantizada; un reprocesamiento puede ser otra revisión, no recuperación binaria.

Revertir código **no restaura imágenes eliminadas**. No revertir a código anterior
que ignore `sentinel-state`: podría reintroducir un producto aún presente en una
caché antigua. Restaurar un producto dado de baja exige revisión explícita de la
entrada del registro y de una nueva copia íntegra, además de una selección fijada
si procede. No borrar la rama de estado para «arreglar» un error. El registro se
limita a 900 KB y exige revisión de compactación si crece; no elimina tombstones
silenciosamente ni obliga a conservar grandes imágenes históricas.

## Validación de #15 y alcance del cierre documental

136 pruebas Python con GDAL local, nueve suites Node, gate WebGIS, comprobación
de política espacial y actionlint. Incluyen orden por observación, 4/menos/más,
duplicados/versiones, 8→6→4, fijación histórica, disco antes de GET/publicación,
fallos de hash/red/cálculo/deploy, referencias/parejas, conservación de la versión
anterior, generación previa opcional, bajas interrumpidas/reintento, protección de
seleccionados y contenidos ajenos, y exclusión por tombstone. Todos los DELETE de
prueba usan transporte falso. El despliegue y la recuperación reales autorizados
se verificaron después, como consta en el cierre. La ejecución destructiva real
continúa pendiente y no está autorizada por esta documentación.

Este cambio documental valida JSON, hashes, fechas, conteos, enlaces locales y
ausencia de modificaciones en código/configuración/workflows. El gate local
offline `python3 scripts/check_webgis.py` también pasa; no sustituye una nueva
prueba visual o remota. Incorpora los
resultados anteriores, sin repetir los tests científicos ni la recuperación de
paquetes. La evidencia de #14 se conserva exactamente como fue revisada; las
instrucciones de operar en 8 se reemplazan por esta guía de retención activa en 4.
