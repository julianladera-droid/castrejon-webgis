"""Fetch two distinct validated acquisitions from this repository's successful runs."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
from urllib.request import Request, HTTPRedirectHandler, build_opener
import zipfile


def collect(output):
    repo = os.environ['GITHUB_REPOSITORY']
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        raise ValueError('Invalid repository')
    base = f'https://api.github.com/repos/{repo}'

    def get(path):
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

    runs = json.loads(get('/actions/workflows/sentinel.yml/runs?branch=main&status=success&per_page=100'))
    seen = set()
    checked = 0
    for run in runs['workflow_runs']:
        if run.get('head_repository', {}).get('full_name') != repo or run['event'] not in ('schedule', 'workflow_dispatch'):
            continue
        artifacts = json.loads(get(f"/actions/runs/{run['id']}/artifacts"))['artifacts']
        artifact = next((a for a in artifacts if not a['expired'] and a['name'] == f"sentinel-{run['id']}"), None)
        if artifact is None:
            continue
        checked += 1
        if checked > 12:
            break
        payload = get(f"/actions/artifacts/{artifact['id']}/zip")
        if len(payload) > 100_000_000 or artifact.get('digest') != 'sha256:' + hashlib.sha256(payload).hexdigest():
            raise ValueError('Artifact size or checksum mismatch')
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            if manifest.get('status') != 'quality_passed':
                continue
            date = manifest['source_item']['properties']['datetime'][:10]
            if date in seen:
                continue
            destination = output / str(run['id'])
            destination.mkdir(parents=True, exist_ok=True)
            for name in ('manifest.json', 'NDVI.tif', 'EVI2.tif', 'NDMI.tif', 'SCL.tif'):
                info = archive.getinfo(name)
                if info.file_size > 100_000_000:
                    raise ValueError('Unexpected product size')
                (destination / name).write_bytes(archive.read(name))
            seen.add(date)
            print(f"Collected {date} from validated run {run['id']}")
            if len(seen) == 2:
                return
    raise ValueError('Two distinct unexpired acquisitions are required; preserve current deployment')


if __name__ == '__main__':
    collect(Path('sentinel-products'))
