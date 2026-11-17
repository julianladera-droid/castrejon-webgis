"""Offline publication decisions; real run metadata, synthetic product bytes."""
import copy
from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import zipfile

import sentinel_publication as publication
from collect_sentinel_products import github_items
from sentinel_contract import PRODUCT_FILES, PRODUCT_VERSION, RADIOMETRY, WATER_METHOD
from sentinel_schedule import is_due

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = json.loads((ROOT / 'scripts/fixtures/sentinel-publication-runs.json').read_text())


def product_files(identity=None, observed='2026-11-06T11:11:49Z', legacy=False):
    identity = identity or EVIDENCE['cases'][0]['selected_item']
    files = {name: ('synthetic:' + name).encode() for name in PRODUCT_FILES if name != 'manifest.json'}
    hashes = {name[:-4]: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    manifest = {'status': 'quality_passed', 'version': 2 if legacy else PRODUCT_VERSION,
                'radiometry': RADIOMETRY, 'source_item': {'id': identity, 'properties': {'datetime': observed}},
                'indices': {k: {'sha256': v} for k, v in hashes.items() if k in ('NDVI', 'EVI2', 'NDMI', 'NDWI', 'MNDWI')},
                'raw_bands': {k[4:]: {'sha256': v} for k, v in hashes.items() if k.startswith('raw_')},
                'water': {'method': 'optical_surface_water_v2' if legacy else WATER_METHOD,
                          **{k.lower() + '_sha256': hashes[k] for k in ('SCL', 'WATER', 'WATER_QUALITY')}}}
    files['manifest.json'] = json.dumps(manifest).encode()
    return files


class PublicationDecisionTests(unittest.TestCase):
    def setUp(self):
        self.case = copy.deepcopy(EVIDENCE['cases'][0])
        self.files = product_files()
        self.calls = []
        self.state = {'version': 1, 'products': []}

    def decide(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            for name, data in self.files.items():
                archive.writestr(name, data)
            archive.writestr('../untrusted.py', 'never extract')
        payload = buffer.getvalue()
        artifacts = copy.deepcopy(self.case['artifacts'])
        for artifact in artifacts:
            # Retain real IDs/name/expiry; use the digest of synthetic ZIP bytes.
            artifact['digest'] = 'sha256:' + hashlib.sha256(payload).hexdigest()
        run_id = self.case['run']['id']

        def get(path, **kwargs):
            self.calls.append(path)
            if '/jobs?' in path:
                self.assertIn(f'/runs/{run_id}/attempts/1/', path)
                return json.dumps({'jobs': self.case['jobs']}).encode()
            if '/artifacts?' in path:
                self.assertIn(f'/runs/{run_id}/', path)
                return json.dumps({'artifacts': artifacts}).encode()
            if path.endswith('/zip'):
                self.assertIn(path, [f"/actions/artifacts/{a['id']}/zip" for a in artifacts])
                return payload
            self.fail(path)

        with patch('collect_sentinel_products.github_get', side_effect=get), \
                patch.object(publication, 'github_get', side_effect=get), \
                patch.object(publication, 'published_state', return_value=self.state) as state:
            result = publication.decide('workflow_run', {'workflow_run': self.case['run']}, EVIDENCE['repository'])
            if not any(path.endswith('/zip') for path in self.calls):
                state.assert_not_called()
            return result

    def test_real_15_november_new_acquisition_is_published(self):
        self.assertTrue(is_due(date(2026, 11, 15)))
        self.assertEqual(self.case['run']['id'], 43716160874)
        self.assertEqual(self.case['pages_run_id'], 43716464181)
        self.assertIn('20261106', self.files['manifest.json'].decode())
        self.assertEqual(self.decide(), (True, 'new-or-changed-product'))

    def test_real_16_november_calendar_only_skips_all_downstream_work(self):
        self.case = copy.deepcopy(EVIDENCE['cases'][1])
        self.assertFalse(is_due(date(2026, 11, 16)))
        self.assertEqual(self.case['calendar_log'], '2026-11-16: run=false')
        self.assertEqual(self.case['run']['head_sha'], EVIDENCE['cases'][0]['run']['head_sha'])
        self.assertEqual(self.decide(), (False, 'calendar-only-or-no-successful-processing'))
        self.assertEqual(len(self.calls), 1)  # No product download or public-site request.

    def test_reuploaded_or_cached_product_is_not_new(self):
        self.state['products'] = [publication.product_record(self.files.__getitem__)]
        self.assertEqual(self.decide(), (False, 'product-already-published'))

    def test_historical_product_outside_full_retention_window_skips_build(self):
        self.state['products'] = [publication.product_record(product_files(f'NEWER_{day}', f'2026-11-{day:02d}T00:00:00Z').__getitem__)
                                  for day in range(7, 15)]
        self.assertEqual(self.decide(), (False, 'product-outside-retention-window'))

    def test_attempt_specific_artifact_is_accepted(self):
        self.case['artifacts'][0]['name'] += '-1'
        self.assertTrue(self.decide()[0])

    def test_exact_attempt_precedes_legacy_artifact_independent_of_api_order(self):
        legacy = self.case['artifacts'][0]
        exact = {**legacy, 'id': legacy['id'] + 1, 'name': legacy['name'] + '-1'}
        self.case['artifacts'].append(exact)
        self.assertTrue(self.decide()[0])
        self.assertIn(f"/actions/artifacts/{exact['id']}/zip", self.calls)
        self.calls.clear()
        exact['expired'] = True
        self.assertEqual(self.decide(), (False, 'no-retained-product-artifact'))

    def test_historical_cache_recovery_not_in_site_can_publish(self):
        self.state['products'] = [publication.product_record(self.files.__getitem__)]
        self.files = product_files('HISTORICAL_20230816', '2023-08-16T10:56:31Z', legacy=True)
        self.case['run']['event'] = 'workflow_dispatch'
        self.assertEqual(self.decide(), (True, 'new-or-changed-product'))

    def test_same_identity_reprocessed_content_is_new(self):
        self.state['products'] = [publication.product_record(self.files.__getitem__)]
        self.files['NDVI.tif'] += b'changed'
        manifest = json.loads(self.files['manifest.json'])
        manifest['indices']['NDVI']['sha256'] = hashlib.sha256(self.files['NDVI.tif']).hexdigest()
        self.files['manifest.json'] = json.dumps(manifest).encode()
        self.assertTrue(self.decide()[0])

    def test_failed_deployment_does_not_acknowledge_candidate(self):
        # Receipt remains the last successfully published site's receipt.
        self.assertTrue(self.decide()[0])
        self.calls.clear()
        self.assertTrue(self.decide()[0])
        self.state['products'] = [publication.product_record(self.files.__getitem__)]
        self.assertFalse(self.decide()[0])

    def test_first_deployment_with_product_bootstraps_receipt(self):
        self.state = None
        self.assertEqual(self.decide(), (True, 'initialize-publication-receipt'))

    def test_failed_cancelled_wrong_branch_repo_workflow_or_event_never_download(self):
        for field, value in [('conclusion', 'failure'), ('conclusion', 'cancelled'),
                             ('head_branch', 'feature'), ('head_repository', {'full_name': 'other/repo'}),
                             ('path', '.github/workflows/other.yml'), ('event', 'pull_request')]:
            with self.subTest(field=field, value=value):
                self.case = copy.deepcopy(EVIDENCE['cases'][0])
                self.case['run'][field] = value
                self.assertFalse(self.decide()[0])
                self.assertEqual(self.calls, [])

    def test_missing_expired_and_diagnostic_artifacts_skip(self):
        for kind in ('missing', 'expired', 'diagnostics'):
            with self.subTest(kind=kind):
                self.case = copy.deepcopy(EVIDENCE['cases'][0])
                self.calls.clear()
                if kind == 'missing':
                    self.case['artifacts'] = []
                elif kind == 'expired':
                    self.case['artifacts'][0]['expired'] = True
                else:
                    self.case['artifacts'][0]['name'] = 'sentinel-diagnostics-43716160874'
                self.assertEqual(self.decide(), (False, 'no-retained-product-artifact'))

    def test_push_pr_and_manual_pages_do_not_need_sentinel_or_network(self):
        with patch.object(publication, 'github_items', side_effect=AssertionError('network')):
            for event in ('push', 'pull_request', 'workflow_dispatch'):
                self.assertTrue(publication.decide(event, {}, EVIDENCE['repository'])[0])

    def test_corrupt_or_incomplete_product_fails_closed(self):
        self.files['NDVI.tif'] += b'corrupt'
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.decide()
        del self.files['NDVI.tif']
        with self.assertRaisesRegex(ValueError, 'Missing'):
            self.decide()

    def test_artifact_digest_mismatch_fails_closed(self):
        with patch.object(publication, 'github_get', return_value=b'wrong'):
            with self.assertRaisesRegex(ValueError, 'checksum'):
                publication.artifact_record(self.case['artifacts'][0])


class ReceiptTests(unittest.TestCase):
    def test_cli_writes_decision_and_summary_for_manual_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'event.json').write_text('{}')
            env = {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REPOSITORY': EVIDENCE['repository'],
                   'GITHUB_EVENT_PATH': str(root / 'event.json'), 'GITHUB_OUTPUT': str(root / 'output'),
                   'GITHUB_STEP_SUMMARY': str(root / 'summary')}
            with patch.dict(os.environ, env), patch('sys.argv', ['sentinel_publication.py']):
                publication.main()
            self.assertIn('proceed=true\n', (root / 'output').read_text())
            self.assertIn('code-review-or-explicit-pages-run', (root / 'summary').read_text(encoding='utf-8'))

    def test_real_rasters_migrate_build_and_acknowledge_original_product(self):
        # This integration uses the production GDAL pipeline, not fake TIFF bytes.
        # The import raises SkipTest in the lightweight, GDAL-free gate environment.
        from test_sentinel_web import PublicationTests
        from osgeo import gdal
        from sentinel_pipeline import process_rasters
        from sentinel_contract import RAW_BANDS
        from upgrade_sentinel_products import upgrade
        from build_sentinel_web import build
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'inputs' / 'historical'
            source.mkdir(parents=True)
            manifest = PublicationTests().fixture(source)
            rasters = {key: gdal.Open(str(source / f'raw_{key}.tif')) for key in RAW_BANDS}
            process_rasters(rasters, manifest['source_item'], manifest['aoi'], source,
                            {'historical': True}, legacy_water=True)
            rasters.clear()
            original = publication.product_record(lambda name: (source / name).read_bytes())
            upgraded = root / 'migrated'
            upgrade(source, upgraded)
            build(upgraded, root / 'web')
            publication.write_state(root / 'inputs', root / 'web/catalog.json')
            state = json.loads((root / 'web/publication.json').read_text())
            self.assertEqual(state['products'], [original])
            self.assertNotEqual(original, publication.product_record(lambda name: (upgraded / name).read_bytes()))

    def test_query_audit_and_json_format_are_not_product_changes(self):
        files = product_files()
        original = publication.product_record(files.__getitem__)
        manifest = json.loads(files['manifest.json'])
        manifest.update(query={'manual_date': '2026-11-06'}, source_audit={'execution': 999})
        files['manifest.json'] = json.dumps(manifest, indent=4).encode()
        self.assertEqual(original, publication.product_record(files.__getitem__))

    def test_quality_and_version_rejected(self):
        for field, value in [('status', 'selected_not_downloaded'), ('status', 'rejected_local_quality'), ('version', 1)]:
            files = product_files()
            manifest = json.loads(files['manifest.json'])
            manifest[field] = value
            files['manifest.json'] = json.dumps(manifest).encode()
            with self.assertRaisesRegex(ValueError, 'quality-passed'):
                publication.product_record(files.__getitem__)

    def test_receipt_only_acknowledges_built_entries_using_original_v2_input(self):
        files = product_files(legacy=True)
        expected = publication.product_record(files.__getitem__)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for run, content in [('original', files), ('not-built', product_files('UNUSED'))]:
                folder = root / 'inputs' / run
                folder.mkdir(parents=True)
                for name, data in content.items():
                    (folder / name).write_bytes(data)
            catalog = root / 'catalog.json'
            catalog.write_text(json.dumps({'acquisitions': [{'id': expected['id'], 'datetime': expected['datetime']}]}))
            publication.write_state(root / 'inputs', catalog)
            state = json.loads((root / 'publication.json').read_text())
            self.assertEqual(state, {'version': 1, 'products': [expected]})
            catalog.write_text('{"acquisitions": [{"id": "missing", "datetime": "missing"}]}')
            with self.assertRaises(KeyError):
                publication.write_state(root / 'inputs', catalog)

    def test_public_receipt_404_bootstraps_but_errors_do_not(self):
        with patch.object(publication, 'urlopen', side_effect=HTTPError(publication.STATE_URL, 404, '', {}, None)):
            self.assertIsNone(publication.published_state())
        for error in (HTTPError(publication.STATE_URL, 403, '', {}, None), URLError('offline')):
            with patch.object(publication, 'urlopen', side_effect=error), self.assertRaises(type(error)):
                publication.published_state()
        for payload in (b'broken', b'{"version": 2}', b'{"version": 1, "products": [{}]}'):
            with patch.object(publication, 'urlopen', return_value=io.BytesIO(payload)), self.assertRaises(ValueError):
                publication.published_state()

    def test_recheck_uses_fresh_public_url_without_credentials(self):
        payload = b'{"version": 1, "products": []}'
        with patch.object(publication, 'urlopen', side_effect=lambda *args, **kwargs: io.BytesIO(payload)) as get, \
                patch.object(publication.time, 'time_ns', side_effect=[100, 200]):
            publication.published_state()
            publication.published_state()
        first, second = [call.args[0] for call in get.call_args_list]
        self.assertNotEqual(first.full_url, second.full_url)
        self.assertTrue(second.full_url.startswith(publication.STATE_URL + '?'))
        self.assertEqual(second.get_header('Cache-control'), 'no-cache')
        self.assertIsNone(second.get_header('Authorization'))

    def test_pagination_keeps_history_beyond_100_calendar_runs(self):
        pages = [json.dumps({'workflow_runs': [{'id': i} for i in range(100)]}).encode(),
                 b'{"workflow_runs": [{"id": 43716160874}]}']
        with patch('collect_sentinel_products.github_get', side_effect=pages) as get:
            runs = list(github_items('/actions/workflows/sentinel.yml/runs?per_page=100', 'workflow_runs'))
        self.assertEqual(runs[-1]['id'], 43716160874)
        self.assertTrue(get.call_args.args[0].endswith('&page=2'))


class WorkflowContractTests(unittest.TestCase):
    def test_recovery_and_cache_guards_run_before_publication(self):
        yaml = (ROOT / '.github/workflows/pages.yml').read_text()
        self.assertLess(yaml.index('scripts/sentinel_recovery.py'), yaml.index('uses: actions/upload-pages-artifact@'))
        self.assertNotIn('contents: write', yaml)
        sentinel = (ROOT / '.github/workflows/sentinel.yml').read_text()
        self.assertIn('--catalogue-only --output sentinel-selection', sentinel)
        self.assertIn('--catalogue-file sentinel-selection/selection.json', sentinel)
        self.assertIn('uses: actions/cache/restore@v4', sentinel)
        self.assertIn('uses: actions/cache/save@v4', sentinel)
        self.assertIn("if: steps.cached.outputs.usable != 'true'", sentinel)
        self.assertNotIn('retention-days: 90', sentinel)
        self.assertIn('name: sentinel-${{ github.run_id }}-${{ github.run_attempt }}', sentinel)

    def test_noop_runs_cannot_displace_deployment_and_queued_runs_recheck(self):
        yaml = (ROOT / '.github/workflows/pages.yml').read_text()
        before, deploy = yaml.split('  deploy:')
        self.assertNotIn('concurrency:', before)
        self.assertIn('group: sentinel-resources', deploy)
        self.assertIn('id: current', deploy)
        self.assertIn('run: python3 scripts/sentinel_publication.py', deploy)
        for name in ('Setup Pages', 'Collect compatible Sentinel acquisitions by observation date',
                     'Install geospatial runtime', 'Stage public files', 'Upload static site', 'Deploy to GitHub Pages'):
            self.assertIn(f"- name: {name}\n        if: steps.current.outputs.proceed == 'true'", deploy)

    def test_all_heavy_jobs_depend_on_publication_and_quality_gates_remain(self):
        # Dependency assertions supplement actionlint without adding a runtime YAML dependency.
        yaml = (ROOT / '.github/workflows/pages.yml').read_text()
        for job in ('geospatial', 'gate', 'wordpress'):
            self.assertIn(f"  {job}:\n    needs: publication\n    if: needs.publication.outputs.proceed == 'true'", yaml)
        self.assertIn('needs: [publication, gate, wordpress, geospatial]', yaml)
        self.assertIn("github.ref == 'refs/heads/main' && github.event_name != 'pull_request'", yaml)
        for command in ('scripts/check_webgis.py', 'scripts/verify-wordpress.mjs',
                        'scripts/test_sentinel_web.py', 'scripts/upgrade_sentinel_products.py'):
            self.assertIn(command, yaml)
        self.assertLess(yaml.index('--record sentinel-products'), yaml.index('uses: actions/upload-pages-artifact@'))
        self.assertIn('cancel-in-progress: false', yaml)
        self.assertIn('actions: read', yaml.split('  geospatial:')[0])

    def test_calendar_manual_inputs_and_success_only_artifact_preserved(self):
        yaml = (ROOT / '.github/workflows/sentinel.yml').read_text()
        self.assertIn("- cron: '30 5 * * *'", yaml)
        self.assertIn("if: needs.calendar.outputs.run == 'true'", yaml)
        for value in ('workflow_dispatch:', '      date:', '      item_id:'):
            self.assertIn(value, yaml)
        upload = yaml.split('- name: Save products and provenance')[1].split('- name: Save failed')[0]
        self.assertNotIn('always()', upload.split('      - name:')[0])
        self.assertIn('if-no-files-found: error', upload)
        self.assertIn('name: sentinel-diagnostics-${{ github.run_id }}', yaml)


if __name__ == '__main__':
    unittest.main()
