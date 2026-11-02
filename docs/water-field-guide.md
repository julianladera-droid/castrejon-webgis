# Aproximación de encharcamiento para visitas de campo

Integración autorizada por el usuario el 02/11/2026, posterior al estudio de la
PR #7. El objetivo es localizar zonas que conviene visitar, con comprobación in
situ. No se atribuye una exactitud espacial validada al resultado.

## Lectura del visor

| Color | Interpretación | Uso en campo |
|---|---|---|
| Azul | Agua superficial estimada por el detector anterior | Comprobar lámina y extensión |
| Morado | Posible mezcla o agua residual, añadida con B11 estimada | Priorizar inspección; puede ser otra superficie oscura |
| Ámbar | Señal dudosa | Contrastar con vegetación, sombras, edificios y paneles |
| Gris | No evaluable en esa adquisición | No interpretarlo como ausencia de agua |

Seleccionar una fecha y activar «Posible encharcamiento». Al pulsar una parcela,
la ficha muestra por separado el agua estimada y los metros cuadrados candidatos
que se deben revisar. Los porcentajes se refieren a la superficie de parcela
dentro de la zona regable. Las superficies se calculan en EPSG:25830 por
intersección fraccional de celdas, no midiendo la imagen en pantalla.

La reconstrucción aporta detalle estimado en una rejilla de 10 m; B11 se observa
a 20 m. NDWI de 10 m y MNDWI nativo de 20 m mantienen sus valores y máscaras.
La capa de agua corresponde a la fecha elegida: una laguna preexistente sigue
apareciendo. Los cambios entre fechas sólo usan celdas clasificables en ambas,
sin contar candidatos, ambigüedad o falta de datos como aparición/desaparición.

## Método aplicado

`optical_field_visit_v3` conserva **todos** los píxeles de agua y no evaluables
del detector v2. Usa la reconstrucción E existente, guiada por NDWI y NDVI,
ajustada globalmente por adquisición sin etiquetas y conservando medias de B11.
No se introduce un reconstruidor nuevo.

En celdas interpretables que no eran agua ni no evaluables, un MNDWI estimado
positivo añade una señal dudosa. Se diferencia como candidata residual cuando
NDWI ≤ 0, B11 estimada está entre 0 y 0,08 y B08/B8A entre 0 y 0,15. Es la
hipótesis H1 sobre E del estudio, conservando su carácter candidato. Si faltan
bloques completos para el ajuste, se conserva el resultado anterior y se
registra el motivo en el manifiesto. Las máscaras radiométricas y SCL permanecen.

No se promueve automáticamente a agua toda señal recuperada. No se excluyen
parcelas mixtas enteras por contener edificios. Los falsos positivos anteriores
pueden persistir; esta versión amplía la orientación para visitas, no demuestra
su eliminación. El agua bajo vegetación puede quedar sin detectar. Las anomalías
del cultivo no se convierten en agua por sí solas.

## Comprobación sobre los productos disponibles

[Validación numérica](field-water-validation.json), realizada sobre los recortes
originales conservados y sus versiones v3; los recuentos siguientes abarcan el
rectángulo de proceso, no sólo las parcelas:

| Adquisición | Píxeles de agua conservados | No evaluables conservados | Candidatos añadidos |
|---|---:|---:|---:|
| 16/08/2023, N0510 publicado | 1.957 de 1.957 | 14.174 de 14.174 | 102 |
| 14/10/2026, N0513 | 6.533 de 6.533 | 5.892 de 5.892 | 668 |
| 31/10/2026, N0513 | 9.045 de 9.045 | 0 de 0 | 695 |

Se verificó igualdad de los cinco índices nativos y el balance de superficies
para las 919 parcelas en cada fecha. El 31/10 se añaden 700 m² candidatos en
45137A00900001 y 966,318 m² en 45137A00900059. En 45137A00700014 se señalan
2.200 m² como dudosos. En los cuatro controles de construcciones y paneles
aportados no aparecen candidatos morados en estas tres adquisiciones; esto no
descarta falsos positivos existentes ni acredita precisión general.

El agua excluida de 45137A00900059 en agosto sigue como no evaluable: no se
convierten reflectancias inválidas en una señal inventada. La auditoría separada
N0509/N0510, las firmas y sus límites se conservan en
[el estudio de continuación](b11-followup/README.md).

## Migración y reproducción

Los artefactos v2 se admiten únicamente como entrada a una migración verificada.
Antes de publicar se comprueban hashes y SAFE de los DN originales y se genera
v3 en una carpeta distinta. Las entradas permanecen intactas. El visor exige el
nuevo contrato, con clase 4, `residual_m2` y hashes de tabla y geometrías. Un fallo
de migración o validación detiene el despliegue.

```sh
python scripts/upgrade_sentinel_products.py sentinel-products-v3 sentinel-products
python scripts/build_sentinel_web.py sentinel-products-v3 _site/sentinel --collection
python -m unittest discover -s scripts -p 'test_*.py'
python scripts/check_webgis.py
node scripts/test-water.cjs
```

GDAL y NumPy son necesarios. Para la comprobación local se usaron los recortes
`artifacts/b11-followup/n0510`, `artifacts/b11-followup/published` (31/10) y el
SAFE de 14/10 de `artifacts/water-review/products`. El JSON conserva los SAFE
completos. No se mezcló el producto N0509 con el N0510 publicado.

Regresiones: conservación de clases previas, máscaras, rechazo de DN alterados,
migración y copia v3, candidatos y ambigüedad separados, superficies fraccionales,
transiciones sin candidatos y contrato de interfaz. También se verificaron el
visor con datos reales, cambio de fecha, ficha de parcela y tamaños móviles.

Decisión: **Avanza** como orientación para visitas de campo; **Revisa** señales
en materiales construidos; **No concluyente** para presencia de agua bajo
vegetación o en píxeles inválidos sin observaciones locales adicionales.
