"""Decide whether a completed Sentinel run changes the published product set.

No GDAL, Copernicus requests, cache state or run-date heuristics are needed.
The receipt travels with Pages itself, so a failed build/deploy cannot advance it.
"""
import argparse
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from collect_sentinel_products import github_get, github_items
from sentinel_products import product_record, open_product, observed_at
from sentinel_retention import policy

STATE_URL = 'https://julianladera-droid.github.io/castrejon-webgis/sentinel/publication.json'


def artifact_record(artifact):
    payload = github_get(f"/actions/artifacts/{artifact['id']}/zip")
    with open_product(payload, artifact.get('digest')) as archive:
        return product_record(archive.read)


def published_state():
    query = urlencode({'run': os.environ.get('GITHUB_RUN_ID', 'local'),
                       'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', '1'), 'check': time.time_ns()})
    request = Request(STATE_URL + '?' + query, headers={'Cache-Control': 'no-cache', 'User-Agent': 'castrejon-publication'})
    try:
        with urlopen(request, timeout=30) as response:
            state = json.loads(response.read(1_000_001))
    except HTTPError as error:
        if error.code == 404:
            return None  # First deployment of this contract, or site recovery.
        raise
    if state.get('version') != 1 or not isinstance(state.get('products'), list):
        raise ValueError('Invalid published Sentinel receipt')
    for product in state['products']:
        if not (isinstance(product.get('id'), str) and isinstance(product.get('datetime'), str)
                and re.fullmatch(r'[0-9a-f]{64}', product.get('fingerprint', ''))):
            raise ValueError('Invalid published product record')
    return state


def decide(event_name, event, repository):
    if event_name in ('push', 'pull_request', 'workflow_dispatch'):
        return True, 'code-review-or-explicit-pages-run'
    if event_name != 'workflow_run':
        return False, 'unsupported-event'
    run = event['workflow_run']
    if not (run.get('conclusion') == 'success' and run.get('head_branch') == 'main'
            and run.get('head_repository', {}).get('full_name') == repository
            and run.get('path') == '.github/workflows/sentinel.yml'
            and run.get('event') in ('schedule', 'workflow_dispatch')):
        return False, 'unsuccessful-or-untrusted-sentinel-run'
    run_id = int(run['id'])
    jobs = list(github_items(f"/actions/runs/{run_id}/attempts/{int(run.get('run_attempt', 1))}/jobs?per_page=100", 'jobs'))
    sentinel = next((job for job in jobs if job['name'] == 'sentinel'), None)
    if sentinel is None or sentinel.get('conclusion') != 'success':
        return False, 'calendar-only-or-no-successful-processing'
    artifacts = list(github_items(f'/actions/runs/{run_id}/artifacts?per_page=100', 'artifacts'))
    exact_name = f"sentinel-{run_id}-{int(run.get('run_attempt', 1))}"
    artifact = next((a for a in artifacts if a['name'] == exact_name), None)
    if artifact is None:
        artifact = next((a for a in artifacts if a['name'] == f'sentinel-{run_id}'), None)
    if artifact is None or artifact['expired']:
        return False, 'no-retained-product-artifact'
    candidate = artifact_record(artifact)
    state = published_state()
    if state is None:
        return True, 'initialize-publication-receipt'
    if candidate in state['products']:
        return False, 'product-already-published'
    limit = policy()['max_acquisitions']
    days = sorted({observed_at(p['datetime']).date() for p in state['products']}, reverse=True)
    if len(days) >= limit and observed_at(candidate['datetime']).date() < days[limit - 1]:
        return False, 'product-outside-retention-window'
    return True, 'new-or-changed-product'


def write_state(source, catalog_path):
    """Record original inputs of the built catalogue, including v2 -> v3 inputs."""
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    records = {}
    for path in sorted(source.glob('*/manifest.json')):
        record = product_record(lambda name, folder=path.parent: (folder / name).read_bytes())
        key = (record['id'], record['datetime'])
        if key in records:
            raise ValueError('Duplicate publication input')
        records[key] = record
    products = [records[(a['id'], a['datetime'])] for a in catalog['acquisitions']]
    if not products:
        raise ValueError('Cannot acknowledge an empty publication')
    target = catalog_path.with_name('publication.json')
    target.write_text(json.dumps({'version': 1, 'products': products}, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', nargs=2, type=Path, metavar=('INPUTS', 'CATALOG'))
    args = parser.parse_args()
    if args.record:
        write_state(*args.record)
        return
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    proceed, reason = decide(os.environ['GITHUB_EVENT_NAME'], event, os.environ['GITHUB_REPOSITORY'])
    line = f'proceed={str(proceed).lower()}'
    print(f'{line}: {reason}')
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write(f'{line}\nreason={reason}\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
            summary.write(f'Sentinel publication decision: `{line}` — `{reason}`\n')


if __name__ == '__main__':
    main()
