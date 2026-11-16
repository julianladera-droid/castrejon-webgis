"""Bounded AOI recovery packages travel atomically with the published Pages site."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

from sentinel_contract import PRODUCT_FILES, RAW_BANDS
from sentinel_products import MAX_ARCHIVE_BYTES, open_product, product_record
from sentinel_retention import policy, select

BASE_URL = 'https://julianladera-droid.github.io/castrejon-webgis/sentinel/'
SHA = r'[0-9a-f]{64}'


def public_get(path, limit=1_000_000):
    # The index cannot redirect us to arbitrary hosts or paths, or request credentials.
    if path not in ('recovery.json', 'publication.json', 'catalog.json') and not re.fullmatch(
            rf'recovery/{SHA}\.zip', path):
        raise ValueError('Invalid recovery path')
    request = Request(BASE_URL + path + '?check=' + str(time.time_ns()),
                      headers={'Cache-Control': 'no-cache', 'User-Agent': 'castrejon-recovery'})
    with urlopen(request, timeout=60) as response:
        if response.geturl().split('?')[0] != BASE_URL + path:
            raise ValueError('Unexpected recovery redirect')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Recovery response exceeds byte budget')
    return data


def read_snapshot():
    try:
        index = json.loads(public_get('recovery.json'))
    except HTTPError as error:
        if error.code != 404:
            raise
        # Bootstrap: an existing receipt is a continuity requirement, not an empty site.
        try:
            state = json.loads(public_get('publication.json'))
        except HTTPError as missing:
            if missing.code != 404:
                raise
            return []
        if state.get('version') != 1 or not state.get('products'):
            raise ValueError('Invalid bootstrap publication receipt')
        return [{'product': p, 'product_version': 0, 'unavailable': True} for p in state['products']]
    entries = index.get('entries')
    if index.get('version') != 1 or not isinstance(entries, list) or not 1 <= len(entries) <= 8:
        raise ValueError('Invalid recovery index')
    for name in ('catalog', 'publication'):
        payload = public_get(name + '.json')
        if hashlib.sha256(payload).hexdigest() != index.get(name + '_sha256'):
            raise ValueError('Recovery/catalog/receipt checksum mismatch')
        if name == 'publication':
            state = json.loads(payload)
        else:
            catalog = json.loads(payload)
    records = [e['product'] for e in entries]
    if state != {'version': 1, 'products': records} or [(r['id'], r['datetime']) for r in records] != [
            (a['id'], a['datetime']) for a in catalog['acquisitions']]:
        raise ValueError('Recovery/catalog/receipt membership mismatch')
    if select(entries, 8) != entries or len({e['product']['datetime'][:10] for e in entries}) != len(entries):
        raise ValueError('Duplicate or unordered recovery entries')
    for entry in entries:
        if (entry['product_version'] not in (2, 3) or not re.fullmatch(SHA, entry['sha256'])
                or entry['path'] != 'recovery/' + entry['sha256'] + '.zip'
                or type(entry['size_bytes']) is not int or not 0 < entry['size_bytes'] <= MAX_ARCHIVE_BYTES):
            raise ValueError('Invalid recovery package metadata')
        # Ignore any external attempt to add local paths to the index.
        entry.pop('local_path', None)
        entry.pop('unavailable', None)
    return entries


def restore(entry, destination):
    payload = public_get(entry['path'], entry['size_bytes'])
    if len(payload) != entry['size_bytes']:
        raise ValueError('Recovery package size mismatch')
    with open_product(payload, 'sha256:' + entry['sha256']) as archive:
        if (product_record(archive.read) != entry['product']
                or json.loads(archive.read('manifest.json'))['version'] != entry['product_version']):
            raise ValueError('Recovery product fingerprint mismatch')
        destination.mkdir(parents=True)
        for name in PRODUCT_FILES:
            (destination / name).write_bytes(archive.read(name))


def public_manifest(manifest):
    """Keep calibration and DN provenance; exclude provider catalogue and private audit."""
    result = copy.deepcopy(manifest)
    result.pop('query', None)
    result.pop('source_audit', None)
    allowed = {'version', 'radiometry', 'status', 'source_item', 'aoi', 'quality_policy',
               'indices', 'raw_bands', 'diagnostics', 'aggregation', 'water', 'note'}
    if set(result) - allowed:
        raise ValueError('Unreviewed public manifest field')
    item = result['source_item']
    assets = {}
    for name in RAW_BANDS:
        band = result['raw_bands'][name]
        # Public, unsigned CDSE object identifiers only; never signed URLs or headers.
        if not re.fullmatch(r's3://eodata/Sentinel-2/MSI/L2A/[A-Za-z0-9_./-]+', band['asset_href']):
            raise ValueError('Unexpected public band source')
        assets[name] = {'href': band['asset_href'], 'raster:scale': band['scale'],
                        'raster:offset': band['offset'], 'nodata': band['nodata'],
                        'file:checksum': band.get('source_checksum')}
    result['source_item'] = {'id': item['id'], 'properties': {'datetime': item['properties']['datetime']},
                             'assets': assets}
    return result


def calculation_record(value):
    """Preserve the new runtime/source hashes without copying arbitrary audit fields."""
    if value is None:
        return None  # Historical artifacts did not record their installed runtime.
    files, runtime = value['files'], value['runtime']
    if (not isinstance(files, dict) or not isinstance(runtime, dict)
            or set(runtime) != {'python', 'numpy', 'gdal'}
            or any(not isinstance(v, str) or len(v) > 200 for v in runtime.values())
            or any(not re.fullmatch(r'scripts/[\w-]+\.py|data/sentinel-aoi\.json', k)
                   or not re.fullmatch(SHA, v) for k, v in files.items())):
        raise ValueError('Invalid calculation provenance')
    result = {'files': files, 'runtime': runtime}
    digest = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    if value.get('fingerprint') != digest:
        raise ValueError('Calculation provenance checksum mismatch')
    return {**result, 'fingerprint': digest}


def write_recovery(source, catalog_path, site_root, config=None):
    config = config or policy()
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    state_path = catalog_path.with_name('publication.json')
    state = json.loads(state_path.read_text(encoding='utf-8'))
    records = state['products']
    if not 1 <= len(records) <= config['max_acquisitions'] or [(p['id'], p['datetime']) for p in records] != [
            (a['id'], a['datetime']) for a in catalog['acquisitions']]:
        raise ValueError('Retention/catalog/receipt mismatch')
    folders = {}
    for manifest in source.glob('*/manifest.json'):
        record = product_record(lambda name, p=manifest.parent: (p / name).read_bytes())
        folders[record['fingerprint']] = manifest.parent
    if set(folders) != {p['fingerprint'] for p in records}:
        raise ValueError('Recovery inputs differ from published products')
    output = catalog_path.parent
    (output / 'recovery').mkdir()  # A clean stage prevents leftover packages after 8 -> 4.
    entries = []
    for record in records:
        folder = folders[record['fingerprint']]
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name in PRODUCT_FILES:
                data = json.dumps(public_manifest(manifest), sort_keys=True, allow_nan=False).encode() if name == 'manifest.json' else (folder / name).read_bytes()
                member = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                member.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(member, data)
        payload = buffer.getvalue()
        digest = hashlib.sha256(payload).hexdigest()
        with open_product(payload, 'sha256:' + digest) as archive:
            if product_record(archive.read) != record:
                raise ValueError('Sanitized package changes product fingerprint')
        relative = 'recovery/' + digest + '.zip'
        (output / relative).write_bytes(payload)
        origin_path = folder / 'origin.json'
        origin = json.loads(origin_path.read_text()) if origin_path.exists() else {}
        # Origin is produced by the collector, and contains no provider responses.
        entry = {'product': record, 'product_version': manifest['version'], 'path': relative,
                 'sha256': digest, 'size_bytes': len(payload),
                 'calculation': calculation_record((manifest.get('source_audit') or {}).get('calculation', origin.get('calculation'))),
                 **{k: origin[k] for k in ('processed_at', 'run_id', 'artifact_id', 'code_sha') if k in origin}}
        entries.append(entry)
    if select(entries, config['max_acquisitions']) != entries:
        raise ValueError('Recovery selection is not canonical')
    index = {'version': 1, 'retention': config['max_acquisitions'], 'entries': entries,
             'catalog_sha256': hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
             'publication_sha256': hashlib.sha256(state_path.read_bytes()).hexdigest()}
    (output / 'recovery.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
    total = sum(p.stat().st_size for p in site_root.rglob('*') if p.is_file())
    if total > config['max_site_bytes']:
        raise ValueError(f'Site size {total} exceeds budget; preserve current deployment')
    print(f'Retention: {len(entries)}/{config["max_acquisitions"]}; site bytes: {total}/{config["max_site_bytes"]}')
    return index


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', type=Path)
    parser.add_argument('catalog', type=Path)
    parser.add_argument('site', type=Path)
    args = parser.parse_args()
    write_recovery(args.inputs, args.catalog, args.site)
