"""Reproduce published legacy NDVI directly from preserved original DN crops."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
import numpy as np
from osgeo import gdal
from parcel_grid import sample_parcel, require_same_grid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw', type=Path)
    parser.add_argument('published_catalogue', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--refs', nargs='+', required=True)
    args = parser.parse_args()
    gdal.UseExceptions()
    master = json.loads((Path(__file__).resolve().parents[1]/'data/parcel-master.json').read_text())
    rows = []
    for entry in json.loads(args.published_catalogue.read_text())['acquisitions']:
        folder = args.output/entry['id']; folder.mkdir(parents=True, exist_ok=True)
        path = folder/'NDVI.tif'
        relative = entry['indices']['NDVI']['download']
        if relative != f"sentinel/{entry['id']}/NDVI.tif" or '/' in entry['id'] or '..' in entry['id']:
            raise ValueError('Unexpected publication path')
        if not path.exists():
            with urlopen('https://julianladera-droid.github.io/castrejon-webgis/'+relative, timeout=60) as response:
                path.write_bytes(response.read())
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if checksum != entry['indices']['NDVI']['sha256']:
            raise ValueError('Published original has changed; do not substitute silently')
        ds = gdal.Open(str(path)); raw = args.raw/entry['id']
        item = json.loads((raw/'source_item.json').read_text())
        bands = []
        for name in ('B04_10m', 'B08_10m'):
            band = gdal.Open(str(raw/f'raw_{name}.tif')); require_same_grid(ds, band)
            asset = item['assets'][name]
            dn = band.ReadAsArray()
            bands.append(np.where(dn == -9999, np.nan, dn*asset['raster:scale']+asset['raster:offset']))
        red, nir = bands
        with np.errstate(divide='ignore', invalid='ignore'):
            expected = (nir-red)/(nir+red)
        old = ds.ReadAsArray(); valid = (old != -9999) & np.isfinite(old) & np.isfinite(expected)
        row = {'id': entry['id'], 'published_sha256': checksum,
            'max_abs_difference_from_original_dn_float32_formula': float(np.max(np.abs(old[valid]-expected[valid]))), 'parcels': {}}
        for ref in args.refs:
            geometry = next(f['geometry'] for f in master['features'] if f['refcat'] == ref)
            values, inside = sample_parcel(ds, geometry, 10)
            values = values[inside & (values != -9999) & np.isfinite(values)]
            row['parcels'][ref] = {'min': float(values.min()), 'max': float(values.max()),
                'out_of_range_count': int((np.abs(values) > 1).sum()), 'valid_raw_count': len(values)}
        rows.append(row)
    (args.output/'diagnostic.json').write_text(json.dumps(rows, indent=2)+'\n')


if __name__ == '__main__': main()
