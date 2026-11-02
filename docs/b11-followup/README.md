# Continuación acotada: producto publicado, calidad, firmas y detector

Actualización posterior: la integración autorizada para orientar visitas de campo se documenta en [guía operativa](../water-field-guide.md). Los resultados y las conclusiones siguientes conservan el alcance del estudio original.

02/11/2026 · rama `codex/estudio-b11-ciclos-0-3` · PR #7 en borrador.
Base revisada: `48a78e88c956727853b87bf51261ba104a2804f8`; al empezar no había
cambios posteriores en la rama remota. No se modifica el método operativo, el
visor, los workflows ni la publicación. No se añade SAR ni otro reconstruidor.

**Resultado:** el caso de inválidos se reproduce sobre el SAFE exacto publicado.
La política estricta de hijos cambia cobertura y ajuste, sin mejorar necesariamente
el RMSE. Con D/E congeladas, dos hipótesis del detector recuperan candidatos en
00001 y 00059; 00700014 requiere investigar una firma de mayor NIR. Estas ganancias
son descriptivas, sin etiquetas espaciales independientes suficientes para exactitud.

## Corrección del alcance, sin reescribir resultados

Las reconstrucciones **D/E completas 20→10** ajustan `guided_b11` globalmente por
adquisición. No usan etiquetas, pero no excluyen las zonas examinadas. Eso no es,
por sí solo, fuga de etiquetas; tampoco es validación espacial fuera del ajuste.
La reserva de zonas completas más **80 m sólo corresponde al ensayo reducido
40→20**. Mejorar su RMSE frente a B11 observada de 20 m es distinto de recuperar
candidatos MNDWI a 10 m.

Se corrigen el README anterior, `inventory.json`, `frozen.json` y el generador de
metadatos. `experiment_roles` distingue ajuste global, reserva reducida y desarrollo
del detector. `previous-inventory.json` y `previous-frozen.json` conservan las versiones
originales. Los 58 restantes archivos de resultados anteriores se compararon con
el commit revisado y se preservan: [preserved-results.json](preserved-results.json).
Sus hashes textuales se normalizan a LF; las figuras conservan bytes exactos.
Los hashes históricos de `../b11-cycles/validation.json` siguen siendo históricos.

Todos los casos previamente inspeccionados son ahora **desarrollo**. No se han
rebautizado como reserva independiente. La evaluación etiquetada independiente
queda pendiente; no se optimizan umbrales para una supuesta exactitud en esos casos.

## SAFE publicado N0510 frente al histórico N0509

Se conservan por separado:

* Histórico: `S2A_MSIL2A_20230816T105631_N0509_R094_T30TUK_20230816T171602`.
* Publicado: `S2A_MSIL2A_20230816T105631_N0510_R094_T30TUK_20241021T044404`.

Se recuperó el artefacto `13091783958` del [run 41327640780](https://github.com/julianladera-droid/castrejon-webgis/actions/runs/41327640780).
Su SHA-256 es `846c1dc70834cfc18a1c8e1266703aca89c9b89ce2513ba3d8b1d15b2a244055`.
NDWI y MNDWI coinciden por hash con el catálogo del visor consultado el 02/11.
[provenance.json](provenance.json), [published-catalog.json](published-catalog.json)
y [frozen.json](frozen.json) registran identidades, procedencia, bandas, escalas,
offsets, hashes, rejillas y ajustes. Ambos AOI tienen la misma rejilla 10 m,
1488×642, EPSG:25830; sus bandas de 20 m están exactamente anidadas.

Se recalculan NDWI, NDVI, MNDWI y el detector B a partir de sus propias bandas.
Se exige igualdad numérica con los rásteres conservados y con `WATER.tif`.
El código y los parámetros se mantienen iguales entre baselines: las diferencias
de esta comparación pertenecen a los productos de entrada, no a un cambio de
nuestro método. No se atribuye cada cambio a un mecanismo específico del procesador
atmosférico sin documentación adicional.

**45137A00900059, 16/08/2023 — m² por motivo (solapables, no sumar):**

| Motivo | N0509 | N0510 publicado |
|---|---:|---:|
| Verde/NIR ausente | 33,159 | 0 |
| Verde o NIR negativo | 2.555,729 | 3.388,888 |
| Suma verde+NIR ≤0,01 | 4.655,729 | 4.888,888 |
| SCL fuera de 4/5/6 | 5.329,571 | 4.529,571 |
| NDWI excluido, unión de motivos | 8.792,018 | 8.292,018 |
| MNDWI excluido | 5.329,571 | 4.529,571 |

N0510 gana 1.200 m² válidos de NDWI y pierde 700 m² en otros lugares: saldo
+500 m². La SCL cambia en 2.400 m². MNDWI gana 1.600 m² y pierde 800 m².
El cambio de NIR tiene RMSE 0,007532 y sesgo N0510−N0509 de +0,002281 sobre
421 centros finitos de 10 m de la parcela; no son métricas de exactitud del agua.

Una máscara exploratoria fija N0509 (`NIR<0,06`, `B11<0,08`, valores finitos)
interseca 7.917,958 m² de la parcela. De ella, NDWI excluye 6.717,958 m² en N0509
y 6.617,958 m² en N0510. Es una **coincidencia con una propuesta oscura**, no un
contorno independiente de agua ni superficie inundada validada. La confirmación
parcelaria del usuario y la imagen orientan la revisión, pero no etiquetan todos
los excluidos.

[baseline-quality.csv](baseline-quality.csv) detalla 17 zonas por baseline y clase
SCL; [baseline-deltas.csv](baseline-deltas.csv) aporta cambios de reflectancia y
validez. Hay mapas de motivos para 00059 y otras cuatro parcelas descritas como
lagunas, sin atribuirles automáticamente el testimonio de agua inválida:
[00059](45137A00900059-baseline-exclusions.jpg),
[00001](45137A00900001-baseline-exclusions.jpg),
[00900013](45137A00900013-baseline-exclusions.jpg),
[01000045](45137A01000045-baseline-exclusions.jpg),
[00800001](45137A00800001-baseline-exclusions.jpg).
Faltan coordenadas de las otras zonas de río/laguna señaladas. No se asignan a
153, 155 o 074.

## Experimento separado de agregación y calidad

Se conserva el ensayo anterior y se ejecutan, en cada uno de los cuatro SAFE,
dos políticas con suelos 0 / 0,005 / 0,01 / 0,02:

* `aggregate`: la validez depende de las reflectancias agregadas y su suma.
* `all_children`: además exige que todos los hijos de 10 m de la pareja de bandas
  sean finitos, no negativos y superen el suelo antes de contribuir.

Ambas calculan el índice **después de agregar reflectancias**. Una observación
negativa puede contribuir a una media positiva: es una diferencia explícita de
política, no un error declarado automáticamente. Nodata propaga ausencia en ambas;
no se utiliza `nanmean`, recorte a cero ni a −1.

En 00059 de agosto, de 109 centros de celda de 20 m:

| SAFE / guía | Válidos agregada | Válidos todos los hijos | Bloques con hijo negativo y agregado válido |
|---|---:|---:|---:|
| N0509 NDWI | 87 | 83 | 2 |
| N0509 NDVI | 83 | 82 | 1 |
| N0510 NDWI | 88 | 85 | 1 |
| N0510 NDVI | 84 | 82 | 2 |

Las pérdidas adicionales pueden proceder del suelo de señal, no sólo de negativos.
N0509 tiene un bloque con ausencia para ambas parejas; N0510 ninguno para NDWI
y uno para NDVI. Las guías coinciden numéricamente en su intersección válida:
lo que cambia primero es la elegibilidad y después la población del ajuste.

Se separan dos modos en [quality-metrics.csv](quality-metrics.csv):
`eligibility_only_fixed` aplica la nueva elegibilidad a la reconstrucción reducida
base congelada; `recomputed` vuelve a calcular guías, coeficientes y reconstrucción.
La comparación `n/bias/mae/rmse` usa exactamente su soporte compartido; `own_n` y
`own_rmse` documentan la cobertura propia. No se confunde mejor resultado por
selección de cobertura con mejor reconstrucción.

| E, 00059, suelo 0,01, política todos los hijos | n común | RMSE congelada | RMSE recalculada |
|---|---:|---:|---:|
| N0509 | 69 | 0,023132 | 0,023958 |
| N0510 | 71 | 0,024099 | 0,025189 |

La política estricta no mejora estos casos. N0509 E pasa de 73 muestras propias
con política agregada a 69 con hijos estrictos. Con política agregada, su RMSE
varía de 0,022684 (suelo 0) a 0,023302 (0,02), con 73 muestras en este caso.
No es una selección del suelo óptimo: el conjunto ya está inspeccionado.
[quality-blocks.csv](quality-blocks.csv) cuantifica cambios de guía y bloques;
[quality-fits.json](quality-fits.json) registra cada ajuste. Se verificó igualdad
exacta de los coeficientes del caso base con los tres ensayos anteriores.
Este experimento **no alimenta** el ensayo de detectores.

## Zonas propuestas y firmas

Se buscaron geometrías en el inventario, maestro parcelario, controles y archivos
geoespaciales disponibles del repositorio. No había huellas vectoriales independientes
de edificios, paneles o agua. El WMS catastral del visor es una imagen, no esas huellas.
Se generan **72 propuestas** para las nueve parcelas prioritarias en cuatro SAFE:
contexto oscuro, brillante, vegetación y candidatos recuperados por D/E. Cada una
se deriva de la propia adquisición, se recorta a la parcela y declara fuente,
fecha, precisión de rejilla, incertidumbre, vigencia y función de desarrollo.

[proposed-zones.geojson](proposed-zones.geojson) es cartografía métrica EPSG:25830;
[proposed-zones.json](proposed-zones.json) incluye los datos pendientes.
El maestro parcelario no declara fecha de vigencia geométrica: su correspondencia
histórica necesita revisión. No son huellas verdaderas de edificios/paneles ni contornos de agua; tampoco se
excluyen parcelas mixtas completas. Los contextos seleccionados por índice o
reflectancia no sirven como validación independiente de sus propios selectores.
La selección de centros y posterior recorte tampoco pretende precisión subpíxel.

[signatures.csv](signatures.csv) y las figuras `*-spectra.jpg` contienen:

* Reflectancias observadas a 20 m: B02/B03/B04/B08 agregadas, B8A/B11 nativas.
* Rejilla 10 m: visibles/NIR nativos; B8A repetida del padre; B11 B repetida y
  B11 D/E reconstruidas, etiquetadas como tales.
* Mediana, p10/p25/p75/p90, número de muestras propias/comunes, cobertura común,
  negativos y muestras con SCL admisible. Curvas de mediana y banda intercuartílica.

Las firmas diagnósticas conservan reflectancias originales **con signo** sobre
soporte común finito, sin ocultar negativos por la máscara del detector. Su
cobertura no equivale a cobertura interpretable para cocientes. No proceden de
colores JPEG. Se usa forma e intensidad, no un ángulo espectral aislado.

B02 se verifica por SAFE, hash y rejilla en los tres productos históricos.
El artefacto publicado N0510 no incluye B02 y no hay credenciales CDSE disponibles:
se analiza con cinco bandas y su panel contextual se etiqueta **falso color
NIR/rojo/verde**. No se usa B02 de N0509 ni se inventa una curva azul de N0510.

El 31/10, la propuesta recuperada de 00001 tiene medianas observadas a 20 m
NIR=0,03775 y B11=0,05960 (`n=3`); la de 00700014 NIR=0,20350 y B11=0,11795
(`n=4`). El contraste de intensidad y la elevación del NIR son distintos,
aunque ambos tengan candidatos MNDWI reconstruidos. Son muestras pequeñas y
seleccionadas, sin exactitud por clase. El contexto oscuro de 00059 en N0509
presenta rojo mediano −0,002513 y NIR 0,010363 (`n=22`), mostrando por qué los
valores originales y la elegibilidad radiométrica deben examinarse por separado.

En el contexto oscuro de 00059 de agosto, el soporte común de B/D/E a 10 m
queda vacío: las figuras indican n=0, sin confundirlo con ausencia de agua.

No se entrenó un clasificador supervisado. Suelo húmedo sin lámina, sombra y
materiales de edificios/paneles siguen sin etiquetas locales suficientes: los
contextos oscuros/brillantes ayudan a revisarlos, pero no los identifican por sí
solos. En 153/155 se describen firmas vegetadas; una anomalía de cultivo no
demuestra agua subyacente ni su causa. La separación de esas clases permanece
no concluyente.

## Detector con reconstrucciones congeladas

Cada SAFE tiene B (MNDWI original 20 m), D y E identificados por hashes de arrays,
guardados fuera de Git en `artifacts/b11-followup/frozen/`. Se comprueba que los
detectores no los mutan; D/E también reproducen los metadatos de ajuste global
anteriores. Las reconstrucciones del experimento de calidad no se sustituyen aquí.

Se fijaron dos hipótesis antes de ejecutar la primera comparación, usando límites
conservadores relacionados con las reglas radiométricas existentes. No se ajustan
a posteriori para forzar 00700014:

* **Actual:** calidad y NIR≤0,15; `SCL=6 OR (NDWI>0 AND MNDWI>0)`.
* **H1 residual:** conserva el actual y añade **otra clase**, mezcla/agua residual
  candidata, para píxeles válidos con NDWI≤0, MNDWI>0, B11 entre 0 y 0,08,
  NIR≤0,15 y B8A entre 0 y 0,15.
* **H2 estricta:** parte de H1 y promueve a agua superficial estimada sólo los
  nuevos candidatos con NIR≤0,06, B11≤0,05 y B8A≤0,08.

No es sustituir AND por OR globalmente. Nodata, negativos y baja señal mantienen
su exclusión; las nuevas reglas no convierten los inválidos de agosto en agua.
Ambigüedad se mantiene aparte. No se genera una clase de anomalía de cultivo
sin una referencia temporal que la sustente.

**31/10/2026, soporte común B/D/E, m²:**

| Zona / reconstrucción | Actual: agua | H1: agua / residual | H2: agua / residual |
|---|---:|---:|---:|
| 00001 B | 0 | 0 / 0 | 0 / 0 |
| 00001 D | 0 | 0 / 100 | 0 / 100 |
| 00001 E | 0 | 0 / 700 | 400 / 300 |
| 00059 E | 1.000 | 1.000 / 1.066,318 | 1.966,318 / 100 |
| 00700014 B/D/E | 0 | 0 / 0 | 0 / 0 |

En 00700014 los 800/600/1.900 m² de candidatos MNDWI B/D/E tienen NIR>0,15 y
B8A>0,15. Además, 800/400/1.200 m² superan B11=0,08. Retirar únicamente la
condición NDWI positiva **no basta**. La firma observada es compatible con mezcla
o cobertura vegetal, pero no permite confirmar agua ni justificar relajar todos
los límites a partir de esta parcela.

En las cuatro parcelas construidas señaladas, H1/H2 no añaden candidatos en el
soporte común del 31/10. **No eliminan la ambigüedad previa** de edificios/paneles,
ni esto demuestra ausencia general de falsos positivos: faltan huellas y reserva
independiente. Los estados actuales de agua se conservan por construcción de las
hipótesis; las pérdidas son cero, no una evidencia empírica de sensibilidad perfecta.

[detectors.csv](detectors.csv) contiene agua, residual, ambigüedad, ganancias,
pérdidas, cobertura propia/común y descarte, por SAFE/zona/reconstrucción/regla.
El soporte propio exige NDWI y MNDWI interpretables y B11 disponible; el común
es su intersección B/D/E. `native_not_evaluable_m2` conserva la no evaluabilidad
del detector original, que puede diferir de esa máscara de comparación.
Las filas `gate_diagnostic` detallan las barreras de 00001/00700014.

Los mapas `*-detectors.jpg` comparan las tres reglas y tres reconstrucciones
sobre el mismo soporte. `*-map.jpg` muestra contexto, exclusiones, SCL y H1;
`*-zones.jpg`, las propuestas. Se declara SAFE/baseline, fecha, método, soporte
y EPSG:25830. Blanco=sin detección; azul=agua estimada; naranja=ambigüedad;
gris=exclusión; morado=residual candidato. Ningún color es una etiqueta validada.

## Reproducción y verificación

Reutilizar las entradas de la entrega anterior (`artifacts/water-review/products`
y `rgb`). Para recuperar el producto publicado con GitHub CLI autenticado:

```sh
gh run download 41327640780 --repo julianladera-droid/castrejon-webgis --name sentinel-41327640780 --dir artifacts/b11-followup/n0510
```

Esta ejecución utilizó el conector GitHub para descargar el mismo artefacto.
Se verifican los hashes de las bandas en su manifiesto. El catálogo consultado
se conserva versionado; copiarlo a `artifacts/b11-followup/published-catalog.json`
si se reproduce desde una nueva copia. No sustituirlo silenciosamente por una
publicación posterior. Los TIFF y NPZ pesados no entran en Git.

```sh
python scripts/b11_followup.py docs/b11-followup
python scripts/b11_followup.py artifacts/b11-followup/repeat
python -m unittest discover -s scripts -p 'test_*.py'
python -X utf8 scripts/check_webgis.py
python -X utf8 scripts/build-location-policy.py --check
```

Python 3.12.9, GDAL 3.10.2, NumPy 1.26.4 y matplotlib del entorno QGIS 3.40.4;
Windows ejecutado con `C:\Program Files\QGIS 3.40.4\bin\python-qgis-ltr.bat`.
Se ejecutaron 67 pruebas Python, incluyendo ocho nuevas sobre negativos/nodata,
suelo de señal, máscaras, inmutabilidad, reserva, identidad/soportes y preservación.
Los resultados de gates, reproducción y hashes se registran en
[validation.json](validation.json). Se inspeccionaron figuras de firmas, exclusión
y propuestas; no hay cambio de interfaz que requiera desplegar o modificar el visor.

## Cierre por objetivo

| Objetivo / superficie | Decisión | Alcance |
|---|---|---|
| Precisión documental y preservación | **Avanza** | Reserva reducida y ajuste global diferenciados; resultados anteriores conservados |
| Agua inválida en 00059, agosto | **Avanza** en diagnóstico | SAFE publicado confirmado, motivos y reprocesamiento cuantificados; superficie de agua excluida aún sin verdad espacial |
| Validez de todos los hijos | **Revisa** | Cambia cobertura y coeficientes; no mejora automáticamente RMSE |
| Recuperación en 00001/00059 con D/E fijas | **Revisa** | H1/H2 añaden candidatos, no aciertos espaciales demostrados |
| 00700014 | **Revisa** | También bloquean límites NIR/B8A/B11; firma distinta de agua oscura |
| Construcciones y paneles | **Revisa** | Sin nuevos candidatos en estos controles/fecha, pero persiste ambigüedad y faltan huellas |
| Agua bajo vegetación, suelo húmedo y sombra | **No concluyente** | Firmas de contexto, sin etiquetas locales que separen esas causas |
| Exactitud espacial e integración operativa | **No concluyente** | Sin reserva independiente etiquetada; no F1/IoU, contorno verdadero ni superficie validada |

Faltan: huellas y fechas de agua/edificios/paneles, controles negativos localizados,
B02 del SAFE N0510 si se quiere completar esa firma, otras zonas de río/laguna
inválidas y éxitos adicionales de reescalado. El estado de la adquisición conserva
lagunas preexistentes: no se confunde con cambio temporal. El descenso comunicado
10–31/10 no impone monotonía; once imágenes útiles de agosto y el riego iniciado
el 30/07 no prueban agua en cada pasada. No se estima profundidad ni volumen.
Se entrega para revisión antes de cualquier integración operativa.
