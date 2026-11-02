"""Reprocess preserved DN and compare SCL, NDWI and the versioned optical rule.

Outputs reproducible JSON; parcel presence is not pixel ground truth. No accuracy
or calibrated probability is computed. Requires GDAL/NumPy, no browser GIS.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from osgeo import gdal
from sentinel_pipeline import process_rasters, reflectance, write_raster
from sentinel_contract import RAW_BANDS
from spectral_quality import normalized_difference, interpretable
from parcel_grid import mean_2x2, repeat_2x2, sample_parcel
from parcel_water import regions, parcel_areas
from water_sharpening import guided_b11


def statistics(ds, geometry):
    values, inside = sample_parcel(ds, geometry, ds.GetGeoTransform()[1])
    valid = inside & np.isfinite(values) & (values != -9999)
    v = values[valid]
    return {'centres': int(inside.sum()), 'valid_centres': int(valid.sum()),
        'min': float(v.min()) if v.size else None, 'max': float(v.max()) if v.size else None,
        'median': float(np.median(v)) if v.size else None,
        'mean': float(v.mean()) if v.size else None}


def study(raw_folder, output, master, refs):
    item = json.loads((raw_folder/'source_item.json').read_text())
    source_audit = json.loads((raw_folder/'mirror.json').read_text())
    original = {key: gdal.Open(str(raw_folder/f'raw_{key}.tif')) for key in RAW_BANDS}
    coarse = original['B11_20m']; gt = coarse.GetGeoTransform()
    bounds = [gt[0], gt[3]-coarse.RasterYSize*20, gt[0]+coarse.RasterXSize*20, gt[3]]
    rasters = {}
    for key, resolution in RAW_BANDS.items():
        rasters[key] = gdal.Warp('', original[key], format='MEM', outputBounds=bounds,
            xRes=resolution, yRes=resolution, srcNodata=-9999, dstNodata=-9999, resampleAlg='near')
    # Earlier 10m AOI crops may lack a marginal 10m strip outside the requested AOI.
    # Padding that strip with nodata preserves source DN and reports missing coverage.
    source_audit['alignment'] = 'common 20m extent; any unavailable marginal cells padded nodata'
    destination = output/item['id']
    manifest = process_rasters(rasters, item, {'crs': 'EPSG:25830', 'bounds': bounds}, destination,
        {'study': 'preserved_original_jp2_dn', 'original_product': item['id']}, source_audit, legacy_water=True)
    fine = rasters['B03_10m']
    ndwi = gdal.Open(str(destination/'NDWI.tif')).ReadAsArray()
    ndvi = gdal.Open(str(destination/'NDVI.tif')).ReadAsArray()
    scl = rasters['SCL_20m'].ReadAsArray()
    water = gdal.Open(str(destination/'WATER.tif'))
    mndwi20 = gdal.Open(str(destination/'MNDWI.tif')).ReadAsArray()
    alternatives = {'combined': regions(water),
        'scl': regions(coarse, np.where(np.isin(scl, [4, 5, 6]), (scl == 6).astype(int), 3)),
        'mndwi20': regions(coarse, np.where(interpretable(mndwi20), (mndwi20 > 0).astype(int), 3)),
        'ndwi': regions(fine, np.where(interpretable(ndwi), (ndwi > 0).astype(int), 3))}
    green = reflectance(fine, item['assets']['B03_10m'])
    swir = reflectance(rasters['B11_20m'], item['assets']['B11_20m'])
    nearest = normalized_difference(green, repeat_2x2(swir), np.isin(repeat_2x2(scl), [4, 5, 6]))
    alternatives['nearest_b11_mndwi'] = regions(fine, np.where(interpretable(nearest), (nearest > 0).astype(int), 3))
    experiments = {}
    for name, auxiliary in [('guided_ndwi', None), ('guided_ndwi_ndvi', ndvi)]:
        try:
            estimate, metadata = guided_b11(swir, ndwi, auxiliary, np.isin(scl, [4, 5, 6]))
        except ValueError as error:
            if 'Insufficient complete blocks' not in str(error):
                raise
            experiments[name] = {'status': 'not_evaluable', 'reason': str(error)}
            continue
        value = normalized_difference(green, estimate, np.isin(repeat_2x2(scl), [4, 5, 6]))
        write_raster(destination/f'{name}_B11.tif', np.where(np.isfinite(estimate), estimate, -9999), fine, name+'_B11', item['id'])
        write_raster(destination/f'{name}_MNDWI.tif', value, fine, name+'_MNDWI', item['id'])
        alternatives[name] = regions(fine, np.where(interpretable(value), (value > 0).astype(int), 3))
        experiments[name] = metadata
    report = {'product': item['id'], 'datetime': item['properties']['datetime'],
        'manifest_sha256': hashlib.sha256((destination/'manifest.json').read_bytes()).hexdigest(),
        'status': manifest['status'], 'experiments': experiments, 'parcels': {}}
    for feature in master['features']:
        if refs and feature['refcat'] not in refs:
            continue
        geometry = feature['geometry']; measurements = {}
        for name, vector in alternatives.items():
            areas, total, missing, _ = parcel_areas(vector.GetLayer(), geometry)
            measurements[name] = {'water_m2': round(areas[1], 3), 'ambiguous_m2': round(areas[2], 3),
                'unknown_m2': round(areas[3]+missing, 3), 'parcel_m2': round(total, 3),
                'classified_percent': round((areas[0]+areas[1])/total*100, 3),
                'water_percent': round(areas[1]/total*100, 3)}
        measurements['indices'] = {name: statistics(gdal.Open(str(destination/f'{name}.tif')), geometry)
                                  for name in ('NDVI', 'NDWI', 'MNDWI', 'NDMI')}
        report['parcels'][feature['refcat']] = measurements
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--refs', nargs='*')
    parser.add_argument('--controls', type=Path, help='Optional independent study polygons, EPSG:25830')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    gdal.UseExceptions()
    root = Path(__file__).resolve().parents[1]
    master = json.loads((root/'data/parcel-master.json').read_text())
    if args.controls:
        master = json.loads(args.controls.read_text())
        if master.get('crs') != 'EPSG:25830':
            raise ValueError('Study controls must be metric')
    reports = []
    for path in sorted(args.raw.glob('*/source_item.json')):
        reports.append(study(path.parent, args.output, master, args.refs))
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({'master_sha256': hashlib.sha256((args.controls or root/'data/parcel-master.json').read_bytes()).hexdigest(),
            'observations': reports}, indent=2, allow_nan=False)+'\n')
        print('Studied', reports[-1]['product'], flush=True)


if __name__ == '__main__':
    main()
