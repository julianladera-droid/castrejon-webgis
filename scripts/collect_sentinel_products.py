"""Fetch compatible observations; backfill execution order never defines recency."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
from urllib.request import Request, HTTPRedirectHandler, build_opener
import zipfile
from sentinel_contract import compatible, upgradeable, PRODUCT_FILES


def github_get(path):
    repo = os.environ['GITHUB_REPOSITORY']
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        raise ValueError('Invalid repository')
    base = f'https://api.github.com/repos/{repo}'

    request = Request(base + path, headers={'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
                      'Accept': 'application/vnd.github+json', 'User-Agent': 'castrejon-products'})
    # Do not forward the token to artifact storage after GitHub redirects.
    class Redirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not newurl.startswith('https://'):
                raise ValueError('Insecure artifact redirect')
            return Request(newurl, headers={'User-Agent': 'castrejon-products'})
    with build_opener(Redirect).open(request, timeout=60) as response:
        return response.read(100_000_001)


def github_items(path, key):
    """Do not let daily calendar-only runs hide retained historical products."""
    page = 1
    while True:
        suffix = '' if page == 1 else f'&page={page}'
        items = json.loads(github_get(path + suffix))[key]
        yield from items
        if len(items) < 100:
            return
        page += 1


def collect(output):
    repo = os.environ['GITHUB_REPOSITORY']

    runs = github_items('/actions/workflows/sentinel.yml/runs?branch=main&status=success&per_page=100', 'workflow_runs')
    seen = set()
    for run in runs:
        if run.get('head_repository', {}).get('full_name') != repo or run['event'] not in ('schedule', 'workflow_dispatch'):
            continue
        artifacts = json.loads(github_get(f"/actions/runs/{run['id']}/artifacts"))['artifacts']
        artifact = next((a for a in artifacts if not a['expired'] and a['name'] == f"sentinel-{run['id']}"), None)
        if artifact is None:
            continue
        payload = github_get(f"/actions/artifacts/{artifact['id']}/zip")
        if len(payload) > 100_000_000 or artifact.get('digest') != 'sha256:' + hashlib.sha256(payload).hexdigest():
            raise ValueError('Artifact size or checksum mismatch')
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            if manifest.get('status') != 'quality_passed' or not (compatible(manifest) or upgradeable(manifest)):
                continue
            date = manifest['source_item']['properties']['datetime'][:10]
            if date in seen:
                continue
            destination = output / str(run['id'])
            destination.mkdir(parents=True, exist_ok=True)
            for name in PRODUCT_FILES:
                info = archive.getinfo(name)
                if info.file_size > 100_000_000:
                    raise ValueError('Unexpected product size')
                (destination / name).write_bytes(archive.read(name))
            seen.add(date)
            print(f"Collected {date} from validated run {run['id']}")
    if not seen:
        raise ValueError('At least one compatible unexpired acquisition is required; preserve current deployment')


if __name__ == '__main__':
    collect(Path('sentinel-products'))
