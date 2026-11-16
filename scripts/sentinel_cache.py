"""Fingerprint local calculation dependencies and validate restored acquisitions."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import platform

ROOT = Path(__file__).resolve().parents[1]


def dependencies(root=ROOT):
    """Follow local imports so a new detector dependency cannot silently be omitted."""
    pending = ['sentinel_pipeline', 'sentinel_cache']
    found = set()
    while pending:
        name = pending.pop()
        path = root / 'scripts' / (name + '.py')
        if name in found or not path.is_file():
            continue
        found.add(name)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.ImportFrom) and node.module:
                pending.append(node.module.split('.')[0])
            elif isinstance(node, ast.Import):
                pending.extend(alias.name.split('.')[0] for alias in node.names)
    return sorted('scripts/' + name + '.py' for name in found) + ['data/sentinel-aoi.json']


def provenance(root=ROOT, runtime=None):
    if runtime is None:
        import numpy
        from osgeo import gdal
        runtime = {'python': platform.python_version(), 'numpy': numpy.__version__,
                   'gdal': gdal.VersionInfo('--version')}
    files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in dependencies(root)}
    payload = {'files': files, 'runtime': runtime}
    payload['fingerprint'] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


def validate_cache(folder, selection, expected):
    from build_sentinel_web import validate_product
    from sentinel_pipeline import aligned_bounds
    manifest, rasters = validate_product(folder)
    rasters.clear()
    item = json.loads(selection.read_text(encoding='utf-8'))['features'][0]
    if (manifest['source_item']['id'], manifest['source_item']['properties']['datetime']) != (
            item['id'], item['properties']['datetime']):
        raise ValueError('Cached product identity mismatch')
    aoi = json.loads((ROOT / 'data/sentinel-aoi.json').read_text())['processing_aoi']
    if manifest['aoi'] != {**aoi, 'bounds': aligned_bounds(aoi['bounds'], 20)}:
        raise ValueError('Cached AOI mismatch')
    if (manifest.get('source_audit') or {}).get('calculation') != expected:
        raise ValueError('Cached calculation/runtime mismatch')
    for name, band in manifest['raw_bands'].items():
        asset = item['assets'][name]
        if any(band[key] != asset.get(source, default) for key, source, default in (
                ('asset_href', 'href', None), ('source_checksum', 'file:checksum', None),
                ('scale', 'raster:scale', None), ('offset', 'raster:offset', None), ('nodata', 'nodata', 0))):
            raise ValueError('Cached source calibration mismatch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', type=Path)
    parser.add_argument('--selection', type=Path)
    args = parser.parse_args()
    expected = provenance()
    if args.check:
        try:
            validate_cache(args.check, args.selection, expected)
            line = 'usable=true'
        except (ValueError, KeyError, OSError, RuntimeError, TypeError, AttributeError, IndexError):
            # Cache is only an accelerator. A bad/missing entry triggers calculation.
            line = 'usable=false'
    else:
        line = 'fingerprint=' + expected['fingerprint']
    print(line)
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write(line + '\n')


if __name__ == '__main__':
    main()
