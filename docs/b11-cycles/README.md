# B11 guiada, ciclos 0–3 — entrega para revisión

Estudio del 02/11/2026 sobre `bb863cc82990de6d85a07994609de16b2ef10ec5`, en
`codex/estudio-b11-ciclos-0-3`. Se comprobó `origin/main`: no había cambios
posteriores al iniciar el bloque. No modifica el detector operativo, el visor,
los workflows ni los productos publicados. No incluye fusión ni despliegue.

**Resultado:** el reescalado conserva ámbitos de utilidad. Recupera candidatos
ausentes en el MNDWI original y mejora la reconstrucción reducida en numerosas
zonas. La ganancia depende de la guía, fecha y superficie; también produce
señales sobre construcciones. No se justifica sustituir el método operativo.

## Referencias y alcance

[references.json](references.json) conserva los testimonios y sus límites;
[inventory.json](inventory.json) contiene **51 unidades zona × adquisición**:
13 parcelas maestras y cuatro contextos RGB, en tres fechas. Cada unidad incluye
geometría EPSG:25830, SAFE, fuente, clase, precisión, incertidumbre y función.
Las geometrías y su hash proceden del maestro, sin dibujar contornos de agua.

Las cuatro parcelas iniciales ya se habían explorado: se consideran selección,
no validación independiente. Las nueve referencias nuevas se incorporaron tras
fijar los parámetros; no se reajustaron umbrales para conseguir aciertos. En la
reconstrucción se reserva la unión de **todas** las zonas, más 80 m, en cada fecha.
El conjunto de entrenamiento final cambia al incorporar esas zonas, siguiendo
la misma regla previamente fijada.

| Referencia | Evidencia conservada |
|---|---|
| 45137A00900001 | Agua el 14 y 31/10/2026; parte es laguna semipermanente; NDVI positivo el 31 |
| 45137A00900059 | Laguna y agua en ambas fechas de octubre; el usuario localiza agua marcada como inválida el 16/08/2023 |
| 45137A03300153 / 155 | Episodios de agosto bajo vegetación; sur de 153 y mayor agua en 155; no confirma cada pasada |
| 45137A03300074 / 153 / 155 | Inicio seguro del riego por inundación el 30/07/2023; no implica continuidad hasta el 16/08 |
| 45137A00700014 | Encharcamiento intermitente el 31/10/2026, referencia adicional fechada |
| 45137A00900013 / 45137A00800001 | Pequeñas lagunas intermitentes, sin fechas individuales de presencia |
| 45137A01000045 | Laguna, sin correspondencia temporal confirmada por adquisición |
| 45137A01200109 | Construcciones, confusión confirmada para 31/10/2026 |
| 45137A01200001 | Edificios y paneles solares, confusión confirmada para 31/10/2026 |
| 45137A04000023 | Nave ganadera señalada por la capa, 31/10/2026 |
| 45137A01200080 | Parcela completamente construida según usuario; control del 31/10/2026 |

Los contextos heredados `east_bare_soil`, `north_dense_crop`,
`northwest_roof_context` y `west_dark_context` se mantienen como **contextos sin
clase independiente**, no como controles negativos confirmados. Faltan suelo
seco confirmado, suelo húmedo sin lámina, sombra y cultivo comparable sin
afección, todos con zona y fecha. Edificios y paneles ya tienen parcelas y fecha;
faltan sus huellas para medir solapamientos en parcelas mixtas.

Se conserva la valoración favorable del usuario sobre NDWI para lámina libre
el 31/10, sin convertirla en porcentaje de exactitud ni atribuirla al reescalado.
Sus éxitos adicionales de reescalado siguen pendientes de identificar por
método, zona y fecha. Los candidatos recuperados del estudio previo sí se incluyen.
Las otras zonas de río/laguna con datos inválidos el 16/08 quedan pendientes de
localizar; el usuario aclaró que no se refería a 153, 155 y 074.

El descenso comunicado desde el 10 al 31/10 no se transforma en tendencia de
superficie, índices o volumen. No se inventa una adquisición del día 10. La
serie previa de trece imágenes de agosto permanece en `../water-evidence/`:
once utilizables no equivalen a once confirmaciones de agua. Este bloque ejecuta
el contraste completo en 16/08, 14/10 y 31/10.

## Datos congelados y protocolo

Productos originales completos del AOI, reutilizados desde
`artifacts/water-review/products/`:

* `S2A_MSIL2A_20230816T105631_N0509_R094_T30TUK_20230816T171602`
* `S2A_MSIL2A_20261014T110941_N0513_R137_T30TUK_20261014T173008`
* `S2A_MSIL2A_20261031T110121_N0513_R094_T30TUK_20261031T173605`

[frozen.json](frozen.json) registra manifiestos, hashes de bandas DN, origen,
escala/offset, nodata, rejillas, dimensiones, coeficientes y diagnóstico.
[protocol.json](protocol.json) registra versiones y hashes del código. El RGB
añade únicamente B02 original de cada mismo SAFE, con identidad y rejilla
comprobadas; B03/B04 se reutilizan. No se utiliza un RGB de otra fecha.

Agosto es **05.09**, mientras que la adquisición publicada es el reprocesado
05.10 `S2A_MSIL2A_20230816T105631_N0510_R094_T30TUK_20241021T044404`.
No se mezclan; el programa rechaza fechas duplicadas entre productos. Por ello,
la auditoría histórica ayuda a investigar la observación de inválidos del visor,
pero no demuestra identidad píxel a píxel con ese reprocesado publicado.

Se convierten DN a reflectancia una vez, excluyendo nodata antes del cálculo.
Se exige CRS métrico y rejillas anidadas exactas; se comprueban todas las bandas.
NDWI y MNDWI recalculados deben coincidir exactamente con los productos
conservados. El detector B debe reproducir exactamente `WATER.tif`.
Nodata, negativos y baja señal conservan su condición de exclusión: no se
rellenan con cero ni se recortan a −1 para clasificar. Las áreas son
intersecciones geométricas con la parcela, incluidos píxeles parciales.

| Variante | Índice y soporte |
|---|---|
| A | NDWI de verde/NIR nativos de 10 m; comparador adicional |
| B | MNDWI original de 20 m: verde agregado y B11 original; replicado para visualizar y cruzar soportes |
| C | MNDWI con verde nativo y B11 por vecino próximo |
| D | MNDWI con B11 guiada por NDWI |
| E | MNDWI con B11 guiada por NDWI+NDVI |

B–E mantienen **MNDWI > 0**, calidad SCL 4/5/6, suma mínima 0,01 y
resto de parámetros fijos. A utiliza NDWI > 0 y no es el mismo clasificador.
Se ejecuta también el detector operativo sin cambiar sus umbrales, diferenciando
agua estimada, ambigüedad y no evaluable. Se usan las guías de cada adquisición.
El ridge actual es global por adquisición, con detalle intrabloque y conservación
de media; no es regresión local ni reproducción completa de Yang et al.

[comparison.csv](comparison.csv) contiene cobertura propia, porcentaje sobre
parcela, soporte común B–E y A–E, positivos propios/comunes y estados del detector.
La comparación B–E utiliza la intersección válida; los candidatos excluidos de
ella siguen visibles en las columnas de soporte propio. Un aumento de cobertura
no se confunde con una mejora del detector.

## Calidad: agua observada y datos inválidos

[quality.json](quality.json) cuantifica por zona/fecha SCL por clase, reflectancias
negativas y ausentes por banda, baja señal, MNDWI no disponible y sensibilidad
separada a 0 / 0,005 / 0,01 / 0,02. Los motivos se solapan y **no se suman**.
El suelo 0,01 es una decisión conservadora, no una estimación instrumental del ruido.

En **45137A00900059, 16/08/2023**, NDWI conserva 33.335,338 de 42.127,356 m²
(79,13 %): quedan fuera 8.792,018 m². La SCL excluye 5.329,571 m², todos
clase 7 en esta parcela; hay 2.555,729 m² con NIR negativo, 33,159 m² con NIR
ausente y 4.655,729 m² con suma verde+NIR ≤0,01, con solapamientos entre causas.
Esto es compatible con pérdida de cobertura sobre la laguna comunicada; falta
su contorno para localizar exactamente cuánto del agua queda excluido.

| Suelo de señal | NDWI válido, m² | NDWI >0, m² | MNDWI original >0, m² |
|---|---:|---:|---:|
| 0 | 34.935,338 | 1.900 | 0 |
| 0,005 | 34.335,338 | 1.400 | 0 |
| 0,01 | 33.335,338 | 800 | 0 |
| 0,02 | 32.735,338 | 700 | 0 |

Bajar el suelo recupera señal en este caso, pero no corrige SCL ni negativos y
no demuestra que todos los nuevos positivos sean agua. La prueba cambia sólo
la elegibilidad de los índices nativos; no reajusta reconstrucción y detector.

El 14/10, la misma parcela cambia de 4.650,822 a 1.295,093 m² de NDWI positivo
entre los extremos del suelo; con 0,01 son 2.895,093 m². En 00001, el 14/10,
hay 2.500 m² con verde negativo y 1.200 m² sin MNDWI; bajar el suelo no crea
NDWI ni MNDWI positivos. Son problemas distintos y requieren decisiones separadas.

## Candidatos recuperados y confusiones

Superficies **candidatas** en soporte común B–E, m²; no son superficies inundadas
validadas. A se muestra adicionalmente en ese soporte.

| Parcela / fecha | B | C | D | E |
|---|---:|---:|---:|---:|
| 00059 · 14/10/2026 | 0 | 0 | 900 | 700 |
| 00059 · 31/10/2026 | 0 | 0 | 1.440,901 | 1.566,318 |
| 00001 · 14/10/2026 | 0 | 0 | 0 | 0 |
| 00001 · 31/10/2026 | 0 | 0 | 100 | 700 |
| 03300153 / 03300155 · 16/08/2023 | 0 | 0 | 0 | 0 |
| 00700014 · 31/10/2026 | 800 | 700 | 600 | 1.900 |
| 00900013 · 31/10/2026 | 0 | 0 | 500 | 200 |
| 01000045 · 31/10/2026 | 5.600 | 5.700 | 7.300 | 7.600 |
| 00800001 · 31/10/2026 | 1.200 | 1.000 | 1.200 | 1.400 |

00001/00059 de octubre conservan los candidatos recuperados conocidos. En 00700014,
referencia nueva con agua fechada, NDWI >0 da cero, mientras B–E conservan
candidatos y E amplía la señal. Las últimas tres lagunas carecen de confirmación
individual de agua para esa pasada: se muestran como contexto, no aciertos fechados.

La cobertura común el 14/10 es 22.560,528 m² en 00001 y 35.935,338 m² en
00059, frente a totales de 27.760,528 y 42.127,356 m². El 31/10 ambas son
completamente válidas. En 00059 de agosto el soporte común es 31.635,338 m²:
NDWI tiene 800 m² positivos propios y 700 comunes; B–E ninguno.

Manteniendo el **detector operativo**, 00001 y 00700014 siguen sin agua estimada
aunque aparezcan candidatos MNDWI. En 00059, el 14/10 todas las variantes dan
1.000 m² y el 31/10 B/C/D dan 800 m² y E 1.000 m². La reconstrucción y la
regla de decisión tienen límites diferentes; la mejora de un índice no implica
automáticamente mejora de la salida operativa.

| Construcciones · 31/10/2026 | A >0 | B >0 | C >0 | D >0 | E >0 | Operativo B: agua / ambigua |
|---|---:|---:|---:|---:|---:|---:|
| 45137A01200109 | 1.115,084 | 534,736 | 583,296 | 473,946 | 965,947 | 0 / 1.475,778 |
| 45137A01200001 | 2.824,106 | 0 | 176,422 | 100 | 176,422 | 0 / 2.824,106 |
| 45137A01200080 | 0 | 0 | 100 | 100 | 100 | 0 / 0 |
| 45137A04000023 | 400 | 0 | 0 | 0 | 0 | 0 / 400 |

En estas cuatro parcelas hay cobertura completa el 31/10. La confusión señalada
por el usuario aparece numéricamente sobre todo como **ambigüedad o NDWI positivo**,
no como clase operativa 1 en los productos auditados. No se descarta su observación:
se documenta la correspondencia de clases. D no elimina el problema y E aumenta
la señal en 01200109. En 01200080, completamente construida según el usuario,
C/D/E introducen 100 m² que B no tenía. No se asigna un falso positivo a cada
píxel de las otras parcelas mixtas sin huellas independientes.

## Reconstrucción reducida 40→20 m

Filtro box de área 2×2 antes de decimar B11; se recorta la última fila/columna
si es impar. No se ha calibrado la MTF del sensor: es una prueba reducida
reproducible, no una simulación instrumental completa. Se agregan reflectancias
verde/NIR/rojo 10→20 **antes** de calcular las guías. No se promedian índices.

Ridge 1e−6 por fecha, sin penalizar intercepto; los coeficientes excluyen zonas
completas y halo de 80 m. Si cualquier hijo de un bloque de 40 m cae en esa
reserva, se excluye el bloque entero. B11 observada de 20 m en la reserva sólo
se usa para contraste; el promedio degradado de 40 m es la entrada legítima
de reconstrucción. No hay reparto aleatorio de vecinos entre ajuste y evaluación.

RMSE en reflectancia, soporte común de las tres reconstrucciones; `n` es número
de centros de celda de 20 m, no superficie ponderada ni número de observaciones
independientes. [reconstruction.csv](reconstruction.csv) y
[reconstruction.json](reconstruction.json) incluyen sesgo, MAE, RMSE y cobertura
propia/común para cada zona/fecha y estrato.

| Parcela / fecha | n | Vecino próximo | D | E |
|---|---:|---:|---:|---:|
| 03300153 · 16/08 | 133 | 0,025827 | 0,013529 | 0,013665 |
| 03300155 · 16/08 | 84 | 0,019883 | 0,013308 | 0,018465 |
| 00900059 · 16/08 | 73 | 0,044854 | 0,030618 | 0,022922 |
| 00900001 · 14/10 | 62 | 0,044224 | 0,023961 | 0,023717 |
| 00900059 · 14/10 | 93 | 0,039945 | 0,037131 | 0,028370 |
| 00900001 · 31/10 | 70 | 0,038694 | 0,037818 | 0,025144 |
| 00900059 · 31/10 | 109 | 0,035681 | 0,042647 | 0,023551 |
| 00700014 · 31/10 | 343 | 0,021026 | 0,020453 | 0,017590 |

D mejora el RMSE frente al vecino en 33 de 51 unidades y E en 37 de 51. Son
recuentos descriptivos correlacionados, no tasas de acierto del detector ni
pruebas de transferencia. D empeora claramente en 00059 el 31/10; E no domina
en todos los casos, por ejemplo agosto en 155 favorece D.

Los bordes se fijaron como contraste B11 nativo entre vecinos >0,03; no son
contornos de agua. Hay estratos SCL4/5/6 e interior. Ejemplo E en 00700014 el
31/10: RMSE de borde 0,017823 (`n=181`) e interior 0,017327 (`n=162`);
SCL4 0,019927 (`n=73`) y SCL5 0,016903 (`n=270`). SCL6 tiene `n=0` y métricas
nulas, nunca cero inventado. SCL se utiliza como estrato, no como verdad de agua.

## Conservación y artefactos 20→10 m

En los tres AOI, D/E no producen negativos y el RMSE de reagregación está entre
1,07×10⁻⁸ y 1,18×10⁻⁸. Esto prueba conservación, no veracidad del detalle.
El diagnóstico registra desviaciones fuera del rango de padres vecinos 3×3,
amplitud de detalle y saltos dentro/entre bloques. Son indicadores de posibles
halos o discontinuidades, no un inventario de artefactos confirmados.

| Fecha | Fuera de rango vecino D / E, píxeles | Desacuerdos de signo D/E / soporte común |
|---|---:|---:|
| 16/08/2023 | 110.360 / 112.267 | 1.297 / 934.332 |
| 14/10/2026 | 92.157 / 159.009 | 3.749 / 942.548 |
| 31/10/2026 | 68.695 / 177.147 | 8.025 / 951.016 |

Los conteos de rango vecino usan el soporte propio de cada reconstrucción;
no deben compararse como tasas sin denominador. En octubre E introduce mayor
detalle y más salidas del rango vecino. Los desacuerdos muestran dependencia de
guía y fecha; no se fuerza estabilidad de agua real entre fechas diferentes.

La prueba reducida incluye desplazamientos artificiales ±1 celda (20 m) en
cada eje, con bordes de imagen excluidos. Son sensibilidad a registro, no una
medición del desplazamiento real de agua de 10 m; las máscaras pueden cambiar
de tamaño y se conserva `n`. Sin verdad de 10 m no puede inferirse un error
geométrico exacto. La semejanza con NDWI no valida independientemente D/E.

## Comparador publicado: Sen2Res

Se valora **sólo Sen2Res**, asociado a Brodu (2017). La
[documentación oficial de ESA](https://step.esa.int/main/snap-supported-plugins/sen2res/)
describe un complemento SNAP que usa información geométrica compartida entre
las cuatro bandas nativas de 10 m y reflectancias dependientes de banda,
conservando reflectancia. Esa estructura es diferente de nuestro ridge de índices.

Dependencias: SNAP y módulo Sen2Res; producto Sentinel-2 reconocido y sus bandas
nativas, memoria suficiente y recorte ROI; el sitio ofrece módulo 1.1 y
construcción Maven. Se comprobó SNAP 8 instalado con `gpt -h`: **Sen2Res no está
en los operadores disponibles**. Los recortes de seis bandas del estudio no
constituyen por sí solos el producto de entrada del complemento. Se considera
viable como comparador posterior con instalación/versionado del módulo y prueba
de compatibilidad L2A/baseline. **No se ejecutó ni se asignan resultados numéricos
a Sen2Res**. No se implementó una aproximación y se llamó reproducción del artículo.

Marco metodológico: [Du et al. 2016](https://doi.org/10.3390/rs8040354),
[Yang et al. 2017](https://doi.org/10.3390/rs9060596),
[Brodu 2017](https://doi.org/10.1109/TGRS.2017.2694881),
[Ármannsson et al. 2021](https://doi.org/10.3390/rs13112192) y
[Roberts et al. 2017](https://doi.org/10.1111/ecog.02881).
Se consultó la documentación primaria de Sen2Res y fuentes primarias accesibles;
los accesos restringidos de las editoriales no se presentan como lectura completa
ni reproducción de sus experimentos. La reserva espacial sigue el principio de
evaluar fuera de la estructura vecina del ajuste, sin prometer independencia
completa entre fechas de una misma zona.

## Mapas y reproducción

Hay **51 mapas JPEG**, uno por unidad del inventario. RGB del mismo SAFE (0–0,30,
gamma 1,3), A–E con escala fija [−1,1], y candidatos >0 en soporte común B–E.
Magenta delimita la zona, gris indica exclusión, blanco ausencia de candidato y
azul candidato. El panel de soporte usa negro para válido y blanco para excluido;
los índices superiores muestran cobertura propia. Son representaciones de los
mismos arrays usados en las tablas, sin interpolación gráfica del detalle.

* [Laguna 00059, agosto e inválidos](45137A00900059-2023-08-16.jpg)
* [00001, candidatos recuperados el 31/10](45137A00900001-2026-10-31.jpg)
* [00700014, referencia adicional del 31/10](45137A00700014-2026-10-31.jpg)
* [Edificios y paneles 01200001](45137A01200001-2026-10-31.jpg)
* [155, agosto con vegetación](45137A03300155-2023-08-16.jpg)

Python con GDAL, NumPy y matplotlib. Ejecución auditada: Python 3.12.9,
GDAL 3.10.2, NumPy 1.26.4 (entorno QGIS 3.40.4). Desde la raíz del repositorio,
para reutilizar los productos conservados:

```sh
python scripts/download_b11_rgb.py artifacts/water-review/raw artifacts/water-review/products artifacts/water-review/rgb
python scripts/b11_cycles.py artifacts/water-review/products docs/b11-cycles
python scripts/b11_cycles.py artifacts/water-review/products artifacts/b11-repeat
python -m unittest discover -s scripts -p 'test_*.py'
```

Para reconstruir entradas desde los catálogos públicos congelados, usar otra
carpeta, preservando los SAFE exactos; requiere red y disponibilidad del espejo:

```sh
python scripts/download_water_reference.py docs/water-evidence/august-catalogue.json artifacts/b11-reproduce/raw --dates 2023-08-16
python scripts/download_water_reference.py docs/water-evidence/october-catalogue.json artifacts/b11-reproduce/raw --cdse-catalogue docs/water-evidence/october-cdse.json --dates 2026-10-14 2026-10-31
python scripts/water_reference_study.py artifacts/b11-reproduce/raw artifacts/b11-reproduce/products --refs 45137A00900001 45137A00900059 45137A03300153 45137A03300155 --report artifacts/b11-reproduce/preparation.json
python scripts/download_b11_rgb.py artifacts/b11-reproduce/raw artifacts/b11-reproduce/products artifacts/b11-reproduce/rgb
python scripts/b11_cycles.py artifacts/b11-reproduce/products artifacts/b11-reproduce/results
```

`--refs` en el procesamiento sólo limita el informe previo, no recorta el AOI.
No usar `--refs` en la descarga de esta reproducción: cambiaría el contexto del
ajuste. Los rásteres pesados permanecen fuera de Git. Una nueva escritura TIFF
puede cambiar hashes comprimidos por versión GDAL; en ese caso deben verificarse
SAFE, valores, rejillas y escala/offset, sin fingir identidad binaria. No se volvió
a descargar el AOI entero durante este bloque: se reutilizaron los originales
conservados y se completó B02 para RGB.

En Windows se ejecutó con `C:\Program Files\QGIS 3.40.4\bin\python-qgis-ltr.bat`.
Para los gates Python ajenos a QGIS se utilizó `python -X utf8` por la codificación
de consola. No se modificó código operativo para resolver esa diferencia local.

## Verificación y cierre por objetivo

59 pruebas Python con GDAL superadas, incluidas seis nuevas: ausencia de fuga al
ajuste, conservación, reproducción determinista, propagación de máscaras, orden
de agregación de reflectancias, áreas parciales, métricas vacías y semántica de
fechas/referencias. Las regresiones existentes incluyen rejillas y detección.
También se ejecutan los nueve scripts Node del gate, política de localización y
gate offline. La comprobación completa por segunda ejecución y sus hashes se
registra en [validation.json](validation.json). Las figuras se inspeccionan
visualmente; no se requiere prueba del visor porque no cambia en este bloque.

| Objetivo / superficie | Decisión | Evidencia y límite |
|---|---|---|
| Conservación y reconstrucción B11 en zonas reservadas | **Avanza**, como línea de investigación | Conservación y menor RMSE en múltiples zonas frente a vecino; no demuestra detalle verdadero a 10 m |
| Selección general de una guía | **Revisa** | E mejora varios casos y D otros; D empeora 00059 el 31/10, E amplifica señal construida |
| Lámina libre / lagunas de octubre | **Revisa** | Candidatos recuperados y valoración positiva de NDWI; sin contornos no se valida precisión espacial |
| Encharcamiento de 00700014 el 31/10 | **Revisa** | MNDWI conserva señal que NDWI no muestra; E amplía candidatos, detector operativo sigue sin agua estimada |
| Agua bajo vegetación en 153/155, agosto | **No concluyente** para exactitud por pasada | Omisión descriptiva en 16/08; presencia intermitente mensual, sin contorno ni certeza de cada pasada |
| Laguna 00059: agua marcada como inválida en agosto | **Revisa** | Exclusiones radiométricas/SCL cuantificadas y sensibilidad al suelo; falta contorno y contraste exacto con baseline publicado |
| Construcciones y paneles | **Revisa** | Controles nuevos identifican señales no deseadas; más detalle no basta para distinguir materiales |
| Suelo húmedo, sombra y cultivo comparable | **No concluyente** | Faltan controles independientes fechados |
| Precisión, sensibilidad, F1/IoU, contorno y error de superficie de agua | **No concluyente** | Sin etiquetas espaciales suficientes; no se inventan métricas ni hectáreas validadas |

Para resolver lo pendiente: huellas de edificios/paneles y agua, fechas de las
lagunas intermitentes, localización de los éxitos adicionales del reescalado y
de los otros inválidos sobre río/laguna, y controles negativos fechados. La
observación parcelaria no se convierte en probabilidad calibrada, profundidad
ni volumen. Los ciclos temporales, SAR, integración y transferencia operativa
quedan fuera de esta entrega y se plantearán tras la revisión del usuario.
