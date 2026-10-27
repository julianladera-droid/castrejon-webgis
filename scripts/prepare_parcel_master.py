"""Export original metric parcel geometry for build-time zonal statistics only."""
import argparse
import hashlib
import json
from pathlib import Path
from osgeo import ogr, osr


def prepare(source, output, web_folder):
    ogr.UseExceptions()
    meta = json.loads((web_folder/'metadata.json').read_text(encoding='utf-8'))
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if digest(source) != meta['source_sha256'] or digest(web_folder/'parcelas.geojson') != meta['web_sha256']:
        raise ValueError('Parcel source/web checksum mismatch')
    web = json.loads((web_folder/'parcelas.geojson').read_text(encoding='utf-8'))
    areas = {f['id']: f['properties']['area_m2'] for f in web['features']}
    ds = ogr.Open('/vsizip/' + source.resolve().as_posix() + '/parcelas_zr.shp')
    layer = ds.GetLayer()
    crs = osr.SpatialReference(); crs.ImportFromEPSG(25830)
    if not layer.GetSpatialRef().IsSame(crs):
        raise ValueError('Expected original EPSG:25830')
    features = []
    for feature in layer:
        ref = feature.GetField('REFCAT'); geom = feature.GetGeometryRef()
        if (ref not in areas or geom is None or geom.IsEmpty() or not geom.IsValid()
                or ogr.GT_Flatten(geom.GetGeometryType()) not in (ogr.wkbPolygon, ogr.wkbMultiPolygon)
                or abs(geom.GetArea()-areas[ref]) > .001):
            raise ValueError('Invalid original parcel')
        features.append({'refcat': ref, 'geometry': json.loads(geom.ExportToJson(['COORDINATE_PRECISION=15']))})
    if len(features) != 919 or {f['refcat'] for f in features} != set(areas):
        raise ValueError('Parcel identity mismatch')
    payload = {'version': 1, 'crs': 'EPSG:25830', 'source_sha256': meta['source_sha256'],
               'web_sha256': meta['web_sha256'], 'features': sorted(features, key=lambda f: f['refcat'])}
    output.write_bytes((json.dumps(payload, separators=(',', ':'))+'\n').encode('utf-8'))
    print(f'Prepared {len(features)} original metric parcels: {output.stat().st_size} bytes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    prepare(args.source, root/'data/parcel-master.json', root/'data/parcels')
