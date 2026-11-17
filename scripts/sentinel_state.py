"""Small CAS journal on a dedicated Git ref; never commits to or deploys main."""
import base64
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BRANCH = 'sentinel-state'
FILE = 'sentinel-state.json'


def api(method, path, body=None):
    from collect_sentinel_products import github_get
    if method == 'GET':
        return json.loads(github_get(path, limit=2_000_000))
    repo = os.environ['GITHUB_REPOSITORY']
    request = Request('https://api.github.com/repos/' + repo + path, method=method,
                      headers={'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
                               'Accept': 'application/vnd.github+json', 'User-Agent': 'castrejon-retention'},
                      data=json.dumps(body).encode() if body is not None else None)
    with urlopen(request, timeout=30) as response:
        payload = response.read(2_000_001)
    return json.loads(payload) if payload else None


def read_state():
    try:
        value = api('GET', f'/contents/{FILE}?ref={BRANCH}')
    except HTTPError as error:
        if error.code != 404:
            raise
        try:
            api('GET', '/git/ref/heads/' + BRANCH)
        except HTTPError as missing:
            if missing.code == 404:
                return {'version': 1, 'tombstones': [], 'operations': {}}, None
            raise
        raise ValueError('State branch exists without journal; stop')
    state = json.loads(base64.b64decode(value['content']))
    if state.get('version') != 1 or not isinstance(state.get('tombstones'), list) or not isinstance(state.get('operations'), dict):
        raise ValueError('Invalid retention ledger')
    return state, value['sha']


def save_state(state, revision):
    payload = json.dumps(state, sort_keys=True, separators=(',', ':')).encode()
    if len(payload) > 900_000:
        raise ValueError('Ledger budget reached; preserve tombstones and review compaction')
    if revision is None:
        base = api('GET', '/git/ref/heads/main')['object']['sha']
        commit = api('GET', '/git/commits/' + base)
        tree = api('POST', '/git/trees', {'base_tree': commit['tree']['sha'],
                   'tree': [{'path': FILE, 'mode': '100644', 'type': 'blob', 'content': payload.decode()}]})
        created = api('POST', '/git/commits', {'message': 'Initialize Sentinel cleanup ledger [skip ci]',
                                             'parents': [base], 'tree': tree['sha']})
        api('POST', '/git/refs', {'ref': 'refs/heads/' + BRANCH, 'sha': created['sha']})
        return api('GET', f'/contents/{FILE}?ref={BRANCH}')['sha']
    body = {'message': 'Record explicit Sentinel cleanup [skip ci]', 'branch': BRANCH,
            'content': base64.b64encode(payload).decode()}
    if revision:
        body['sha'] = revision
    return api('PUT', '/contents/' + FILE, body)['content']['sha']


def prohibit_retired(item):
    state, _ = read_state()
    if any(t.get('scope') == 'product' and t['product']['id'] == item['id'] for t in state['tombstones']):
        raise ValueError('Acquisition retired; explicit restoration of ledger required')
