"""Paired-pixel changes on original grids; reusable coverage for future water analysis."""
import hashlib
import json
import numpy as np
from parcel_grid import sample_parcel, valid_pixels, require_same_grid
from parcel_ndvi import INDICES, MIN_VALID_PERCENT


def compare_parcel(a, b, geometry, name):
    require_same_grid(a, b)
    resolution, value_range = INDICES[name]
    va, inside = sample_parcel(a, geometry, resolution)
    vb, other = sample_parcel(b, geometry, resolution)
    if not np.array_equal(inside, other):
        raise ValueError('Parcel mask mismatch')
    common = valid_pixels(a, va, inside, value_range) & valid_pixels(b, vb, inside, value_range)
    count, total = int(common.sum()), int(inside.sum())
    means = [None, None, None]
    if total and count / total * 100 >= MIN_VALID_PERCENT:
        means = [round(float(np.mean(x, dtype=np.float64)), 4)
                 for x in (va[common], vb[common], vb[common] - va[common])]
    return means + [count, total]


def build_comparison(before, after, master_path, web_hash):
    ma, ra = before
    mb, rb = after
    if ma['source_item']['properties']['datetime'] >= mb['source_item']['properties']['datetime']:
        raise ValueError('Comparison requires chronological distinct acquisitions')
    master_bytes = master_path.read_bytes()
    master = json.loads(master_bytes)
    if master['crs'] != 'EPSG:25830' or master['web_sha256'] != web_hash:
        raise ValueError('Comparison parcel provenance mismatch')
    for name in INDICES:
        require_same_grid(ra[name], rb[name])
    return {
        'version': 1, 'method': 'common_valid_pixel_centres', 'min_valid_percent': MIN_VALID_PERCENT,
        'a': {'id': ma['source_item']['id'], 'datetime': ma['source_item']['properties']['datetime']},
        'b': {'id': mb['source_item']['id'], 'datetime': mb['source_item']['properties']['datetime']},
        'parcel_web_sha256': web_hash, 'master_sha256': hashlib.sha256(master_bytes).hexdigest(),
        'columns': ['mean_a', 'mean_b', 'delta_b_minus_a', 'common_pixels', 'total_pixels'],
        'indices': {name: {'resolution_m': spec[0], 'pixel_area_m2': spec[0] ** 2,
                          'a_sha256': ma['indices'][name]['sha256'],
                          'b_sha256': mb['indices'][name]['sha256']}
                    for name, spec in INDICES.items()},
        'parcels': {f['refcat']: {name: compare_parcel(ra[name], rb[name], f['geometry'], name)
                                  for name in INDICES} for f in master['features']}}
