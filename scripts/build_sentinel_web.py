"""Validate an Actions product and prepare same-origin static Sentinel layers."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from datetime import datetime, timezone

import numpy as np
from osgeo import gdal
from parcel_ndvi import build_parcel_indices
from parcel_comparison import build_comparison
from parcel_grid import require_same_grid
from parcel_water import build_water
from sentinel_contract import compatible, INDEX_RESOLUTIONS, RAW_BANDS
from water_detection import PARAMETERS, QUALITY_BITS

PALETTES = {
    'NDVI': {'label': 'NDVI · vigor vegetal', 'range': [-1, 1],
             'colors': ['#314b91', '#d8c496', '#ffffbf', '#73b554', '#006837']},
    'EVI2': {'label': 'EVI2 · vegetación', 'range': [0, 1],
             'colors': ['#fff7bc', '#fec44f', '#78c679', '#238443', '#004529']},
    'NDMI': {'label': 'NDMI · humedad de la vegetación', 'range': [-1, 1],
             'colors': ['#8c510a', '#dfc27d', '#f5f5f5', '#80cdc1', '#01665e']},
    'NDWI': {'label': 'NDWI · señal de agua superficial', 'range': [-1, 1],
             'colors': ['#8c510a', '#dfc27d', '#f5f5f5', '#80cdc1', '#01665e']},
    'MNDWI': {'label': 'MNDWI · apoyo de 20 m', 'range': [-1, 1],
              'colors': ['#8c510a', '#dfc27d', '#f5f5f5', '#80cdc1', '#01665e']},
}


def colorize(values, valid, spec):
    """Fixed scales; invalid values stay fully transparent, never zero-filled."""
    colors = np.array([[int(c[i:i+2], 16) for i in (1, 3, 5)] for c in spec['colors']])
    lo, hi = spec['range']
    valid = valid & np.isfinite(values)
    if spec['range'] == [-1, 1]:
        valid &= (values >= -1) & (values <= 1)
    position = np.clip((np.where(valid, values, lo)-lo)/(hi-lo), 0, 1)
    channels = [np.interp(position, np.linspace(0, 1, len(colors)), colors[:, i])
                for i in range(3)]
    return np.array(channels + [np.where(valid, 255, 0)], dtype=np.uint8)


def validate_product(folder):
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status') != 'quality_passed':
        raise ValueError('Product has not passed quality checks')
    if not compatible(manifest):
        raise ValueError('Incompatible product schema/radiometry/water method; reprocess original bands')
    if manifest['water'].get('parameters') != PARAMETERS or manifest['water'].get('quality_bits') != QUALITY_BITS:
        raise ValueError('Incompatible detection parameters')
    item = manifest['source_item']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,150}', item['id']):
        raise ValueError('Invalid product identifier')
    date = datetime.fromisoformat(item['properties']['datetime'].replace('Z', '+00:00'))
    if date.tzinfo is None or date > datetime.now(timezone.utc):
        raise ValueError('Invalid acquisition date')
    rasters = {}
    bounds = manifest['aoi']['bounds']
    if manifest['aoi']['crs'] != 'EPSG:25830':
        raise ValueError('Unexpected AOI CRS')
    for name in PALETTES:
        path = folder/f'{name}.tif'
        info = manifest['indices'][name]
        if hashlib.sha256(path.read_bytes()).hexdigest() != info['sha256']:
            raise ValueError('Product checksum mismatch')
        ds = gdal.Open(str(path))
        res = INDEX_RESOLUTIONS[name]
        expected = [np.floor(bounds[0]/res)*res, res, 0,
                    np.ceil(bounds[3]/res)*res, 0, -res]
        if (ds.RasterCount != 1 or ds.GetSpatialRef().GetAuthorityCode(None) != '25830'
                or not np.allclose(ds.GetGeoTransform(), expected)
                or ds.RasterXSize != int(np.ceil(bounds[2]/res)-np.floor(bounds[0]/res))
                or ds.RasterYSize != int(np.ceil(bounds[3]/res)-np.floor(bounds[1]/res))
                or ds.GetRasterBand(1).GetNoDataValue() != -9999):
            raise ValueError('Unexpected technical raster grid')
        array = ds.ReadAsArray()
        valid = np.isfinite(array) & (array != -9999)
        if name != 'EVI2' and np.any(valid & ((array < -1) | (array > 1))):
            raise ValueError('Uninterpretable normalized ratio')
        if ds.GetMetadataItem('SOURCE_ITEM') != item['id']:
            raise ValueError('Raster acquisition identity mismatch')
        percent = float(valid.mean()*100)
        if percent < 80 or abs(percent-info['valid_percent_rectangle']) > .001:
            raise ValueError('Product quality mismatch')
        rasters[name] = ds
    from parcel_grid import require_nested_grid
    require_same_grid(rasters['NDVI'], rasters['NDWI'])
    require_same_grid(rasters['NDMI'], rasters['MNDWI'])
    require_nested_grid(rasters['NDWI'], rasters['MNDWI'])
    for name, classes, ref in [('SCL', [-9999, *range(12)], 'MNDWI'),
                                ('WATER', range(4), 'NDWI'), ('WATER_QUALITY', range(64), 'NDWI')]:
        path = folder/f'{name}.tif'
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['water'][name.lower()+'_sha256']:
            raise ValueError('Water checksum mismatch')
        ds = gdal.Open(str(path))
        require_same_grid(ds, rasters[ref])
        if ds.GetMetadataItem('SOURCE_ITEM') != item['id'] or not np.all(np.isin(ds.ReadAsArray(), classes)):
            raise ValueError('Invalid water classification or provenance')
    for name in RAW_BANDS:
        path = folder/f'raw_{name}.tif'
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['raw_bands'][name]['sha256']:
            raise ValueError('Original DN checksum mismatch')
    return manifest, rasters


def build(folder, output, master_path=None, web_folder=None):
    gdal.UseExceptions()
    manifest, rasters = validate_product(folder)
    item = manifest['source_item']
    acquisition = {'id': item['id'], 'datetime': item['properties']['datetime'],
                   'indices': {}, 'source': 'Copernicus Sentinel-2 L2A',
                   'quality_scope': 'rectángulo envolvente', 'kind': 'ESTIMADO'}
    acquisition['water_raster_sha256'] = manifest['water']['water_sha256']
    destination = output/item['id']
    destination.mkdir(parents=True, exist_ok=True)
    if (folder/'SCL.tif').exists():
        scl = gdal.Open(str(folder/'SCL.tif'))
        require_same_grid(rasters['NDMI'], scl)
        classes = scl.ReadAsArray()
        if not np.all(np.isin(classes, [-9999, *range(12)])):
            raise ValueError('Invalid scene classification')
        shutil.copyfile(folder/'SCL.tif', destination/'SCL.tif')
        acquisition['quality_mask'] = {'path': f"sentinel/{item['id']}/SCL.tif", 'resolution_m': 20,
            'sha256': hashlib.sha256((folder/'SCL.tif').read_bytes()).hexdigest(),
            'kind': 'SCL classification, not a validated waterlogging map'}
    for name, ds in rasters.items():
        warped = gdal.Warp('', ds, format='MEM', dstSRS='EPSG:3857',
                           resampleAlg='near', srcNodata=-9999, dstNodata=-9999)
        values = warped.ReadAsArray()
        rgba = colorize(values, np.isfinite(values) & (values != -9999), PALETTES[name])
        mem = gdal.GetDriverByName('MEM').Create('', warped.RasterXSize, warped.RasterYSize, 4, gdal.GDT_Byte)
        for i in range(4):
            mem.GetRasterBand(i+1).WriteArray(rgba[i])
            mem.GetRasterBand(i+1).SetColorInterpretation([gdal.GCI_RedBand, gdal.GCI_GreenBand,
                gdal.GCI_BlueBand, gdal.GCI_AlphaBand][i])
        gdal.GetDriverByName('PNG').CreateCopy(str(destination/f'{name}.png'), mem)
        shutil.copyfile(folder/f'{name}.tif', destination/f'{name}.tif')
        x, dx, _, y, _, dy = warped.GetGeoTransform()
        acquisition['indices'][name] = {
            **PALETTES[name], **manifest['indices'][name], 'projection': 'EPSG:3857',
            'extent': [x, y+dy*warped.RasterYSize, x+dx*warped.RasterXSize, y],
            'image': f"sentinel/{item['id']}/{name}.png",
            'download': f"sentinel/{item['id']}/{name}.tif"}
    if master_path is not None:
        stats = build_parcel_indices(rasters, manifest, master_path, web_folder)
        payload = (json.dumps(stats, separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8')
        (destination/'parcel-indices.json').write_bytes(payload)
        acquisition['parcel_indices'] = {
            'path': f"sentinel/{item['id']}/parcel-indices.json",
            'sha256': hashlib.sha256(payload).hexdigest(),
            'parcel_web_sha256': stats['parcel_web_sha256']}
        acquisition['water'] = build_water(folder, acquisition, master_path, destination)
    # Public provenance is deliberately minimal: no full provider catalogue or credentials.
    catalog = {'version': 2, 'acquisitions': [acquisition], 'comparisons': []}
    (output/'catalog.json').write_text(json.dumps(catalog, indent=2)+'\n', encoding='utf-8')
    print(f"Prepared {item['id']}: five overlays, current water and GeoTIFF downloads")
    return catalog


def build_collection(folders, output, master_path, web_folder):
    products = [validate_product(folder) for folder in folders]
    unique = {}
    for folder, product in zip(folders, products):
        item = product[0]['source_item']
        day = item['properties']['datetime'][:10]
        old = unique.get(day)
        old_item = old[1][0]['source_item'] if old else None
        if old_item is None or (item['properties']['datetime'], item['id']) > (old_item['properties']['datetime'], old_item['id']):
            unique[day] = (folder, product)
    if not unique:
        raise ValueError('At least one compatible acquisition required')
    selected = [unique[day] for day in sorted(unique)]
    entries = []
    for folder, _ in selected:
        if not (folder/'SCL.tif').exists():
            raise ValueError('Preserve original SCL for subsequent analyses')
        entries.extend(build(folder, output, master_path, web_folder)['acquisitions'])
    web_hash = entries[0]['parcel_indices']['parcel_web_sha256']
    catalog = {'version': 2, 'acquisitions': entries[::-1], 'comparisons': []}
    for i in range(1, len(entries)):
        a, b = entries[i-1], entries[i]
        b['water'] = build_water(selected[i][0], b, master_path, output/b['id'], selected[i-1][0], a)
        try:
            for name in ('NDVI', 'EVI2', 'NDMI'):
                require_same_grid(selected[i-1][1][1][name], selected[i][1][1][name])
        except ValueError:
            continue
        table = build_comparison(selected[i-1][1], selected[i][1], master_path, web_hash)
        pair_id = 'comparison-' + hashlib.sha256((a['id']+'|'+b['id']).encode()).hexdigest()[:24]
        destination = output/pair_id
        destination.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(table, separators=(',', ':'), allow_nan=False)+'\n').encode()
        (destination/'parcel-comparison.json').write_bytes(payload)
        catalog['comparisons'].append({'id': pair_id, 'a': a['id'], 'b': b['id'],
            'path': f'sentinel/{pair_id}/parcel-comparison.json',
            'sha256': hashlib.sha256(payload).hexdigest(), 'parcel_web_sha256': web_hash})
    (output/'catalog.json').write_text(json.dumps(catalog, indent=2)+'\n', encoding='utf-8')
    print(f'Published {len(entries)} observations and {len(catalog["comparisons"])} comparisons')
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--collection', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.collection:
        build_collection(sorted(p.parent for p in args.input.glob('*/manifest.json')), args.output,
                         root/'data/parcel-master.json', root/'data/parcels')
    else:
        build(args.input, args.output, root/'data/parcel-master.json', root/'data/parcels')
