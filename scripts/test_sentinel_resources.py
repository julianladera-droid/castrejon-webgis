"""Resource and destructive-path regressions. No live network or deletion."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import URLError
import zipfile

import sentinel_cleanup as cleanup
from sentinel_retention import choose, policy, retired
from sentinel_resources import disk_guard
from sentinel_resources import run_step
from sentinel_remote_budget import admit
from sentinel_metadata import discover, sidecar
from sentinel_stage import verify
from sentinel_recovery import write_recovery
from test_sentinel_retention import stage_collection


def entry(day, version=3):
    return {'product': {'id': f'S2A_MSIL2A_202610{day:02d}T110000_N0513_TEST',
                        'datetime': f'2026-10-{day:02d}T11:00:00Z', 'fingerprint': f'{day:064x}'},
            'product_version': version, 'size_bytes': 18_000_000, 'public_bytes': 40_000_000,
            'artifact_id': day, 'digest': 'sha256:' + f'{day:064x}'}


def inventory():
    entries = [entry(d) for d in (8, 7, 6, 5)]
    old = entry(1)
    artifacts = [{'id': d, 'name': f'sentinel-{d}-1', 'size_in_bytes': 18_000_000,
                  'digest': 'sha256:' + f'{d:064x}', 'expired': False} for d in (1, 5, 6, 7, 8)]
    artifacts.append({'id': 99, 'name': 'wordpress', 'size_in_bytes': 1000, 'expired': False})
    return {'repository': 'example/visor', 'recovery': {'entries': entries}, 'artifacts': artifacts,
            'metadata': entries + [old], 'legacy': [], 'caches': [],
            'releases': [{'id': 7, 'assets': [{'id': 10, 'name': 'sentinel-unknown.zip', 'size': 2000},
                                          {'id': 11, 'name': 'wordpress.zip', 'size': 3000}]}]}


class FakeTransport:
    def __init__(self):
        self.inv = inventory()
        self.ledger = {'version': 1, 'tombstones': [], 'operations': {}}
        self.revision = None
        self.deleted = []
        self.verified = False
        self.fail_verify = False
        self.interrupt = False
        self.calls = 0
        self.change_after_verify = False

    def inventory(self):
        self.calls += 1
        if self.change_after_verify and self.calls > 1:
            return {**self.inv, 'recovery': {'entries': [entry(9)]}}
        return copy.deepcopy(self.inv)

    def state(self):
        return copy.deepcopy(self.ledger), self.revision

    def save(self, state, revision):
        assert revision == self.revision
        self.ledger = copy.deepcopy(state)
        self.revision = cleanup.digest(state)
        return self.revision

    def verify(self, entries):
        if self.fail_verify:
            raise ValueError('hash failure')
        self.verified = True

    def delete(self, obj):
        assert self.verified
        assert obj['id'] not in (5, 6, 7, 8, 99)
        assert self.ledger['tombstones']  # journal precedes even a lost DELETE response
        self.inv['artifacts'] = [a for a in self.inv['artifacts'] if a['id'] != obj['id']]
        self.deleted.append(obj['id'])
        if self.interrupt:
            self.interrupt = False
            raise ConnectionError('response lost after deletion')


class ResourcePolicyTests(unittest.TestCase):
    def test_default_four_less_than_four_and_more_than_four(self):
        config = policy()
        self.assertEqual(config['max_acquisitions'], 4)
        for count in (1, 3, 4, 10):
            values, _ = choose([entry(i) for i in range(1, count+1)], config)
            self.assertEqual([e['artifact_id'] for e in values], list(range(count, max(0, count-4), -1)))

    def test_observation_order_not_processing_or_input_order(self):
        old = {**entry(1), 'processed_at': '2099-01-01'}
        newer = [{**entry(d), 'processed_at': '2000-01-01'} for d in range(2, 8)]
        values, _ = choose([old, *newer[::-1]], policy())
        self.assertEqual([e['artifact_id'] for e in values], [7, 6, 5, 4])

    def test_duplicates_incompatible_and_published_copy_preferred(self):
        original = {**entry(1), 'path': 'recovery/example.zip'}
        duplicate = {**entry(1), 'processed_at': '2099-01-01', 'artifact_id': 111}
        values, _ = choose([duplicate, entry(2, 99), original], policy())
        self.assertEqual(values, [original])

    def test_pressure_8_to_6_to_4_and_minimum_failure(self):
        entries = [entry(i) for i in range(1, 9)]
        for maximum, expected in ((450_000_000, 8), (350_000_000, 6), (250_000_000, 4)):
            cfg = {**policy(), 'max_acquisitions': 8, 'max_site_bytes': maximum}
            values, report = choose(entries, cfg)
            self.assertEqual((len(values), report['limit']), (expected, expected))
        with self.assertRaisesRegex(ValueError, 'preserve current deployment'):
            choose(entries, {**policy(), 'max_site_bytes': 100_000_000})
        values, _ = choose(entries, {**policy(), 'max_acquisitions': 8, 'max_site_bytes': 400_000_000,
                                    'available_upload_bytes': 200_000_000})
        self.assertEqual(len(values), 4)

    def test_experimental_pin_does_not_claim_historical_is_latest(self):
        cfg = {**policy(), 'pinned_products': [entry(1)['product']['id']]}
        values, report = choose([entry(i) for i in range(1, 10)], cfg)
        self.assertEqual([e['artifact_id'] for e in values], [9, 8, 7, 1])
        self.assertTrue(report['experimental'])
        self.assertEqual(report['latest_available_observation'], entry(9)['product']['datetime'])
        with self.assertRaisesRegex(ValueError, 'Pinned'):
            choose([entry(2)], cfg)

    def test_retired_products_cannot_return_from_old_index_or_cache(self):
        p = entry(9)
        tombstones = {'tombstones': [{'product': p['product'], 'scope': 'product'}]}
        values, _ = choose([p, entry(8)], policy(), tombstones)
        self.assertEqual(values, [entry(8)])
        p['product']['fingerprint'] = 'a'*64
        self.assertTrue(retired(p, tombstones))

    def test_disk_guard_and_separate_services(self):
        with patch('sentinel_resources.shutil.disk_usage', return_value=SimpleNamespace(free=10)):
            with self.assertRaisesRegex(ValueError, 'Insufficient disk'):
                disk_guard('.', 11, {'min_free_disk_bytes': 0})
        with self.assertRaisesRegex(ValueError, 'Actions'):
            admit(300, 200, 400, 'Actions')
        admit(100, 100, 400, 'Pages')  # Pages headroom never admits Actions storage

    def test_low_disk_prevents_first_raster_download(self):
        from collect_sentinel_products import collect
        with tempfile.TemporaryDirectory() as tmp, \
                patch('collect_sentinel_products.read_snapshot', return_value=[entry(1)]), \
                patch('collect_sentinel_products.read_state', return_value=({}, None)), \
                patch('collect_sentinel_products.github_items', return_value=[]), \
                patch('collect_sentinel_products.discover', return_value=[]), \
                patch('sentinel_resources.shutil.disk_usage', return_value=SimpleNamespace(free=1)), \
                patch('collect_sentinel_products.github_get') as get:
            with self.assertRaisesRegex(ValueError, 'Insufficient disk'):
                collect(Path(tmp) / 'new')
            get.assert_not_called()

    def test_unknown_archives_are_not_downloaded_for_discovery(self):
        with patch.dict('os.environ', {'GITHUB_REPOSITORY': 'example/visor'}), \
                patch('sentinel_metadata.ROOT', Path('/nonexistent')):
            from unittest.mock import Mock
            get = Mock()
            result = discover([{'id': 5, 'name': 'sentinel-5-1', 'expired': False}], [], get)
            self.assertEqual(result, [])
            get.assert_not_called()

    def test_sidecar_integrity_size_and_run_binding(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            z.writestr('product.json', json.dumps(entry(1)))
        payload = b.getvalue()
        artifact = {'id': 1, 'digest': 'sha256:' + hashlib.sha256(payload).hexdigest()}
        self.assertEqual(sidecar(artifact, lambda *a, **k: payload)['product'], entry(1)['product'])
        with self.assertRaisesRegex(ValueError, 'checksum'):
            sidecar({**artifact, 'digest': 'bad'}, lambda *a, **k: payload)
        with self.assertRaises(URLError):
            def fail(*args, **kwargs):
                raise URLError('offline')
            sidecar(artifact, fail)

    def test_previous_generation_optional_and_low_disk_before_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, site, index = stage_collection(root, 1)
            before = (site / 'sentinel/recovery.json').read_bytes()
            with patch('sentinel_resources.shutil.disk_usage', return_value=SimpleNamespace(free=1)):
                with self.assertRaisesRegex(ValueError, 'Insufficient disk'):
                    write_recovery(source, site / 'sentinel/catalog.json', site)
            self.assertEqual((site / 'sentinel/recovery.json').read_bytes(), before)

    def test_process_failure_does_not_reach_publication(self):
        from unittest.mock import Mock
        child = Mock()
        child.poll.return_value = 1
        child.wait.return_value = 1
        with tempfile.TemporaryDirectory() as tmp, patch('sentinel_resources.subprocess.Popen', return_value=child):
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                with self.assertRaisesRegex(ValueError, 'preserve current deployment'):
                    run_step('calculation', ['fake'], policy())
                result = json.loads(Path('sentinel-metrics.jsonl').read_text())
                self.assertEqual(result['exit_code'], 1)
            finally:
                os.chdir(cwd)

    def test_catalog_and_comparison_reference_gate_and_disk_before_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            sentinel = site / 'sentinel'
            sentinel.mkdir()
            data = b'verified fixture'
            target = sentinel / 'file'
            target.write_bytes(data)
            sha = hashlib.sha256(data).hexdigest()
            ref = {'path': 'sentinel/file', 'sha256': sha}
            acquisition = {'id': 'A', 'indices': {'NDVI': {'image': 'sentinel/file', 'download': 'sentinel/file', 'sha256': sha}},
                           'parcel_indices': ref, 'water': {'table': ref, 'zones': ref}}
            catalog = {'acquisitions': [acquisition, {**acquisition, 'id': 'B'}],
                       'comparisons': [{**ref, 'a': 'A', 'b': 'B'}]}
            path = sentinel / 'catalog.json'
            path.write_text(json.dumps(catalog))
            self.assertGreater(verify(site), 0)
            with patch('sentinel_resources.shutil.disk_usage', return_value=SimpleNamespace(free=1)), \
                    self.assertRaisesRegex(ValueError, 'Insufficient disk'):
                verify(site)
            catalog['comparisons'][0]['b'] = 'REMOVED'
            path.write_text(json.dumps(catalog))
            with self.assertRaisesRegex(ValueError, 'unselected'):
                verify(site)
            catalog['comparisons'][0]['b'] = 'B'
            path.write_text(json.dumps(catalog))
            target.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'Corrupt'):
                verify(site)

    def test_previous_generation_kept_once_if_budget_allows(self):
        import sentinel_recovery as recovery
        from sentinel_publication import write_state
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, site, index = stage_collection(root, 2)
            # Keep only observation 2; retain original observation 1 as optional recovery.
            old = index['entries'][1]
            (source / 'previous.json').write_text(json.dumps(index['entries']))
            import shutil
            shutil.rmtree(source / '1')
            for keep_previous in (True, False):
                new_site = root / str(keep_previous)
                catalog = new_site / 'sentinel/catalog.json'
                catalog.parent.mkdir(parents=True)
                catalog.write_text(json.dumps({'acquisitions': [index['entries'][0]['product']]}))
                write_state(source, catalog)
                with patch.object(recovery, 'public_get', side_effect=lambda p, *a: (site / 'sentinel' / p).read_bytes()):
                    result = write_recovery(source, catalog, new_site, {**policy(), 'previous_generation': keep_previous})
                self.assertEqual([e['product'] for e in result['previous']], [old['product']] if keep_previous else [])
                self.assertEqual(len(list((new_site / 'sentinel/recovery').glob('*.zip'))), 2 if keep_previous else 1)


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.config = policy()
        self.plan = cleanup.make_plan(self.transport.inv, self.config)

    def run_plan(self):
        return cleanup.execute(self.plan, self.plan['sha256'], self.transport, self.config)

    def test_only_exact_unselected_owned_objects_and_bytes(self):
        targets = [o['id'] for o in self.plan['objects'] if o['action'] == 'delete']
        self.assertEqual(targets, [1])
        self.assertEqual(self.plan['totals']['artifacts']['reclaimable'], 18_000_000)
        self.assertEqual(self.plan['totals']['releases']['reclaimable'], 0)
        state = self.run_plan()
        self.assertEqual(self.transport.deleted, [1])
        self.assertIsNotNone(state['tombstones'][0]['deleted_at'])

    def test_hash_failure_or_failed_deploy_never_mutates(self):
        self.transport.fail_verify = True
        with self.assertRaisesRegex(ValueError, 'hash'):
            self.run_plan()
        self.assertFalse(self.transport.deleted)
        self.assertIsNone(self.transport.revision)
        self.transport.inv['recovery']['entries'] = [entry(4)]
        with self.assertRaisesRegex(ValueError, 'Publication'):
            self.run_plan()

    def test_interrupted_delete_retry_and_idempotent_completed_retry(self):
        self.transport.interrupt = True
        with self.assertRaises(ConnectionError):
            self.run_plan()
        self.assertTrue(retired(entry(1), self.transport.ledger))
        state = self.run_plan()
        self.assertEqual(len(state['tombstones']), 1)
        count = len(self.transport.deleted)
        self.run_plan()
        self.assertEqual(len(self.transport.deleted), count)

    def test_tampered_plan_cannot_delete_selected_or_foreign_content(self):
        for target in (5, 99):
            plan = copy.deepcopy(self.plan)
            for obj in plan['objects']:
                if obj['id'] == target and obj['service'] == 'artifacts':
                    obj['action'] = 'delete'
            plan['sha256'] = cleanup.digest({k: v for k, v in plan.items() if k != 'sha256'})
            with self.assertRaisesRegex(ValueError, 'protected'):
                cleanup.execute(plan, plan['sha256'], self.transport, self.config)
        self.assertFalse(self.transport.deleted)

    def test_missing_confirmation_ledger_change_or_concurrent_publication(self):
        with self.assertRaisesRegex(ValueError, 'confirmation'):
            cleanup.execute(self.plan, '', self.transport, self.config)
        self.transport.revision = 'changed'
        with self.assertRaisesRegex(ValueError, 'Ledger changed'):
            self.run_plan()
        self.transport.revision = None
        self.transport.calls = 0
        self.transport.change_after_verify = True
        with self.assertRaisesRegex(ValueError, 'during integrity'):
            self.run_plan()
        self.assertFalse(self.transport.deleted)


if __name__ == '__main__':
    unittest.main()
