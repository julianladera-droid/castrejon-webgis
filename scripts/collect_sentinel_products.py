"""Fetch compatible observations; backfill execution order never defines recency."""
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.request import Request, HTTPRedirectHandler, build_opener
from sentinel_contract import compatible, upgradeable, PRODUCT_FILES
from sentinel_products import open_product, product_record
from sentinel_recovery import read_snapshot, restore
from sentinel_retention import policy, select


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


def collect(output, config=None):
    config = config or policy()
    repo = os.environ['GITHUB_REPOSITORY']
    if output.exists():
        raise ValueError('Collection requires a fresh staging directory')
    # Listing artifacts avoids the filtered workflow-runs API's 1,000-result ceiling.
    # Daily empty runs therefore neither consume ZIP downloads nor hide old inputs.
    snapshot = read_snapshot()
    selected = select(snapshot, config['max_acquisitions'])
    known = {e.get('artifact_id') for e in snapshot if not e.get('unavailable')}
    artifacts = github_items('/actions/artifacts?per_page=100', 'artifacts')
    with tempfile.TemporaryDirectory(prefix='sentinel-collect-') as tmp:
        stage = Path(tmp)
        for artifact in artifacts:
            match = re.fullmatch(r'sentinel-(\d+)(?:-(\d+))?', artifact['name'])
            if artifact['expired'] or not match or artifact['id'] in known:
                continue
            run = json.loads(github_get(f'/actions/runs/{match[1]}'))
            if not (run.get('head_repository', {}).get('full_name') == repo
                    and run.get('head_branch') == 'main' and run.get('conclusion') == 'success'
                    and run.get('path') == '.github/workflows/sentinel.yml'
                    and run.get('event') in ('schedule', 'workflow_dispatch')):
                continue
            payload = github_get(f"/actions/artifacts/{artifact['id']}/zip")
            with open_product(payload, artifact.get('digest'), allow_unsupported=True) as archive:
                manifest = json.loads(archive.read('manifest.json'))
                if manifest.get('status') != 'quality_passed' or not (compatible(manifest) or upgradeable(manifest)):
                    continue
                record = product_record(archive.read)
                entry = {'product': record, 'product_version': manifest['version'],
                         'processed_at': artifact['created_at'], 'run_id': run['id'],
                         'artifact_id': artifact['id'], 'code_sha': run['head_sha'],
                         'local_path': str(stage / record['fingerprint'])}
                selected = select([*selected, entry], config['max_acquisitions'])
                if entry in selected:
                    destination = Path(entry['local_path'])
                    destination.mkdir(exist_ok=True)
                    for name in PRODUCT_FILES:
                        (destination / name).write_bytes(archive.read(name))
            # Only temporary, newly downloaded staging files are pruned, never remote data.
            keep = {e.get('local_path') for e in selected}
            for folder in stage.iterdir():
                if str(folder) not in keep:
                    shutil.rmtree(folder)
        if not selected or any(e.get('unavailable') for e in selected):
            raise ValueError('At least one compatible acquisition and all retained published dates are required; preserve current deployment')
        output.mkdir(parents=True)
        for entry in selected:
            destination = output / entry['product']['fingerprint']
            if entry.get('local_path'):
                shutil.copytree(entry['local_path'], destination)
            else:
                restore(entry, destination)
            origin = {k: entry[k] for k in ('processed_at', 'run_id', 'artifact_id', 'code_sha', 'calculation') if k in entry}
            (destination / 'origin.json').write_text(json.dumps(origin), encoding='utf-8')
        print(f'Collected {len(selected)} observations; retention limit {config["max_acquisitions"]}')


if __name__ == '__main__':
    collect(Path('sentinel-products'))
