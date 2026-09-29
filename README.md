# castrejon-webgis

Visor de control de la **C.R. Canal de Castrejón Margen Derecha**.

## Estado
M0.2 — visor cartográfico estático para pruebas.

Capas actuales:
- PNOA Máxima Actualidad (IGN/CNIG), XYZ/TMS.
- Recintos SIGPAC (FEGA/MAPA), WMS.
- Catastro INSPIRE, límites de parcela.

## Arquitectura de esta fase
GitHub Pages sirve únicamente el frontend estático. WordPress actúa como portal y enlaza al visor. Los servicios cartográficos se consumen directamente desde sus proveedores oficiales.

No contiene todavía cartografía interna, datos personales, telemetría ni simulaciones.

## CRS
- EPSG:25830: CRS maestro técnico de datos internos futuros.
- EPSG:3857: visualización web.
- EPSG:4326: coordenadas e intercambio.

## Desarrollo
En esta fase `index.html` es autocontenido salvo OpenLayers y los servicios cartográficos externos. La evolución futura prevista es React + TypeScript + OpenLayers con API FastAPI y PostgreSQL/PostGIS.

## Despliegue con GitHub Pages
El workflow `.github/workflows/pages.yml` publica el contenido del repositorio como sitio estático.

En el repositorio de GitHub, activar una vez **Settings → Pages → Build and deployment → Source: GitHub Actions**. Después, cada push a `main` despliega automáticamente.

## Regla del proyecto
Antes de introducir cambios estructurales, consultar y actualizar `SKILL_CASTREJON_WEBGIS.md`.