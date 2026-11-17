"""Collector regressions with paginated API metadata and small, synthetic ZIPs."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from collect_sentinel_products import collect
from sentinel_products import product_record
from test_sentinel_publication import product_files


def zipped(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr('../unexpected.txt', 'Do not extract')
    return buffer.getvalue()


class CollectionTests(unittest.TestCase):
    def run_collection(self, dates, bad_digest=False, legacy=False, snapshot=None, limit=8, decoys=0):
        repo = 'example/visor'
        replies = {}
        artifacts = [{'id': 1000+i, 'name': 'diagnostic', 'expired': False} for i in range(decoys)]
        metadata = []
        for number, date in enumerate(dates, 1):
            files = product_files('PRODUCT_' + date.replace('-', ''), date + 'T11:00:00Z')
            if legacy and number == 1:
                manifest = json.loads(files['manifest.json'])
                manifest['version'] = 1
                files['manifest.json'] = json.dumps(manifest).encode()
                del files['raw_B03_10m.tif']
            payload = zipped(files)
            artifacts.append({'id': number, 'name': f'sentinel-{number}', 'expired': False,
                              'created_at': f'2026-11-{20-number:02d}T00:00:00Z',
                              'digest': 'invalid' if bad_digest else 'sha256:' + hashlib.sha256(payload).hexdigest()})
            replies[f'/actions/runs/{number}'] = json.dumps({'id': number, 'event': 'schedule',
                'head_repository': {'full_name': repo}, 'head_branch': 'main', 'conclusion': 'success',
                'path': '.github/workflows/sentinel.yml', 'head_sha': 'a'*40}).encode()
            replies[f'/actions/artifacts/{number}/zip'] = payload
            if not (legacy and number == 1):
                metadata.append({'artifact_id': number, 'product': product_record(files.__getitem__),
                                 'product_version': 3, 'size_bytes': len(payload),
                                 'digest': artifacts[-1]['digest']})
        for offset in range(0, len(artifacts) + 1, 100):
            page = offset // 100 + 1
            suffix = '' if page == 1 else f'&page={page}'
            replies['/actions/artifacts?per_page=100' + suffix] = json.dumps({'artifacts': artifacts[offset:offset+100]}).encode()
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'GITHUB_REPOSITORY': repo}), \
                patch('collect_sentinel_products.github_get', side_effect=lambda path, **kw: replies[path]) as get, \
                patch('collect_sentinel_products.read_state', return_value=({'tombstones': []}, None)), \
                patch('collect_sentinel_products.discover', return_value=metadata), \
                patch('collect_sentinel_products.read_snapshot', return_value=snapshot or []):
            root = Path(tmp)
            collect(root / 'products', {'max_acquisitions': limit})
            self.assertFalse((root / 'unexpected.txt').exists())
            self.assertFalse(any('workflow_runs' in call.args[0] for call in get.call_args_list))
            self.assertLessEqual(sum(c.args[0].endswith('/zip') for c in get.call_args_list), limit)
            return sorted(json.loads(p.read_text())['source_item']['properties']['datetime'][:10]
                          for p in (root / 'products').glob('*/manifest.json'))

    def test_duplicate_day_and_backfill_do_not_change_recency(self):
        self.assertEqual(self.run_collection(['2023-08-16', '2026-10-14', '2026-10-14', '2026-10-31']),
                         ['2023-08-16', '2026-10-14', '2026-10-31'])

    def test_single_old_observation_remains_useful(self):
        self.assertEqual(self.run_collection(['2023-08-16']), ['2023-08-16'])

    def test_artifact_pagination_does_not_use_filtered_run_listing(self):
        self.assertEqual(self.run_collection(['2023-08-16'], decoys=1100), ['2023-08-16'])

    def test_checksum_failure_stops_deployment(self):
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.run_collection(['2026-10-14'], bad_digest=True)

    def test_unsupported_legacy_is_skipped(self):
        self.assertEqual(self.run_collection(['2026-10-31', '2026-10-14'], legacy=True), ['2026-10-14'])
        with self.assertRaisesRegex(ValueError, 'At least one compatible'):
            self.run_collection(['2026-10-31'], legacy=True)

    def test_bootstrap_missing_published_date_fails_instead_of_silently_shrinking(self):
        record = product_record(product_files('OLD', '2023-08-16T00:00:00Z').__getitem__)
        with self.assertRaisesRegex(ValueError, 'retained published dates'):
            self.run_collection(['2026-10-14'], snapshot=[{'product': record, 'product_version': 0, 'unavailable': True}])

    def test_retention_limits_downloaded_collection(self):
        dates = [f'2026-10-{i:02d}' for i in range(1, 10)]
        for limit in (8, 6, 4):
            with self.subTest(limit=limit):
                self.assertEqual(self.run_collection(dates, limit=limit), dates[-limit:])


if __name__ == '__main__':
    unittest.main()
