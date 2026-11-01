"""Reproducible research download of original public JP2, never harmonized COG DN.

Input is a preserved Earth Search STAC FeatureCollection. Tile metadata must match
the original SAFE product. Each band's own JP2 scale/offset is retained. Production
continues to use CDSE; this public mirror is an explicitly recorded study source.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
import numpy as np
from osgeo import gdal, ogr
from sentinel_pipeline import aligned_bounds, write_raster
from sentinel_contract import RAW_BANDS

NAMES = {'B02': 'blue', 'B03': 'green', 'B04': 'red', 'B08': 'nir',
         'B8A': 'nir08', 'B11': 'swir16', 'SCL': 'scl'}


def download(item, bounds, folder, cdse=None):
    product = item['properties']['s2:product_uri'].removesuffix('.SAFE')
    destination = folder/product
    destination.mkdir(parents=True, exist_ok=True)
    metadata_url = item['assets']['tileinfo_metadata']['href']
    if not metadata_url.startswith('https://sentinel-cogs.s3.us-west-2.amazonaws.com/'):
        raise ValueError('Unexpected metadata host')
    with urlopen(metadata_url, timeout=60) as response:
        metadata = json.load(response)
    if metadata['productName'].removesuffix('.SAFE') != product:
        raise ValueError('Mirror product mismatch')
    source = cdse or {'id': product, 'properties': item['properties'],
                     'geometry': item['geometry'], 'assets': {}}
    audit = {}
    for key, resolution in {**RAW_BANDS, 'B02_10m': 10}.items():
        band = key.split('_')[0]
        asset = item['assets'][NAMES[band]+'-jp2']
        href = asset['href']
        if not href.startswith('s3://sentinel-s2-l2a/tiles/') or '..' in href:
            raise ValueError('Unexpected original JP2 location')
        base = href.rsplit('/', 1)[0]
        if base.endswith(('/R10m', '/R20m', '/R60m')):
            base = base.rsplit('/', 1)[0]
        url = base.replace('s3://sentinel-s2-l2a/', 'https://sentinel-s2-l2a.s3.eu-central-1.amazonaws.com/')+f'/R{resolution}m/{band}.jp2'
        file = destination/f'raw_{key}.tif'
        if not file.exists():
            print('Read original JP2', product, key, flush=True)
            ds = gdal.Warp('', '/vsicurl/'+url, format='MEM', dstSRS='EPSG:25830',
                outputBounds=bounds, xRes=resolution, yRes=resolution, resampleAlg='near',
                srcNodata=0, dstNodata=-9999, outputType=gdal.GDT_Float32)
            write_raster(file, ds.ReadAsArray(), ds, 'raw_'+key, product)
        radiometry = asset['raster:bands'][0]
        if key not in source['assets']:
            source['assets'][key] = {'href': url, 'nodata': radiometry['nodata'],
                'raster:scale': 1 if band == 'SCL' else radiometry['scale'],
                'raster:offset': 0 if band == 'SCL' else radiometry['offset']}
        audit[key] = {'url': url, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}
    # Keep the source catalogue and original product identity, not just the date.
    (destination/'source_item.json').write_text(json.dumps(source, indent=2)+'\n')
    (destination/'mirror.json').write_text(json.dumps({'source': item, 'mirror_identity': metadata,
        'raw_crops': audit, 'requested_bounds_25830': bounds}, indent=2)+'\n')
    print('Ready', product, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalogue', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--cdse-catalogue', type=Path)
    parser.add_argument('--dates', nargs='*')
    parser.add_argument('--refs', nargs='*', help='Optional parcel subset plus 100m context')
    args = parser.parse_args()
    gdal.UseExceptions()
    for key, value in {'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR', 'GDAL_HTTP_TIMEOUT': '90',
                       'GDAL_HTTP_MAX_RETRY': '1', 'GDAL_HTTP_RETRY_DELAY': '30'}.items():
        gdal.SetConfigOption(key, value)
    root = Path(__file__).resolve().parents[1]
    bounds = json.loads((root/'data/sentinel-aoi.json').read_text())['processing_aoi']['bounds']
    if args.refs:
        master = json.loads((root/'data/parcel-master.json').read_text())
        envelopes = [ogr.CreateGeometryFromJson(json.dumps(f['geometry'])).GetEnvelope()
                     for f in master['features'] if f['refcat'] in args.refs]
        if len(envelopes) != len(set(args.refs)):
            raise ValueError('Unknown reference parcel')
        bounds = [min(e[0] for e in envelopes)-100, min(e[2] for e in envelopes)-100,
                  max(e[1] for e in envelopes)+100, max(e[3] for e in envelopes)+100]
    bounds = aligned_bounds(bounds, 20)
    items = json.loads(args.catalogue.read_text())['features']
    cdse = json.loads(args.cdse_catalogue.read_text())['features'] if args.cdse_catalogue else []
    for item in sorted(items, key=lambda x: x['properties']['datetime']):
        if args.dates and item['properties']['datetime'][:10] not in args.dates:
            continue
        original_id = item['properties']['s2:product_uri'].removesuffix('.SAFE')
        match = next((x for x in cdse if x['id'] == original_id), None)
        if args.cdse_catalogue and match is None:
            raise ValueError('Requested exact CDSE product absent in mirror')
        download(item, bounds, args.output, match)


if __name__ == '__main__':
    main()
