import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from collect_sentinel_products import collect


class CollectionTests(unittest.TestCase):
    def run_collection(self, dates, bad_digest=False):
        repo = 'example/visor'
        replies = {}
        runs = []
        for number, date in enumerate(dates, 1):
            runs.append({'id': number, 'event': 'schedule', 'head_repository': {'full_name': repo}})
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as archive:
                archive.writestr('manifest.json', json.dumps({'status': 'quality_passed',
                    'source_item': {'properties': {'datetime': date + 'T11:00:00Z'}}}))
                for name in ('NDVI', 'EVI2', 'NDMI', 'SCL'):
                    archive.writestr(name + '.tif', b'fixture')
                archive.writestr('../unexpected.txt', 'Do not extract')
            payload = buffer.getvalue()
            digest = 'sha256:' + hashlib.sha256(payload).hexdigest()
            replies[f'/actions/runs/{number}/artifacts'] = json.dumps({'artifacts': [{
                'id': number, 'name': f'sentinel-{number}', 'expired': False,
                'digest': 'invalid' if bad_digest else digest}]}).encode()
            replies[f'/actions/artifacts/{number}/zip'] = payload
        replies['/actions/workflows/sentinel.yml/runs?branch=main&status=success&per_page=100'] = json.dumps({'workflow_runs': runs}).encode()

        class Opener:
            def open(self, request, timeout):
                return io.BytesIO(replies[request.full_url.removeprefix('https://api.github.com/repos/' + repo)])

        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {
            'GITHUB_REPOSITORY': repo, 'GITHUB_TOKEN': 'test'}), patch(
                'collect_sentinel_products.build_opener', return_value=Opener()):
            root = Path(tmp)
            collect(root / 'products')
            self.assertFalse((root / 'products' / 'unexpected.txt').exists())
            return sorted(p.name for p in (root / 'products').iterdir())

    def test_duplicate_date_skipped_and_only_allowlist_extracted(self):
        self.assertEqual(self.run_collection(['2026-10-14', '2026-10-14', '2026-09-24']), ['1', '3'])

    def test_missing_second_date_stops_deployment(self):
        with self.assertRaisesRegex(ValueError, 'Two distinct'):
            self.run_collection(['2026-10-14', '2026-10-14'])

    def test_checksum_failure_stops_deployment(self):
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.run_collection(['2026-10-14', '2026-09-24'], bad_digest=True)


if __name__ == '__main__':
    unittest.main()
