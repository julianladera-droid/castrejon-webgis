"""Bounded, checksum-verified product I/O shared by publication and recovery."""
from datetime import datetime, timezone
import hashlib
import io
import json
import re
import zipfile

from sentinel_contract import compatible, upgradeable, PRODUCT_FILES

MAX_ARCHIVE_BYTES = 100_000_000
MAX_PRODUCT_BYTES = 200_000_000


def observed_at(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('Observation requires timezone')
    return result.astimezone(timezone.utc)


def product_record(read):
    """Content identity independent of ZIP timestamps, queries and run/cache IDs."""
    manifest = json.loads(read('manifest.json'))
    if manifest.get('status') != 'quality_passed' or not (compatible(manifest) or upgradeable(manifest)):
        raise ValueError('Product is not quality-passed and compatible/upgradeable')
    item = manifest['source_item']
    identity, observed = item['id'], item['properties']['datetime']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,150}', identity):
        raise ValueError('Invalid product identifier')
    observed_at(observed)
    hashes = {}
    for name in PRODUCT_FILES:
        if name == 'manifest.json':
            continue
        key = name.removesuffix('.tif')
        if key.startswith('raw_'):
            expected = manifest['raw_bands'][key[4:]]['sha256']
        elif key in manifest['indices']:
            expected = manifest['indices'][key]['sha256']
        else:
            expected = manifest['water'][key.lower() + '_sha256']
        hashes[name] = hashlib.sha256(read(name)).hexdigest()
        if hashes[name] != expected:
            raise ValueError('Product checksum mismatch')
    metadata = {k: v for k, v in manifest.items() if k not in ('query', 'source_audit', 'source_item')}
    payload = {'id': identity, 'datetime': observed, 'metadata': metadata, 'files': hashes}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                       allow_nan=False).encode()).hexdigest()
    return {'id': identity, 'datetime': observed, 'fingerprint': digest}


def open_product(payload, digest, allow_unsupported=False):
    if len(payload) > MAX_ARCHIVE_BYTES or digest != 'sha256:' + hashlib.sha256(payload).hexdigest():
        raise ValueError('Artifact size or checksum mismatch')
    archive = zipfile.ZipFile(io.BytesIO(payload))
    try:
        names = archive.namelist()
        if names.count('manifest.json') != 1 or archive.getinfo('manifest.json').file_size > 1_000_000:
            raise ValueError('Missing, duplicate or oversized product manifest')
        manifest = json.loads(archive.read('manifest.json'))
        if allow_unsupported and not (compatible(manifest) or upgradeable(manifest)):
            return archive
        for name in PRODUCT_FILES:
            if names.count(name) != 1 or archive.getinfo(name).file_size > MAX_ARCHIVE_BYTES:
                raise ValueError('Missing, duplicate or oversized product member')
        if sum(archive.getinfo(name).file_size for name in PRODUCT_FILES) > MAX_PRODUCT_BYTES:
            raise ValueError('Oversized expanded product')
        return archive
    except Exception:
        archive.close()
        raise
