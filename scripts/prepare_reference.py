"""Regenerate the reference overlay and Sentinel AOI from an unmodified EPSG:25830 GML.

Run with QGIS/GDAL Python: python prepare_reference.py path/to/ZR.gml
Only local derived files change. No imagery requests or downloads are made.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from osgeo import gdal, ogr, osr


def display_geometry(geom):
    simplified = geom.SimplifyPreserveTopology(15)
    result = ogr.Geometry(ogr.wkbPolygon)
    for index in range(simplified.GetGeometryCount()):
        source = simplified.GetGeometryRef(index)
        points = [source.GetPoint(i)[:2] for i in range(source.GetPointCount()-1)]
        ring = ogr.Geometry(ogr.wkbLinearRing)
        for i, vertex in enumerate(points):
            previous, following = points[i-1], points[(i+1) % len(points)]
            def cut(neighbor):
                distance = math.dist(vertex, neighbor)
                ratio = min(.25, 40/distance) if distance else 0
                return tuple(v+(n-v)*ratio for v, n in zip(vertex, neighbor))
            a, b = cut(previous), cut(following)
            # Quadratic corner: bounded rounding rather than moving long edges.
            for t in (0, .5, 1):
                ring.AddPoint_2D(*((1-t)**2*a[k]+2*(1-t)*t*vertex[k]+t*t*b[k] for k in (0, 1)))
        ring.CloseRings()
        result.AddGeometry(ring)
    if (not result.IsValid() or result.IsEmpty() or
            abs(result.GetArea()/geom.GetArea()-1) >= .01 or
            not geom.Boundary().Buffer(30).Contains(result.Boundary())):
        raise ValueError('Display simplification exceeds geometry safeguards')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--display-only', action='store_true', help='Preserve existing Sentinel AOI metadata')
    args = parser.parse_args()
    gdal.UseExceptions()
    ds = ogr.Open(str(args.source))
    if ds is None or ds.GetLayerCount() != 1:
        raise ValueError('Expected one source layer')
    layer = ds.GetLayer(0)
    srs = layer.GetSpatialRef()
    if srs is None or srs.GetAuthorityCode(None) != '25830':
        raise ValueError('Expected EPSG:25830')
    if layer.GetFeatureCount() != 1:
        raise ValueError('Expected one reference feature; review changes explicitly')
    feature = layer.GetNextFeature()
    geom = feature.GetGeometryRef().Clone()
    if geom.IsEmpty() or not geom.IsValid() or geom.GetGeometryName() != 'POLYGON':
        raise ValueError('Expected a valid nonempty Polygon; no automatic repair')
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(srs, wgs)
    derived = display_geometry(geom)
    derived.Transform(transform)
    identifier = feature.GetField('gml_id')
    collection = {'type': 'FeatureCollection', 'features': [{
        'type': 'Feature', 'id': identifier,
        'properties': {'source_id': identifier, 'role': 'irrigable_zone_reference',
                       'status': 'pending_adjustment', 'display_simplified': True},
        'geometry': json.loads(derived.ExportToJson(['COORDINATE_PRECISION=6']))}]}

    # Technical rectangle stays metric. Densify its edges before calculating
    # a conservative lon/lat bbox, since a projected rectangle has curved edges.
    xmin, xmax, ymin, ymax = geom.GetEnvelope()
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin)]:
        ring.AddPoint_2D(x, y)
    rectangle = ogr.Geometry(ogr.wkbPolygon)
    rectangle.AddGeometry(ring)
    if not rectangle.Contains(geom) and not rectangle.Equals(geom):
        raise ValueError('Rectangle does not contain the reference geometry')
    geographic = rectangle.Clone()
    geographic.Segmentize(100)
    geographic.Transform(transform)
    west, east, south, north = geographic.GetEnvelope()
    bbox = [math.floor(west*1e5)/1e5, math.floor(south*1e5)/1e5,
            math.ceil(east*1e5)/1e5, math.ceil(north*1e5)/1e5]
    for lon, lat in collection['features'][0]['geometry']['coordinates'][0]:
        if not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
            raise ValueError('Geographic bbox excludes a perimeter vertex')
    metadata = {
        'source_file': args.source.name,
        'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
        'source_id': identifier, 'status': 'reference_pending_adjustment',
        'reference_area_ha_epsg25830': geom.GetArea()/10000,
        'processing_aoi': {'type': 'enclosing_rectangle', 'crs': 'EPSG:25830',
                           'bounds_order': ['min_x', 'min_y', 'max_x', 'max_y'],
                           'bounds': [xmin, ymin, xmax, ymax],
                           'area_ha': rectangle.GetArea()/10000},
        'catalog_bbox': {'crs': 'EPSG:4326', 'bounds': bbox,
                         'method': 'UTM rectangle edges sampled every <=100 m; rounded outward to 0.00001 degrees'},
        'stac_search_draft': {'collections': ['sentinel-2-l2a'], 'bbox': bbox, 'limit': 20},
        'imagery_status': 'not_requested_or_downloaded',
        'notes': ['Choose datetime and scene quality before submitting the STAC request.',
                  'Process on the rectangular AOI; keep reference polygon separate for later adjustment.',
                  'The rectangle area is not the irrigable area. Align output grid outward to pixel resolution.',
                  'This bbox filters the catalogue; scene asset downloads may still cover full tiles.']}
    root = Path(__file__).resolve().parents[1]
    page = root/'index.html'
    html = page.read_text(encoding='utf-8')
    start = '  // BEGIN ZONA REGABLE DATA'
    end = '  // END ZONA REGABLE DATA'
    if html.count(start) != 1 or html.count(end) != 1:
        raise ValueError('Expected unique data markers')
    before, remainder = html.split(start)
    _, after = remainder.split(end)
    block = start + ' — generated by scripts/prepare_reference.py\n'
    block += '  const zonaRegableData = ' + json.dumps(collection, ensure_ascii=False, separators=(',', ':')) + ';\n'
    page.write_text(before + block + end + after, encoding='utf-8')
    (root/'data').mkdir(exist_ok=True)
    if not args.display_only:
        (root/'data'/'sentinel-aoi.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'source_vertices': geom.GetGeometryRef(0).GetPointCount(),
                      'display_vertices': derived.GetGeometryRef(0).GetPointCount(),
                      'geometry_bytes': len(json.dumps(collection, separators=(',', ':')))}))


if __name__ == '__main__':
    main()
