# Revisión de Sentinel → GitHub Pages · 16/11/2026

Preparado sobre `b9c4d176fe1303377b4708e24a5da66b17b6c383`, en la rama local
`codex/pages-sentinel-update-gate`. No se ha modificado `main`, enviado la rama,
iniciado Actions ni desplegado. La integración y el despliegue requieren la
aprobación expresa solicitada por el usuario.

## Evidencia contrastada

| Caso | Sentinel | Pages | Resultado observado |
| --- | --- | --- | --- |
| 15/11 | [43716160874](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/43716160874) | [43716464181](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/43716464181) | Procesamiento correcto, caché ausente, artefacto `14161964706` de 18.002.158 bytes; producto observado el 06/11. Pages publicó cuatro observaciones y tres comparaciones. |
| 16/11 | [43880178969](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/43880178969) | [43880230274](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/43880230274) | `2026-11-16: run=false`; `sentinel` omitido; cero artefactos. Pages volvió a ejecutar geoespacial, gate, WordPress y despliegue; paquete de 69.342.532 bytes. |

Ambos Pages usaron el mismo SHA indicado arriba. Los logs del 15 identifican
`S2B_MSIL2A_20261106T111149_N0513_R137_T30TUK_20261106T132030` y muestran que
se conservaron también 16/08/2023, 14/10/2026 y 31/10/2026.
El paquete Pages del 15, ya ausente en la lista de artefactos, consta en su log:
`14162139462`, 69.342.528 bytes. No se afirma igualdad binaria de ambos ZIP.

Los metadatos reducidos de la API están en
`scripts/fixtures/sentinel-publication-runs.json`. Las pruebas de decisiones
usan esos IDs, estados y nombres reales, con bytes de producto sintéticos:
no se ha descargado ni vuelto a procesar el ZIP real del 15. Otra prueba separada
ejecuta el pipeline GDAL, migración y construcción con rásteres de prueba.

## Dependencias y criterio

Antes: `Sentinel terminado → geospatial + gate + wordpress → deploy`.
Sólo `gate` exigía éxito de Sentinel; ninguno exigía un producto nuevo.
`success` puede incluir un trabajo `sentinel` omitido. Es la semántica de
[workflow_run](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run).

Ahora: `publication → geospatial + gate + wordpress → deploy → recheck → construcción/publicación`.

`publication` produce `proceed` y una razón verificable en outputs y resumen:

1. `push`, `pull_request` y Pages manual: continuar. Se conserva el filtro que
   sólo publica desde `main`, nunca desde una PR.
2. `workflow_run`: exigir éxito, rama `main`, repositorio de origen correcto,
   ruta `.github/workflows/sentinel.yml` y evento Sentinel programado/manual.
3. Consultar los trabajos del **intento exacto**. Sin `sentinel=success`, omitir
   todos los trabajos posteriores. El caso del 16 sólo consulta estos metadatos;
   no descarga ZIP, no consulta el sitio ni Copernicus.
4. Exigir el artefacto no caducado `sentinel-<run_id>` de esa ejecución. Verificar
   SHA-256 del ZIP, archivos permitidos y sus hashes, calidad y versión compatible
   o migrable. No se ejecuta ni extrae código del artefacto.
5. Comparar `{id, datetime, fingerprint}` con `sentinel/publication.json` del sitio
   publicado. La huella incluye rásteres y metadatos de procesamiento; excluye
   consulta, auditoría de ejecución, formato JSON y empaquetado ZIP.
   Coincidencia exacta: `product-already-published`; ausencia o cambio:
   `new-or-changed-product`.

El registro se genera **después** de construir el catálogo y a partir de los
productos originales que ese catálogo incluye. Así reconoce un v2 ya publicado
tras migrarlo a v3. Sólo contiene identificador, instante y huella; no publica
el manifiesto del proveedor, credenciales ni auditoría. Viaja dentro del mismo
paquete Pages: una construcción/publicación fallida no actualiza el registro
del sitio. No hay caché usada como evidencia de publicación ni servicio nuevo.

La lectura pública usa HTTPS, sin token, con consulta única y `no-cache`.
404 permite inicializar el registro o recuperar el sitio, siempre que exista
un producto válido. Otros errores HTTP/red, JSON inválido o integridad incorrecta
detienen el flujo automático; no se interpretan como ausencia de cambios.
Pages manual permite recuperar el servicio sin depender de esa lectura.
El token sólo lee Actions y contenidos; los permisos de publicación siguen
limitados al trabajo `deploy`.

La concurrencia `pages-production` se aplica a `deploy`. Una ejecución vacía
no entra en esa cola ni sustituye un despliegue pendiente. Se repite la decisión
después de esperar: si otro despliegue ya incluyó el producto, se omiten
construcción, paquete y publicación. GitHub explica la sustitución de pendientes
en su [documentación de concurrencia](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

## Compatibilidad y límites

- Cron intacto: `30 5 * * *`; calendario de 15/3 días intacto.
- Sentinel manual conserva `date` e `item_id`, y puede recuperar productos de
  cualquier fecha. No se compara con la fecha más reciente ni con el SHA de código.
- Un histórico recuperado de caché se publica si falta en el sitio; una
  adquisición nueva se publica aunque el commit sea el mismo. Un producto con
  el mismo identificador pero contenido cambiado también continúa.
- La colección conserva la selección por fecha y la migración v2→v3. Se añade
  paginación para que cien comprobaciones de calendario no oculten históricos
  todavía retenidos. La caducidad de los artefactos sigue siendo de 90 días;
  los caducados deben recuperarse mediante Sentinel manual, como antes.
- Los fallos se guardan como `sentinel-diagnostics-<run_id>` durante 14 días;
  sólo un producto verificado usa el nombre consumido por Pages.
- Sigue apareciendo una ejecución corta de Pages al terminar Sentinel: GitHub
  no permite filtrar `workflow_run` por archivos de artefactos. Lo que se evita
  es ejecutar controles costosos, reconstruir y publicar sin novedades.
- Los controles de calidad no se suprimen cuando procede publicar. Dos eventos
  simultáneos con novedades pueden ejecutar controles en paralelo; el despliegue
  se serializa y vuelve a comprobar el registro antes de construir.
- La URL del registro corresponde al Pages actual del repositorio; debe
  actualizarse si se cambia su ubicación pública.

## Pruebas locales

Resultado: **96 pruebas Python aprobadas, cero omitidas**, con Python 3.12/GDAL
de QGIS 3.40.4; incluyen **23 pruebas nuevas** de publicación. La prueba de
integración genera rásteres, procesa v2, migra a v3, construye el catálogo y
verifica que el registro reconoce el producto original.

También aprobados: nueve suites Node de interfaz, gate WebGIS, sincronización
de política de ubicación y `actionlint 1.7.12` sobre ambos YAML. Actionlint se
ejecutó sin sus analizadores opcionales ShellCheck/Pyflakes.

Comandos equivalentes en el entorno Linux del workflow:

```sh
/usr/bin/python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/check_webgis.py
python3 scripts/build-location-policy.py --check
node scripts/test-sentinel-ui.cjs
node scripts/test-parcels.cjs
node scripts/test-parcel-ndvi.cjs
node scripts/test-water.cjs
node scripts/test-comparison.cjs
node scripts/test-location.cjs
node scripts/test-incidents-form.cjs
node scripts/test-incidents.cjs
node scripts/test-incidents-map.cjs
actionlint -shellcheck= -pyflakes= .github/workflows/pages.yml .github/workflows/sentinel.yml
git diff --check
```

| Regresión | Decisión esperada y comprobada |
| --- | --- |
| Calendario del 16/11, sin artefactos | Omitir los cuatro trabajos posteriores |
| Producto del 15/11 aún no publicado | Continuar |
| Mismo producto desde caché/reintento/otro ZIP | Omitir |
| Histórico de 2023 ausente, incluido v2 | Continuar |
| Mismo producto reprocesado con cambios | Continuar |
| Publicación fallida y reintento | Continuar hasta que aparezca en el registro publicado |
| Artefacto ausente/caducado/diagnóstico | Omitir |
| Origen, rama, workflow o conclusión no válidos | Omitir sin descargar |
| ZIP/raster corrupto, registro inválido o error de red | Fallar sin desplegar |
| Registro todavía inexistente | Inicializar con producto válido |
| Push a main, PR, Pages manual | Conservar controles; PR no publica |
| Histórico detrás de cien ejecuciones | Seguir paginando |
| Ejecución vacía y cola de despliegue | No entrar en la cola; volver a comprobar antes de construir |

No se ha vuelto a ejecutar la integración completa PHP/WordPress, que no cambia;
su trabajo sigue siendo dependencia obligatoria de despliegue. Tampoco se ha
ejecutado el YAML en GitHub ni publicado el sitio. La aceptación en Actions y
la inspección del registro público quedan para después de la aprobación.

## Aplicación y reversión

Tras aprobación: integrar como **un solo commit**, pasar los controles de la PR
y permitir el despliegue por `push` a `main`. Ese primer despliegue inicializa
`sentinel/publication.json` con todas las adquisiciones realmente incluidas.
Comprobar el JSON público y un posterior calendario `run=false`: sólo debe
ejecutarse `publication`, con los demás trabajos omitidos.

Antes de integrar, descartar esta rama/cambio local revierte toda la propuesta;
no hay estado remoto que limpiar.

Después de integrar, preparar una PR que revierta el único commit del arreglo:

```sh
git revert <sha-del-commit-del-arreglo>
```

Revisar y aprobar esa PR antes de incorporarla a `main`. Su `push` ejecutará
los controles y el despliegue anteriores. El registro nuevo dejará de consultarse
y el siguiente paquete anterior ya no lo incluirá. No borrar productos,
cachés ni históricos. Si sólo se necesita publicar urgentemente conservando
el arreglo, ejecutar Pages manual desde `main`: evita la deduplicación y
mantiene todos los controles de calidad.

La reversión restaura también el comportamiento redundante original; por eso
Pages manual es la primera opción de recuperación operativa.
