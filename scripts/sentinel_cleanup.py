"""Explicit two-phase Sentinel cleanup; all destructive tests use fake transports.

The published recovery generation is the authority. A proposed smaller collection
is never a deletion prerequisite until it actually exists on Pages.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError

from sentinel_retention import policy
from sentinel_recovery import read_snapshot, restore, public_get
from sentinel_metadata import discover, ROOT
from sentinel_state import read_state, save_state, api


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def make_plan(inventory, config, revision=None):
    entries = inventory['recovery']['entries']
    if not entries or len(entries) > 8:
        raise ValueError('No verified publication to protect')
    selected = {e['product']['fingerprint'] for e in entries}
    identities = {e['product']['id'] for e in entries}
    known = {e.get('artifact_id'): e for e in inventory.get('metadata', []) + entries}
    for e in inventory.get('legacy', []):
        if e['repository'] == inventory['repository']:
            known.setdefault(e['artifact_id'], e)
    objects = []
    # One artifact backup per selected content identity; duplicates are dispensable.
    primary = {}
    for a in sorted(inventory['artifacts'], key=lambda a: a['id'], reverse=True):
        e = known.get(a['id'])
        obj = {'service': 'artifacts', 'id': a['id'], 'name': a['name'], 'bytes': a['size_in_bytes'],
               'digest': a.get('digest'), 'action': 'keep', 'reason': 'foreign or unverified; protected'}
        if e and re.fullmatch(r'sentinel-\d+(?:-\d+)?', a['name']) and not a['expired']:
            # A seeded manifest must still refer to exactly the current archive bytes.
            if e.get('digest') and e['digest'] != a.get('digest'):
                objects.append(obj)
                continue
            p = e['product']
            obj['product'] = p
            obj['scope'] = 'revision' if p['id'] in identities else 'product'
            if p['fingerprint'] in selected and p['fingerprint'] not in primary:
                primary[p['fingerprint']] = a['id']
                obj['reason'] = 'selected acquisition: one independent artifact backup'
            else:
                obj.update(action='delete', reason='duplicate revision' if p['id'] in identities else 'outside published selection')
                # Removing an extra copy must not retire the selected content itself.
                if p['fingerprint'] in selected:
                    obj['scope'] = 'object'
        objects.append(obj)
    cache_total = sum(c['size_in_bytes'] for c in inventory['caches'])
    cache_kept = set()
    for c in sorted(inventory['caches'], key=lambda c: (c['last_accessed_at'], c['id']), reverse=True):
        obj = {'service': 'caches', 'id': c['id'], 'name': c['key'], 'ref': c['ref'],
               'bytes': c['size_in_bytes'], 'version': c['version'], 'action': 'keep',
               'reason': 'foreign or unverified; protected'}
        # Only this project's cache key grammar and main scope are eligible.
        m = re.fullmatch(r'sentinel-v([23])-(?:[0-9a-f]{64}-)?(S2[ABCD]_MSIL2A_[A-Za-z0-9_]+?)(?:-\d+-\d+)?', c['key'])
        if m and c['ref'] == 'refs/heads/main':
            identity = m[2]
            if m[1] == '2' or identity not in identities or identity in cache_kept or cache_total > config['max_cache_bytes'] * config['target_fraction']:
                obj.update(action='delete', reason='obsolete, duplicate or over-budget accelerator; DN protected on Pages')
                cache_total -= c['size_in_bytes']
            else:
                cache_kept.add(identity)
                obj['reason'] = 'one useful current accelerator within budget'
        objects.append(obj)
    # No verified Sentinel archive contract exists in Releases today. Unknown assets
    # stay protected; never delete a whole Release, even if its tag mentions Sentinel.
    for release in inventory['releases']:
        for a in release['assets']:
            objects.append({'service': 'releases', 'id': a['id'], 'name': a['name'], 'bytes': a['size'],
                            'action': 'keep', 'reason': 'no verified Sentinel asset contract; protected'})
    totals = {s: {'before': sum(o['bytes'] for o in objects if o['service'] == s),
                  'reclaimable': sum(o['bytes'] for o in objects if o['service'] == s and o['action'] == 'delete')}
              for s in ('artifacts', 'caches', 'releases')}
    totals['pages'] = {'reclaimable': 0, 'reason': 'published generation protected; only a future atomic deployment can replace Pages files'}
    plan = {'version': 1, 'repository': inventory['repository'], 'state_revision': revision,
            'published_generation': digest(inventory['recovery']), 'selected': [e['product'] for e in entries],
            'objects': objects, 'totals': totals}
    plan['sha256'] = digest(plan)
    return plan


def inventory_live():
    from collect_sentinel_products import github_items, github_get
    snapshot = read_snapshot()  # verifies catalog and receipt, not merely a cached index
    index = json.loads(public_get('recovery.json'))
    if snapshot != index['entries']:
        raise ValueError('Published generation changed during inventory')
    artifacts = list(github_items('/actions/artifacts?per_page=100', 'artifacts'))
    releases = []
    for page in range(1, 101):
        items = json.loads(github_get(f'/releases?per_page=100&page={page}', limit=4_000_000))
        releases.extend(items)
        if len(items) < 100:
            break
    else:
        raise ValueError('Incomplete Releases inventory')
    # Release list embeds a limited assets list; explicitly paginate each one.
    for release in releases:
        assets = []
        for page in range(1, 101):
            part = json.loads(github_get(f"/releases/{release['id']}/assets?per_page=100&page={page}", limit=4_000_000))
            assets.extend(part)
            if len(part) < 100:
                break
        else:
            raise ValueError('Incomplete Release assets')
        release['assets'] = assets
    return {'repository': os.environ['GITHUB_REPOSITORY'], 'recovery': index,
            'artifacts': artifacts, 'caches': list(github_items('/actions/caches?per_page=100', 'actions_caches')),
            'releases': releases, 'metadata': discover(artifacts, snapshot, github_get),
            'legacy': json.loads((ROOT / 'data/sentinel-legacy-products.json').read_text(encoding='utf-8'))}


class Transport:
    def inventory(self):
        return inventory_live()

    def state(self):
        return read_state()

    def save(self, state, revision):
        return save_state(state, revision)

    def verify(self, entries):
        # Sequential restore verifies package and all DN/index checksums and identity.
        from build_sentinel_web import validate_product
        from upgrade_sentinel_products import upgrade
        for entry in entries:
            with tempfile.TemporaryDirectory(prefix='sentinel-cleanup-') as tmp:
                source = Path(tmp) / 'original'
                restore(entry, source)
                if entry['product_version'] == 3:
                    validate_product(source)
                else:
                    upgrade(source, Path(tmp) / 'v3')

    def delete(self, obj):
        if obj['service'] not in ('artifacts', 'caches') or type(obj['id']) is not int:
            raise ValueError('Ineligible deletion target')
        # GitHub IDs are immutable; inventory was checked immediately before this call.
        try:
            api('DELETE', f"/actions/{obj['service']}/{obj['id']}")
        except HTTPError as error:
            if error.code != 404:
                raise


def execute(plan, confirmation, transport, config):
    checked = {k: v for k, v in plan.items() if k != 'sha256'}
    if confirmation != plan['sha256'] or digest(checked) != confirmation:
        raise ValueError('Explicit confirmation must equal exact plan hash')
    live = transport.inventory()
    state, revision = transport.state()
    if plan['repository'] != live['repository'] or digest(live['recovery']) != plan['published_generation']:
        raise ValueError('Publication changed or deployment failed; replan before cleanup')
    operation = state['operations'].get(confirmation)
    if revision != plan['state_revision'] and operation is None:
        raise ValueError('Ledger changed; replan')
    fresh = make_plan(live, config, revision)
    eligible = {(o['service'], o['id']): o for o in fresh['objects'] if o['action'] == 'delete'}
    present = {(o['service'], o['id']) for o in fresh['objects']}
    targets = [o for o in plan['objects'] if o['action'] == 'delete']
    if sum(e['size_bytes'] for e in live['recovery']['entries']) > config['max_transfer_bytes']:
        raise ValueError('Retained integrity verification exceeds transfer budget')
    for obj in targets:
        key = (obj['service'], obj['id'])
        if key in present and eligible.get(key) != obj:
            raise ValueError('Target changed or now protected; refuse deletion')
        if key not in present and operation is None:
            raise ValueError('Inventory changed before first execution; replan')
    transport.verify(live['recovery']['entries'])  # no mutation precedes integrity validation
    # Recheck after potentially slow DN validation; shared job concurrency also guards it.
    if digest(transport.inventory()['recovery']) != plan['published_generation']:
        raise ValueError('Publication changed during integrity verification')
    if operation is None:
        operation = {'started_at': datetime.now(timezone.utc).isoformat(), 'done': []}
        state['operations'][confirmation] = operation
    for obj in targets:
        key = obj['service'] + ':' + str(obj['id'])
        if key in operation['done']:
            continue
        now = datetime.now(timezone.utc).isoformat()
        if obj.get('product') and obj.get('scope') != 'object':
            tombstone = {'product': obj['product'], 'scope': obj['scope'], 'reason': obj['reason'],
                         'object': key, 'planned_at': now, 'deleted_at': None}
            if not any(t['object'] == key for t in state['tombstones']):
                state['tombstones'].append(tombstone)
        # Pending tombstone is durable BEFORE DELETE, so interruption cannot reinsert it.
        revision = transport.save(state, revision)
        transport.delete(obj)
        for t in state['tombstones']:
            if t['object'] == key:
                t['deleted_at'] = datetime.now(timezone.utc).isoformat()
                t['time_semantics'] = 'deletion or absence confirmed; exact first deletion may precede retry'
        operation['done'].append(key)
        revision = transport.save(state, revision)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, help='Offline, read-only audit fixture')
    parser.add_argument('--plan', type=Path, default=Path('sentinel-cleanup-plan.json'))
    parser.add_argument('--execute', metavar='PLAN_SHA256')
    args = parser.parse_args()
    if args.execute:
        if args.inventory:
            raise ValueError('Execution cannot use an offline inventory')
        execute(json.loads(args.plan.read_text()), args.execute, Transport(), policy())
    else:
        if args.inventory:
            inv = json.loads(args.inventory.read_text(encoding='utf-8'))
            inv['legacy'] = json.loads((ROOT / 'data/sentinel-legacy-products.json').read_text(encoding='utf-8'))
            revision = None
        else:
            inv = inventory_live()
            _, revision = read_state()
        plan = make_plan(inv, policy(), revision)
        args.plan.write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'sha256': plan['sha256'], 'totals': plan['totals']}, indent=2))


if __name__ == '__main__':
    main()
