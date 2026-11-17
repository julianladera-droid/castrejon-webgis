"""Select metadata first; download only a bounded, useful collection sequentially."""
import json
import os
from pathlib import Path
import re
from urllib.request import Request, HTTPRedirectHandler, build_opener

from sentinel_contract import PRODUCT_FILES
from sentinel_products import open_product, product_record, MAX_PRODUCT_BYTES
from sentinel_recovery import read_snapshot, restore
from sentinel_retention import policy, choose
from sentinel_resources import disk_guard
from sentinel_metadata import discover
from sentinel_state import read_state


def github_get(path, limit=100_000_000):
    repo = os.environ['GITHUB_REPOSITORY']
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        raise ValueError('Invalid repository')
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'castrejon-products'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    request = Request(f'https://api.github.com/repos/{repo}' + path, headers=headers)
    class Redirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not newurl.startswith('https://'):
                raise ValueError('Insecure artifact redirect')
            return Request(newurl, headers={'User-Agent': 'castrejon-products'})
    with build_opener(Redirect).open(request, timeout=60) as response:
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise ValueError('GitHub response exceeds byte budget')
    return payload


def github_items(path, key):
    for page in range(1, 101):
        suffix = '' if page == 1 else f'&page={page}'
        items = json.loads(github_get(path + suffix, limit=4_000_000))[key]
        yield from items
        if len(items) < 100:
            return
    raise ValueError('Inventory pagination limit reached; refuse partial inventory')


def collect(output, config=None):
    config = config or policy()
    if output.exists():
        raise ValueError('Collection requires a fresh staging directory')
    snapshot = read_snapshot()
    ledger, _ = read_state()
    artifacts = list(github_items('/actions/artifacts?per_page=100', 'artifacts'))
    if 'max_artifact_bytes' in config:
        config = {**config, 'available_upload_bytes': config['max_artifact_bytes'] -
                  sum(a['size_in_bytes'] for a in artifacts if not a['expired']) - 1_000_000}
    entries = discover(artifacts, snapshot, github_get)
    selected, decision = choose([*entries, *snapshot], config, ledger)
    if not selected or any(e.get('unavailable') for e in selected):
        raise ValueError('At least one compatible acquisition and all retained published dates are required; preserve current deployment')
    disk_guard(output, len(selected) * MAX_PRODUCT_BYTES + max(e.get('size_bytes', 100_000_000) for e in selected), config)
    output.mkdir(parents=True)
    for entry in selected:
        disk_guard(output, MAX_PRODUCT_BYTES + entry.get('size_bytes', 100_000_000), config)
        destination = output / entry['product']['fingerprint']
        if entry.get('path'):
            restore(entry, destination)
        else:
            payload = github_get(f"/actions/artifacts/{entry['artifact_id']}/zip", limit=entry['size_bytes'])
            with open_product(payload, entry.get('digest')) as archive:
                if product_record(archive.read) != entry['product']:
                    raise ValueError('Sidecar/product identity mismatch')
                destination.mkdir()
                for name in PRODUCT_FILES:
                    (destination / name).write_bytes(archive.read(name))
            del payload
        origin = {k: entry[k] for k in ('processed_at', 'run_id', 'artifact_id', 'code_sha', 'calculation') if k in entry}
        (destination / 'origin.json').write_text(json.dumps(origin), encoding='utf-8')
    (output / 'selection.json').write_text(json.dumps(decision), encoding='utf-8')
    (output / 'previous.json').write_text(json.dumps(snapshot), encoding='utf-8')
    print(json.dumps(decision))


if __name__ == '__main__':
    collect(Path('sentinel-products'))
