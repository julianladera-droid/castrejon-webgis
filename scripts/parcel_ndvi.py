"""Build parcel index summaries on original metric grids, never in browser."""
import hashlib
import json
from pathlib import Path
import numpy as np
from parcel_grid import sample_parcel, valid_pixels

MIN_VALID_PERCENT = 80
INDICES = {'NDVI': (10, [-1, 1]), 'EVI2': (10, None), 'NDMI': (20, [-1, 1])}


def summarize(ds, geometry, index='NDVI'):
    """Pixel-centre arithmetic mean; holes excluded, outside raster counted invalid."""
    resolution, valid_range = INDICES[index]
    values, inside = sample_parcel(ds, geometry, resolution)
    valid = valid_pixels(ds, values, inside, valid_range)
    total, valid_count = int(inside.sum()), int(valid.sum())
    mean = None
    if total and valid_count/total*100 >= MIN_VALID_PERCENT:
        mean = round(float(np.mean(values[valid], dtype=np.float64)), 4)
    percent = round(valid_count/total*100, 2) if total else 0
    return {'mean': mean, 'valid_pixels': valid_count, 'total_pixels': total,
            'valid_percent': percent,
            'status': 'ok' if mean is not None else 'no_pixels' if not total else 'insufficient'}


def build_parcel_indices(rasters, manifest, master_path, web_folder):
    master_bytes = master_path.read_bytes()
    master = json.loads(master_bytes)
    meta = json.loads((web_folder/'metadata.json').read_text(encoding='utf-8'))
    web_hash = hashlib.sha256((web_folder/'parcelas.geojson').read_bytes()).hexdigest()
    if (master['version'] != 1 or master['crs'] != 'EPSG:25830' or
            master['web_sha256'] != web_hash or meta['web_sha256'] != web_hash or
            master['source_sha256'] != meta['source_sha256']):
        raise ValueError('Metric parcel provenance mismatch')
    refs = {f['id'] for f in json.loads((web_folder/'parcelas.geojson').read_text(encoding='utf-8'))['features']}
    features = master['features']
    if len(features) != 919 or len(refs) != 919 or {f['refcat'] for f in features} != refs:
        raise ValueError('Metric parcel identity mismatch')
    def compact(geometry):
        rows = {}
        for name in INDICES:
            row = summarize(rasters[name], geometry, name)
            rows[name] = [row['mean'], row['valid_pixels'], row['total_pixels']]
        return rows
    return {'version': 2, 'acquisition_id': manifest['source_item']['id'],
            'datetime': manifest['source_item']['properties']['datetime'],
            'indices': {name: {'sha256': manifest['indices'][name]['sha256'],
                              'resolution_m': spec[0]} for name, spec in INDICES.items()},
            'parcel_web_sha256': web_hash, 'master_sha256': hashlib.sha256(master_bytes).hexdigest(),
            'method': 'pixel_center_mean', 'min_valid_percent': MIN_VALID_PERCENT,
            'columns': ['mean', 'valid_pixels', 'total_pixels'],
            'parcels': {f['refcat']: compact(f['geometry']) for f in features}}
