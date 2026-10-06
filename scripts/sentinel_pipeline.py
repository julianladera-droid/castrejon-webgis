"""Download existing CDSE L2A bands into the rectangular AOI; produce quality-masked indices.

Requires GDAL with JP2OpenJPEG and NumPy. Credentials are environment variables,
never browser cookies. Use --catalogue-only to validate selection without secrets.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

import numpy as np
from osgeo import gdal, ogr

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'https://stac.dataspace.copernicus.eu/v1/search'
BANDS = {'B04_10m': 10, 'B08_10m': 10, 'B8A_20m': 20, 'B11_20m': 20, 'SCL_20m': 20}


def aligned_bounds(bounds, resolution):
    return [math.floor(bounds[0]/resolution)*resolution,
            math.floor(bounds[1]/resolution)*resolution,
            math.ceil(bounds[2]/resolution)*resolution,
            math.ceil(bounds[3]/resolution)*resolution]


def select_scene(features, bbox):
    west, south, east, north = bbox
    area = ogr.CreateGeometryFromWkt(
        f'POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))')
    eligible = []
    for item in features:
        cloud = item['properties'].get('eo:cloud_cover')
        if cloud is None or not 0 <= cloud <= 20 or not all(k in item['assets'] for k in BANDS):
            continue
        footprint = ogr.CreateGeometryFromJson(json.dumps(item['geometry']))
        if footprint and footprint.Contains(area):
            eligible.append(item)
    if not eligible:
        raise ValueError('No complete L2A scene with tile cloud <=20% in the requested interval')
    return max(eligible, key=lambda f: (f['properties']['datetime'], -f['properties']['eo:cloud_cover'], f['id']))


def indices(red, nir, narrow, swir, scl10, scl20):
    # Conservative quality mask; retain vegetation, bare/nonvegetated ground and water.
    valid10 = np.isin(scl10, [4, 5, 6]) & np.isfinite(red) & np.isfinite(nir)
    valid20 = np.isin(scl20, [4, 5, 6]) & np.isfinite(narrow) & np.isfinite(swir)
    def ratio(numerator, denominator, valid):
        result = np.full(numerator.shape, -9999, dtype=np.float32)
        np.divide(numerator, denominator, out=result,
                  where=valid & np.isfinite(denominator) & (np.abs(denominator) > 1e-8))
        return result
    return {'NDVI': ratio(nir-red, nir+red, valid10),
            'EVI2': ratio(2.5*(nir-red), nir+2.4*red+1, valid10),
            'NDMI': ratio(narrow-swir, narrow+swir, valid20)}


def fetch_catalogue(bbox, end):
    query = {'collections': 'sentinel-2-l2a', 'bbox': ','.join(map(str, bbox)),
             'datetime': f'{(end-timedelta(days=30)).isoformat()}/{end.isoformat()}', 'limit': 100}
    url = ENDPOINT + '?' + urlencode(query)
    features = []
    for _ in range(10):
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.netloc != 'stac.dataspace.copernicus.eu':
            raise ValueError('Unexpected catalogue pagination host')
        with urlopen(url, timeout=60) as response:
            page = json.load(response)
        features.extend(page['features'])
        links = [x for x in page.get('links', []) if x.get('rel') == 'next']
        if not links:
            return features, query
        if links[0].get('method', 'GET') != 'GET':
            raise ValueError('Unsupported pagination method')
        url = links[0]['href']
    raise ValueError('Catalogue pagination limit reached; selection stopped')


def crop(asset, bounds, resolution):
    href = asset['href']
    if not href.startswith('s3://eodata/Sentinel-2/MSI/L2A/') or '..' in href:
        raise ValueError('Unexpected S3 asset location')
    path = '/vsis3/' + href.removeprefix('s3://')
    ds = gdal.Warp('', path, format='MEM', dstSRS='EPSG:25830',
                   outputBounds=aligned_bounds(bounds, resolution), xRes=resolution, yRes=resolution,
                   resampleAlg='near', outputType=gdal.GDT_Float32,
                   srcNodata=asset.get('nodata', 0), dstNodata=-9999)
    if ds is None:
        raise ValueError('S3 crop failed')
    return ds


def reflectance(ds, asset):
    if 'raster:scale' not in asset or 'raster:offset' not in asset:
        raise ValueError('Missing reflectance scale/offset; no assumed conversion')
    dn = ds.ReadAsArray()
    return np.where(dn == -9999, np.nan,
                    dn*float(asset['raster:scale'])+float(asset['raster:offset']))


def write_raster(path, array, reference, name, item_id):
    ds = gdal.GetDriverByName('GTiff').Create(str(path), reference.RasterXSize,
        reference.RasterYSize, 1, gdal.GDT_Float32, options=['TILED=YES', 'COMPRESS=DEFLATE'])
    ds.SetGeoTransform(reference.GetGeoTransform())
    ds.SetProjection(reference.GetProjection())
    ds.SetMetadata({'SOURCE_ITEM': item_id, 'INDICATOR': name, 'SOURCE': 'Copernicus Sentinel-2 L2A'})
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(-9999)
    band.SetDescription(name)
    band.WriteArray(array)
    ds.FlushCache()
    ds = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalogue-only', action='store_true')
    parser.add_argument('--catalogue-file', type=Path, help='Offline catalogue fixture')
    parser.add_argument('--end', help='ISO UTC end time; default current UTC')
    parser.add_argument('--output', type=Path, default=ROOT/'sentinel-output')
    args = parser.parse_args()
    gdal.UseExceptions()
    aoi = json.loads((ROOT/'data/sentinel-aoi.json').read_text(encoding='utf-8'))
    end = datetime.fromisoformat(args.end.replace('Z', '+00:00')) if args.end else datetime.now(timezone.utc)
    if end.tzinfo is None:
        raise ValueError('--end requires timezone')
    if args.catalogue_file:
        features = json.loads(args.catalogue_file.read_text(encoding='utf-8-sig'))['features']
        query = {'offline_fixture': args.catalogue_file.name}
    else:
        features, query = fetch_catalogue(aoi['catalog_bbox']['bounds'], end)
    item = select_scene(features, aoi['catalog_bbox']['bounds'])
    if not re.fullmatch(r'[A-Za-z0-9_-]+', item['id']):
        raise ValueError('Invalid item identifier')
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {'status': 'selected_not_downloaded', 'query': query, 'source_item': item,
                'aoi': aoi['processing_aoi'], 'quality_policy': 'SCL 4,5,6; minimum 80% valid rectangle',
                'indices': {}, 'note': 'NDMI is not a direct soil-moisture measurement'}
    report = args.output/'manifest.json'
    report.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print('Selected:', item['id'])
    if args.catalogue_only:
        (args.output/'selection.json').write_text(json.dumps({'type': 'FeatureCollection', 'features': [item]}), encoding='utf-8')
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
                stream.write(f"item={item['id']}\n")
        return
    for source, target in [('CDSE_S3_ACCESS_KEY', 'AWS_ACCESS_KEY_ID'), ('CDSE_S3_SECRET_KEY', 'AWS_SECRET_ACCESS_KEY')]:
        value = os.environ.get(source)
        if not value:
            raise ValueError(f'Missing GitHub secret/environment variable {source}')
        gdal.SetConfigOption(target, value)
    for key, value in {'AWS_S3_ENDPOINT': 'eodata.dataspace.copernicus.eu', 'AWS_REGION': 'default',
                       'AWS_VIRTUAL_HOSTING': 'FALSE', 'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR',
                       'GDAL_HTTP_MAX_RETRY': '3', 'GDAL_HTTP_RETRY_DELAY': '30',
                       'GDAL_HTTP_TIMEOUT': '120'}.items():
        gdal.SetConfigOption(key, value)
    bounds = aoi['processing_aoi']['bounds']
    rasters = {key: crop(item['assets'][key], bounds, res) for key, res in BANDS.items()}
    # Reuse the downloaded classification instead of requesting S3 a second time.
    scl10 = gdal.Warp('', rasters['SCL_20m'], format='MEM',
        outputBounds=aligned_bounds(bounds, 10), xRes=10, yRes=10,
        resampleAlg='near', srcNodata=-9999, dstNodata=-9999).ReadAsArray()
    scl20 = rasters['SCL_20m'].ReadAsArray()
    values = [reflectance(rasters[k], item['assets'][k]) for k in list(BANDS)[:4]]
    outputs = indices(*values, scl10, scl20)
    for name, array in outputs.items():
        valid = array != -9999
        manifest['indices'][name] = {'valid_percent_rectangle': float(valid.mean()*100),
            'resolution_m': 20 if name == 'NDMI' else 10,
            'mean_rectangle': float(array[valid].mean()) if valid.any() else None}
    good = all(x['valid_percent_rectangle'] >= 80 for x in manifest['indices'].values())
    manifest['status'] = 'quality_passed' if good else 'rejected_local_quality'
    report.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    if not good:
        raise ValueError('Local quality below 80%; indices not released')
    for name, array in outputs.items():
        ref = rasters['B8A_20m' if name == 'NDMI' else 'B04_10m']
        path = args.output/f'{name}.tif'
        write_raster(path, array, ref, name, item['id'])
        manifest['indices'][name]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_raster(args.output/'SCL.tif', scl20, rasters['SCL_20m'], 'SCL', item['id'])
    report.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print('Completed: NDVI/EVI2 10 m; NDMI/SCL 20 m; EPSG:25830')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Avoid logging request headers, credentials or provider response bodies.
        print(f'Sentinel pipeline failed ({type(error).__name__}). Check inputs, CDSE access and manifest.', file=sys.stderr)
        sys.exit(1)
