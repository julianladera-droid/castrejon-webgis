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
from parcel_grid import require_same_grid, require_nested_grid, mean_2x2, repeat_2x2
from spectral_quality import normalized_difference, quality_counts, MIN_SUM
from sentinel_contract import PRODUCT_VERSION, RADIOMETRY, WATER_METHOD, INDEX_RESOLUTIONS, RAW_BANDS
from water_detection import detect, PARAMETERS, QUALITY_BITS

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'https://stac.dataspace.copernicus.eu/v1/search'
BANDS = RAW_BANDS


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
    evi = np.full(red.shape, -9999, dtype=np.float32)
    np.divide(2.5*(nir-red), nir+2.4*red+1, out=evi,
              where=valid10 & (red >= 0) & (nir >= 0) & (red+nir > MIN_SUM))
    return {'NDVI': normalized_difference(nir, red, valid10), 'EVI2': evi,
            'NDMI': normalized_difference(narrow, swir, valid20)}


def fetch_catalogue(bbox, end, start=None):
    query = {'collections': 'sentinel-2-l2a', 'bbox': ','.join(map(str, bbox)),
             'datetime': f'{(start or end-timedelta(days=30)).isoformat()}/{end.isoformat()}', 'limit': 100}
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
    if not re.match(r'^s3://eodata/Sentinel-2/MSI/L2A(?:_N0500)?/', href) or '..' in href:
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
    # GDAL ReadAsArray returns DN, it does not apply band scale/offset.
    dn = ds.ReadAsArray().astype(np.float64)
    valid = np.isfinite(dn) & (dn != -9999) & (dn != asset.get('nodata', 0))
    nodata = ds.GetRasterBand(1).GetNoDataValue()
    if nodata is not None:
        valid &= dn != nodata
    scale, offset = float(asset['raster:scale']), float(asset['raster:offset'])
    if not np.isfinite(scale) or scale <= 0 or not np.isfinite(offset):
        raise ValueError('Invalid asset scale/offset')
    return np.where(valid, dn*scale+offset, np.nan)


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


def process_rasters(rasters, item, aoi, output, query, source_audit=None):
    """Same calculation for fresh downloads and preserved, identified DN crops."""
    output.mkdir(parents=True, exist_ok=True)
    fine, coarse = rasters['B03_10m'], rasters['B11_20m']
    for name in ('B04_10m', 'B08_10m'):
        require_same_grid(fine, rasters[name])
    for name in ('B8A_20m', 'SCL_20m'):
        require_same_grid(coarse, rasters[name])
    require_nested_grid(fine, coarse)
    scl20 = rasters['SCL_20m'].ReadAsArray()
    if not np.all(np.isin(scl20, [-9999, *range(12)])):
        raise ValueError('Invalid SCL classes')
    scl10 = repeat_2x2(scl20)
    rho = {name: reflectance(ds, item['assets'][name]) for name, ds in rasters.items()
           if not name.startswith('SCL')}
    green, red, nir, narrow, swir = [rho[n] for n in ('B03_10m', 'B04_10m', 'B08_10m', 'B8A_20m', 'B11_20m')]
    green20 = mean_2x2(green)
    outputs = indices(red, nir, narrow, swir, scl10, scl20)
    outputs['NDWI'] = normalized_difference(green, nir, np.isin(scl10, [4, 5, 6]))
    outputs['MNDWI'] = normalized_difference(green20, swir, np.isin(scl20, [4, 5, 6]))
    water, quality = detect(green, nir, repeat_2x2(swir), outputs['NDWI'],
                            repeat_2x2(outputs['MNDWI']), outputs['NDVI'], scl10)
    manifest = {'version': PRODUCT_VERSION, 'radiometry': RADIOMETRY,
        'status': 'processing', 'query': query, 'source_item': item, 'aoi': aoi,
        'quality_policy': 'SCL 4,5,6; >=80% valid rectangle per index; parcel coverage independent',
        'indices': {}, 'raw_bands': {}, 'diagnostics': {},
        'aggregation': 'B03 arithmetic area mean of four exactly nested 10m cells; all four required',
        'water': {'method': WATER_METHOD, 'parameters': PARAMETERS, 'quality_bits': QUALITY_BITS,
                  'classes': {'0': 'no_detection', '1': 'water', '2': 'ambiguous', '3': 'not_evaluable'}},
        'source_audit': source_audit,
        'note': 'Exploratory surface water; neither depth nor volume; NDMI is not soil moisture'}
    for name, ds in rasters.items():
        path = output / f'raw_{name}.tif'
        # Preserve DN without overwriting a source dataset opened from this same path.
        if Path(ds.GetDescription()).resolve() != path.resolve():
            write_raster(path, ds.ReadAsArray(), ds, 'raw_' + name, item['id'])
        asset = item['assets'][name]
        manifest['raw_bands'][name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'asset_href': asset['href'], 'source_checksum': asset.get('file:checksum'),
            'scale': asset.get('raster:scale'), 'offset': asset.get('raster:offset'),
            'nodata': asset.get('nodata', 0), 'resolution_m': BANDS[name]}
        if name in rho:
            valid = np.isfinite(rho[name])
            manifest['raw_bands'][name]['negative_count'] = int((rho[name][valid] < 0).sum())
    pairs = {'NDVI': (nir, red, scl10), 'NDMI': (narrow, swir, scl20),
             'NDWI': (green, nir, scl10), 'MNDWI': (green20, swir, scl20)}
    for name, (a, b, scl) in pairs.items():
        manifest['diagnostics'][name] = quality_counts(a, b, np.isin(scl, [4, 5, 6]))
    for name, array in outputs.items():
        valid = np.isfinite(array) & (array != -9999)
        path = output / f'{name}.tif'
        write_raster(path, array, coarse if INDEX_RESOLUTIONS[name] == 20 else fine, name, item['id'])
        manifest['indices'][name] = {'valid_percent_rectangle': float(valid.mean()*100),
            'resolution_m': INDEX_RESOLUTIONS[name],
            'mean_rectangle': float(array[valid].mean()) if valid.any() else None,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    for name, array, ref in [('SCL', scl20, coarse), ('WATER', water, fine), ('WATER_QUALITY', quality, fine)]:
        path = output / f'{name}.tif'
        write_raster(path, array, ref, name, item['id'])
        manifest['water'][name.lower() + '_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest['water']['classified_percent_rectangle'] = float(np.isin(water, [0, 1]).mean()*100)
    good = all(x['valid_percent_rectangle'] >= 80 for x in manifest['indices'].values())
    manifest['status'] = 'quality_passed' if good else 'rejected_local_quality'
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalogue-only', action='store_true')
    parser.add_argument('--catalogue-file', type=Path, help='Offline catalogue fixture')
    parser.add_argument('--end', help='ISO UTC end time; default current UTC')
    parser.add_argument('--date', help='Exact observation day YYYY-MM-DD, never silently substitute another day')
    parser.add_argument('--item-id', help='Exact product identifier within the requested catalogue')
    parser.add_argument('--raw-input', type=Path, help='Preserved DN crops with SOURCE_ITEM metadata')
    parser.add_argument('--output', type=Path, default=ROOT/'sentinel-output')
    args = parser.parse_args()
    gdal.UseExceptions()
    aoi = json.loads((ROOT/'data/sentinel-aoi.json').read_text(encoding='utf-8'))
    end = datetime.fromisoformat(args.end.replace('Z', '+00:00')) if args.end else datetime.now(timezone.utc)
    if end.tzinfo is None:
        raise ValueError('--end requires timezone')
    start = None
    if args.date:
        start = datetime.strptime(args.date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end = start + timedelta(days=1) - timedelta(microseconds=1)
    if args.catalogue_file:
        features = json.loads(args.catalogue_file.read_text(encoding='utf-8-sig'))['features']
        query = {'offline_fixture': args.catalogue_file.name}
    else:
        features, query = fetch_catalogue(aoi['catalog_bbox']['bounds'], end, start)
    if args.date:
        features = [f for f in features if f['properties']['datetime'][:10] == args.date]
    if args.item_id:
        features = [f for f in features if f['id'] == args.item_id]
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
    for source, target in ([] if args.raw_input else [('CDSE_S3_ACCESS_KEY', 'AWS_ACCESS_KEY_ID'), ('CDSE_S3_SECRET_KEY', 'AWS_SECRET_ACCESS_KEY')]):
        value = os.environ.get(source)
        if not value:
            raise ValueError(f'Missing GitHub secret/environment variable {source}')
        gdal.SetConfigOption(target, value)
    for key, value in {'AWS_S3_ENDPOINT': 'eodata.dataspace.copernicus.eu', 'AWS_REGION': 'default',
                       'AWS_VIRTUAL_HOSTING': 'FALSE', 'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR',
                       'GDAL_HTTP_MAX_RETRY': '3', 'GDAL_HTTP_RETRY_DELAY': '30',
                       'GDAL_HTTP_TIMEOUT': '120'}.items():
        gdal.SetConfigOption(key, value)
    # A common 20m-aligned extent gives exact 2x2 nesting even at AOI boundaries.
    bounds = aligned_bounds(aoi['processing_aoi']['bounds'], 20)
    if args.raw_input:
        rasters = {key: gdal.Open(str(args.raw_input/f'raw_{key}.tif')) for key in BANDS}
        if any(not ds or ds.GetMetadataItem('SOURCE_ITEM') != item['id'] for ds in rasters.values()):
            raise ValueError('Preserved DN identity mismatch')
    else:
        rasters = {key: crop(item['assets'][key], bounds, res) for key, res in BANDS.items()}
    manifest = process_rasters(rasters, item, {**aoi['processing_aoi'], 'bounds': bounds}, args.output, query)
    if manifest['status'] != 'quality_passed':
        raise ValueError('Local quality below 80%; preserved for diagnosis, not publication')
    print('Completed v2: NDVI/EVI2/NDWI/water 10 m; NDMI/MNDWI/SCL 20 m; EPSG:25830')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Avoid logging request headers, credentials or provider response bodies.
        print(f'Sentinel pipeline failed ({type(error).__name__}). Check inputs, CDSE access and manifest.', file=sys.stderr)
        sys.exit(1)
