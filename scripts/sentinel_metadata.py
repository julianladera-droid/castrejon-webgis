"""Small, run-bound sidecars allow selection before downloading raster packages."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import zipfile

from sentinel_products import product_record, observed_at

ROOT = Path(__file__).resolve().parents[1]


def validate(entry):
    p = entry['product']
    if (not re.fullmatch(r'[A-Za-z0-9_-]{1,150}', p['id']) or
            not re.fullmatch(r'[0-9a-f]{64}', p['fingerprint']) or entry['product_version'] not in (2, 3)
            or type(entry.get('size_bytes')) is not int or not 0 < entry['size_bytes'] <= 100_000_000):
        raise ValueError('Invalid product sidecar')
    observed_at(p['datetime'])
    return {k: entry[k] for k in ('product', 'product_version', 'size_bytes')}


def sidecar(artifact, get):
    payload = get(f"/actions/artifacts/{artifact['id']}/zip", limit=1_000_000)
    digest = artifact.get('digest')
    if not digest or digest != 'sha256:' + hashlib.sha256(payload).hexdigest():
        raise ValueError('Sidecar checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != 'product.json' or members[0].file_size > 100_000:
            raise ValueError('Invalid metadata ZIP')
        return validate(json.loads(archive.read('product.json')))


def discover(artifacts, snapshot, get):
    """Unknown pre-sidecar archives are quarantined, never downloaded speculatively."""
    repo = os.environ['GITHUB_REPOSITORY']
    known = {e.get('artifact_id'): e for e in snapshot if not e.get('unavailable')}
    seed_path = ROOT / 'data/sentinel-legacy-products.json'
    seeds = json.loads(seed_path.read_text(encoding='utf-8')) if seed_path.exists() else []
    seed = {s['artifact_id']: s for s in seeds if s['repository'] == repo}
    names = {a['name']: a for a in artifacts if not a['expired']}
    entries = []
    for a in artifacts:
        match = re.fullmatch(r'sentinel-(\d+)(?:-(\d+))?', a['name'])
        if a['expired'] or not match or a['id'] in known:
            continue
        metadata = names.get('sentinel-index-' + a['name'][9:])
        trusted_seed = seed.get(a['id'])
        if metadata is None and (not trusted_seed or trusted_seed['digest'] != a.get('digest')):
            continue
        run = json.loads(get(f'/actions/runs/{match[1]}'))
        if not (run.get('head_repository', {}).get('full_name') == repo and run.get('head_branch') == 'main'
                and run.get('conclusion') == 'success' and run.get('path') == '.github/workflows/sentinel.yml'
                and run.get('event') in ('schedule', 'workflow_dispatch')):
            continue
        if metadata:
            if metadata.get('workflow_run', {}).get('id') != run['id']:
                raise ValueError('Sidecar belongs to another run')
            entry = sidecar(metadata, get)
        elif trusted_seed.get('product_version') in (2, 3):
            entry = validate(trusted_seed)
        else:
            continue
        entries.append({**entry, 'size_bytes': a.get('size_in_bytes', entry['size_bytes']),
                        'processed_at': a['created_at'], 'run_id': run['id'], 'code_sha': run['head_sha'],
                        'artifact_id': a['id'], 'digest': a.get('digest')})
    return entries


def write(folder, target):
    from sentinel_contract import PRODUCT_FILES
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    record = product_record(lambda name: (folder / name).read_bytes())
    # Upper bound before upload compression; archive size comes from GitHub listing later.
    entry = {'product': record, 'product_version': manifest['version'],
             'size_bytes': sum((folder / n).stat().st_size for n in PRODUCT_FILES)}
    validate(entry)
    target.mkdir(parents=True, exist_ok=True)
    (target / 'product.json').write_text(json.dumps(entry), encoding='utf-8')


if __name__ == '__main__':
    write(Path('sentinel-output'), Path('sentinel-index'))
