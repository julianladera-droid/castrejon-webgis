"""Offline retention, continuity and recovery tests; no real acquisitions downloaded."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import zipfile

from collect_sentinel_products import collect
from sentinel_contract import RAW_BANDS
from sentinel_products import open_product, product_record
from sentinel_publication import write_state
import sentinel_recovery as recovery
from sentinel_retention import policy, select
from test_collect_sentinel_products import zipped
from test_sentinel_publication import product_files


def fixture_files(day=1):
    files = product_files(f'S2A_202610{day:02d}_N0513_TEST', f'2026-10-{day:02d}T11:00:00Z')
    manifest = json.loads(files['manifest.json'])
    for name, band in manifest['raw_bands'].items():
        band.update(asset_href=f's3://eodata/Sentinel-2/MSI/L2A/fixture/{name}.jp2',
                    scale=.0001, offset=-.1, nodata=0, source_checksum=None)
    manifest['query'] = {'private': 'PRIVATE-MARKER'}
    manifest['source_audit'] = {'private': 'PRIVATE-MARKER'}
    manifest['source_item']['links'] = [{'href': 'PRIVATE-MARKER'}]
    files['manifest.json'] = json.dumps(manifest).encode()
    return files


def stage_collection(root, count=8):
    source = root / 'inputs'
    records = []
    for day in range(count, 0, -1):
        folder = source / str(day)
        folder.mkdir(parents=True)
        files = fixture_files(day)
        for name, data in files.items():
            (folder / name).write_bytes(data)
        records.append(product_record(files.__getitem__))
    site = root / 'site'
    catalog = site / 'sentinel/catalog.json'
    catalog.parent.mkdir(parents=True)
    catalog.write_text(json.dumps({'acquisitions': records}))
    write_state(source, catalog)
    index = recovery.write_recovery(source, catalog, site)
    return source, site, index


class RetentionTests(unittest.TestCase):
    def test_only_explicit_8_6_4_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            for limit in (8, 6, 4, 0, 5, 20):
                path.write_text(json.dumps({'version': 1, 'max_acquisitions': limit, 'max_site_bytes': 400_000_000}))
                if limit in (8, 6, 4):
                    self.assertEqual(policy(path)['max_acquisitions'], limit)
                else:
                    with self.assertRaises(ValueError):
                        policy(path)

    def test_baseline_then_schema_precede_processing_date(self):
        base = {'product': product_record(fixture_files().__getitem__), 'product_version': 3,
                'processed_at': '2026-11-01T00:00:00Z'}
        old = copy.deepcopy(base)
        old['product']['id'] = base['product']['id'].replace('N0513', 'N0509')
        old['processed_at'] = '2026-11-16T00:00:00Z'
        v2 = {**base, 'product_version': 2, 'processed_at': '2026-11-17T00:00:00Z'}
        newer_revision = {**base, 'processed_at': '2026-11-02T00:00:00Z'}
        self.assertEqual(select([old, v2, base], 4), [base])
        self.assertEqual(select([base, newer_revision], 4), [newer_revision])
        self.assertEqual(select([newer_revision, base], 4), [newer_revision])


class RecoveryTests(unittest.TestCase):
    def test_real_collection_has_only_retained_dates_and_adjacent_comparisons(self):
        from test_sentinel_web import PublicationTests
        from test_parcel_ndvi import polygon
        from build_sentinel_web import build_collection
        import contextlib
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp)
            master = root / 'master.json'
            master.write_text(json.dumps({'crs': 'EPSG:25830', 'web_sha256': 'a'*64,
                'features': [{'refcat': 'fixture', 'geometry': polygon(380000, 4400000, 380040, 4400040)}]}))
            entries = []
            for day in range(1, 9):
                folder = root / 'all' / str(day)
                folder.mkdir(parents=True)
                PublicationTests().fixture(folder, f'TEST_202510{day:02d}', f'2025-10-{day:02d}T11:00:00Z')
                entries.append({'product': product_record(lambda name, p=folder: (p / name).read_bytes()),
                                'product_version': 3, 'local_path': str(folder)})
            for limit in (8, 6, 4):
                selected = select(entries, limit)
                folders = [Path(e['local_path']) for e in selected]
                # Parcel-table validation has its own regressions; this fixture uses one parcel.
                # Rasters, temporal water, paired-pixel comparisons and catalogue are real.
                with patch('build_sentinel_web.build_parcel_indices', return_value={'parcel_web_sha256': 'a'*64}) as parcel_stats:
                    catalog = build_collection(folders, root / f'web-{limit}', master, root)
                    parcel_stats.reset_mock()  # Release GDAL datasets retained in mock call arguments.
                ids = {e['product']['id'] for e in selected}
                self.assertEqual({a['id'] for a in catalog['acquisitions']}, ids)
                self.assertEqual(len(catalog['comparisons']), limit - 1)
                for comparison in catalog['comparisons']:
                    self.assertTrue({comparison['a'], comparison['b']} <= ids)
                    relative = comparison['path'].removeprefix('sentinel/')
                    content = (root / f'web-{limit}' / relative).read_bytes()
                    self.assertEqual(hashlib.sha256(content).hexdigest(), comparison['sha256'])

    def test_packages_preserve_fingerprint_and_exclude_private_catalogue(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, site, index = stage_collection(Path(tmp), 1)
            entry = index['entries'][0]
            payload = (site / 'sentinel' / entry['path']).read_bytes()
            with open_product(payload, 'sha256:' + entry['sha256']) as archive:
                self.assertNotIn(b'PRIVATE-MARKER', archive.read('manifest.json'))
                self.assertEqual(product_record(archive.read), entry['product'])
                self.assertTrue(all(f'raw_{band}.tif' in archive.namelist() for band in RAW_BANDS))
                manifest = json.loads(archive.read('manifest.json'))
                self.assertEqual(manifest['source_item']['assets']['B03_10m']['raster:offset'], -.1)
            self.assertIn(b'PRIVATE-MARKER', (source / '1/manifest.json').read_bytes())

    def test_total_expiry_and_8_to_6_to_4_restore_without_cache_or_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, site, _ = stage_collection(root)
            original = (site / 'sentinel/recovery.json').read_bytes()
            for limit in (8, 6, 4):
                with self.subTest(limit=limit), patch.object(recovery, 'public_get', side_effect=lambda path, *args: (site / 'sentinel' / path).read_bytes()), \
                        patch('collect_sentinel_products.github_get', return_value=b'{"artifacts": []}') as get, \
                        patch.dict('os.environ', {'GITHUB_REPOSITORY': 'example/visor'}):
                    output = root / f'restored-{limit}'
                    collect(output, {'max_acquisitions': limit})
                    self.assertEqual(get.call_count, 1)
                    manifests = list(output.glob('*/manifest.json'))
                    dates = sorted(json.loads(p.read_text())['source_item']['properties']['datetime'] for p in manifests)
                    self.assertEqual(len(dates), limit)
                    self.assertIn(f'2026-10-{9-limit:02d}', dates[0])
                    new_site = root / f'site-{limit}'
                    catalog = new_site / 'sentinel/catalog.json'
                    catalog.parent.mkdir(parents=True)
                    records = [product_record(lambda name, folder=p.parent: (folder / name).read_bytes()) for p in manifests]
                    catalog.write_text(json.dumps({'acquisitions': sorted(records, key=lambda r: r['datetime'], reverse=True)}))
                    write_state(output, catalog)
                    index = recovery.write_recovery(output, catalog, new_site, {'max_acquisitions': limit, 'max_site_bytes': 400_000_000})
                    self.assertEqual(len(index['entries']), limit)
                    self.assertEqual(len(list((new_site / 'sentinel/recovery').glob('*.zip'))), limit)
                    self.assertEqual((site / 'sentinel/recovery.json').read_bytes(), original)

    def test_partial_expiry_adds_new_observation_and_preserves_published_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, site, _ = stage_collection(root, 2)
            payload = zipped(fixture_files(3))
            artifact = {'id': 3, 'name': 'sentinel-3-2', 'expired': False, 'created_at': '2026-11-15T00:00:00Z',
                        'digest': 'sha256:' + hashlib.sha256(payload).hexdigest()}
            run = {'id': 3, 'head_repository': {'full_name': 'example/visor'}, 'head_branch': 'main',
                   'conclusion': 'success', 'path': '.github/workflows/sentinel.yml', 'event': 'schedule', 'head_sha': 'b'*40}
            replies = {'/actions/artifacts?per_page=100': json.dumps({'artifacts': [artifact, {**artifact, 'id': 1, 'expired': True}]}).encode(),
                       '/actions/runs/3': json.dumps(run).encode(), '/actions/artifacts/3/zip': payload}
            with patch.object(recovery, 'public_get', side_effect=lambda path, *args: (site / 'sentinel' / path).read_bytes()), \
                    patch('collect_sentinel_products.github_get', side_effect=replies.__getitem__), \
                    patch.dict('os.environ', {'GITHUB_REPOSITORY': 'example/visor'}):
                collect(root / 'restored')
            self.assertEqual(len(list((root / 'restored').glob('*/manifest.json'))), 3)

    def test_corruption_and_byte_budget_fail_before_upload_without_changing_previous_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, site, index = stage_collection(root, 1)
            original = (site / 'sentinel/recovery.json').read_bytes()
            def get(path, *args):
                data = (site / 'sentinel' / path).read_bytes()
                return data[:-1] + b'!' if path.endswith('.zip') else data
            with patch.object(recovery, 'public_get', side_effect=get), self.assertRaisesRegex(ValueError, 'checksum'):
                recovery.restore(index['entries'][0], root / 'corrupt')
            self.assertFalse((root / 'corrupt').exists())
            new_site = root / 'oversize'
            catalog = new_site / 'sentinel/catalog.json'
            catalog.parent.mkdir(parents=True)
            catalog.write_bytes((site / 'sentinel/catalog.json').read_bytes())
            write_state(source, catalog)
            with self.assertRaisesRegex(ValueError, 'exceeds budget'):
                recovery.write_recovery(source, catalog, new_site, {'max_acquisitions': 4, 'max_site_bytes': 1})
            self.assertEqual((site / 'sentinel/recovery.json').read_bytes(), original)

    def test_missing_index_bootstrap_retains_receipt_but_network_errors_never_mean_empty(self):
        error404 = HTTPError(recovery.BASE_URL, 404, '', {}, None)
        record = product_record(fixture_files().__getitem__)
        with patch.object(recovery, 'public_get', side_effect=[error404, json.dumps({'version': 1, 'products': [record]}).encode()]):
            self.assertTrue(recovery.read_snapshot()[0]['unavailable'])
        for error in (URLError('offline'), HTTPError(recovery.BASE_URL, 403, '', {}, None)):
            with patch.object(recovery, 'public_get', side_effect=error), self.assertRaises(type(error)):
                recovery.read_snapshot()

    def test_catalog_and_receipt_mismatch_or_unsafe_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, site, _ = stage_collection(Path(tmp), 1)
            def get(path, *args):
                return b'{}' if path == 'catalog.json' else (site / 'sentinel' / path).read_bytes()
            with patch.object(recovery, 'public_get', side_effect=get), self.assertRaisesRegex(ValueError, 'checksum'):
                recovery.read_snapshot()
        with patch.object(recovery, 'urlopen') as network:
            for path in ('../secret', 'https://other.example/file.zip', 'recovery/../../file.zip'):
                with self.assertRaises(ValueError):
                    recovery.public_get(path)
            network.assert_not_called()

    def test_duplicate_and_oversized_members_fail_closed(self):
        files = fixture_files()
        payload = io.BytesIO(zipped(files))
        with zipfile.ZipFile(payload, 'a') as archive:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                archive.writestr('NDVI.tif', b'duplicate')
        data = payload.getvalue()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            open_product(data, 'sha256:' + hashlib.sha256(data).hexdigest())
        data = zipped(files)
        with patch('sentinel_products.MAX_PRODUCT_BYTES', 1), self.assertRaisesRegex(ValueError, 'Oversized'):
            open_product(data, 'sha256:' + hashlib.sha256(data).hexdigest())

    def test_sanitized_legacy_dn_can_recalculate_v3_and_publish(self):
        from test_sentinel_web import PublicationTests
        from osgeo import gdal
        from sentinel_pipeline import process_rasters
        from upgrade_sentinel_products import upgrade
        from build_sentinel_web import build
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'inputs/one'
            source.mkdir(parents=True)
            manifest = PublicationTests().fixture(source)
            for name, asset in manifest['source_item']['assets'].items():
                asset['href'] = f's3://eodata/Sentinel-2/MSI/L2A/fixture/{name}.jp2'
            rasters = {key: gdal.Open(str(source / f'raw_{key}.tif')) for key in RAW_BANDS}
            process_rasters(rasters, manifest['source_item'], manifest['aoi'], source, {}, legacy_water=True)
            rasters.clear()
            upgrade(source, root / 'upgraded')
            build(root / 'upgraded', root / 'site/sentinel')
            catalog = root / 'site/sentinel/catalog.json'
            write_state(root / 'inputs', catalog)
            index = recovery.write_recovery(root / 'inputs', catalog, root / 'site')
            with patch.object(recovery, 'public_get', side_effect=lambda path, *args: (root / 'site/sentinel' / path).read_bytes()):
                recovery.restore(index['entries'][0], root / 'restored')
            upgrade(root / 'restored', root / 'recalculated')
            build(root / 'recalculated', root / 'rebuilt')
            self.assertEqual((root / 'rebuilt/catalog.json').read_bytes(), catalog.read_bytes())


if __name__ == '__main__':
    unittest.main()
