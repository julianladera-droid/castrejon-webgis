"""Validate the supplied parcel ZIP and export only public geometry/identity.

Run with QGIS/GDAL Python. Original EPSG:25830 ZIP is retained locally for
future zonal statistics; the web copy must never become the calculation source.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from osgeo import ogr, osr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    ogr.UseExceptions()
    root = Path(__file__).resolve().parents[1]
    source = args.source.resolve()
    ds = ogr.Open('/vsizip/' + source.as_posix() + '/parcelas_zr.shp')
    layer = ds.GetLayer()
    master = osr.SpatialReference()
    master.ImportFromEPSG(25830)
    if not layer.GetSpatialRef().IsSame(master):
        raise ValueError('Expected EPSG:25830')
    target = osr.SpatialReference()
    target.ImportFromEPSG(4326)
    master.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(master, target)
    features, ids = [], set()
    total = 0
    for feature in layer:
        ref = feature.GetField('REFCAT')
        geom = feature.GetGeometryRef()
        if not isinstance(ref, str) or not ref or ref in ids:
            raise ValueError('Missing/duplicate REFCAT')
        if geom is None or geom.IsEmpty() or not geom.IsValid() or ogr.GT_Flatten(geom.GetGeometryType()) not in (ogr.wkbPolygon, ogr.wkbMultiPolygon):
            raise ValueError('Invalid parcel geometry')
        ids.add(ref)
        area = geom.GetArea()
        total += area
        web = geom.Clone()
        web.Transform(transform)
        # No smoothing: neighbouring parcel boundaries must remain coincident.
        geometry = json.loads(web.ExportToJson(['COORDINATE_PRECISION=15']))
        if not ogr.CreateGeometryFromJson(json.dumps(geometry)).IsValid():
            raise ValueError('Precision change invalidated a parcel')
        features.append({'type': 'Feature', 'id': ref, 'properties': {
            'refcat': ref, 'area_m2': round(area, 3)}, 'geometry': geometry})
    if len(features) != 919:
        raise ValueError('Unexpected delivery count')
    features.sort(key=lambda item: item['id'])
    output = root / 'data' / 'parcels'
    output.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({'type': 'FeatureCollection', 'features': features}, ensure_ascii=False, separators=(',', ':')) + '\n'
    (output/'parcelas.geojson').write_bytes(payload.encode('utf-8'))
    metadata = {'version': 1, 'delivery_date': '2026-10-14', 'count': len(features),
                'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'web_sha256': hashlib.sha256(payload.encode()).hexdigest(),
                'master_crs': 'EPSG:25830', 'web_crs': 'EPSG:4326', 'join_key': 'refcat',
                'area_m2': total, 'area_meaning': 'Geometric area clipped to ZR, not accredited irrigated area',
                'source': 'Catastro INSPIRE; supplied clipped parcel delivery',
                'excluded': 'Rustic parcel codes 09000 through 09999; not a complete road-use classification'}
    (output/'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    archive = root/'sentinel-output'/'parcel-master'
    archive.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, archive/source.name)
    print(json.dumps({'count':len(features), 'web_bytes':len(payload.encode()), 'area_ha':total/10000}))


if __name__ == '__main__':
    main()

