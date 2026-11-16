"""Cache dependency closure and invalidation, using tiny local raster fixtures."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sentinel_cache as cache


class CacheTests(unittest.TestCase):
    def test_detector_dependencies_and_environment_invalidate_fingerprint(self):
        required = ('scripts/field_water.py', 'scripts/water_sharpening.py', 'data/sentinel-aoi.json')
        paths = cache.dependencies()
        self.assertTrue(all(name in paths for name in required))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in paths:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((cache.ROOT / name).read_bytes())
            original = cache.provenance(root, {'gdal': 'a'})['fingerprint']
            self.assertNotEqual(original, cache.provenance(root, {'gdal': 'b'})['fingerprint'])
            for name in required:
                path = root / name
                old = path.read_bytes()
                path.write_bytes(old + b'\n')
                self.assertNotEqual(original, cache.provenance(root, {'gdal': 'a'})['fingerprint'])
                path.write_bytes(old)

    def test_identity_aoi_runtime_parameters_calibration_and_corruption(self):
        from test_sentinel_web import PublicationTests
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'product'
            folder.mkdir()
            manifest = PublicationTests().fixture(folder)
            expected = cache.provenance()
            manifest['source_audit'] = {'calculation': expected}
            selection = root / 'selection.json'
            selection.write_text(json.dumps({'features': [manifest['source_item']]}))
            (root / 'data').mkdir()
            (root / 'data/sentinel-aoi.json').write_text(json.dumps({'processing_aoi': manifest['aoi']}))
            path = folder / 'manifest.json'
            path.write_text(json.dumps(manifest))
            with patch.object(cache, 'ROOT', root):
                cache.validate_cache(folder, selection, expected)
                variants = []
                for kind in ('identity', 'aoi', 'runtime', 'parameters', 'calibration'):
                    changed = copy.deepcopy(manifest)
                    if kind == 'identity': changed['source_item']['id'] = 'OTHER'
                    if kind == 'aoi': changed['aoi']['bounds'][0] += 20
                    if kind == 'runtime': changed['source_audit']['calculation'] = {}
                    if kind == 'parameters': changed['water']['parameters'] = {}
                    if kind == 'calibration': changed['raw_bands']['B03_10m']['offset'] = 0
                    variants.append((kind, changed))
                for kind, changed in variants:
                    with self.subTest(kind=kind):
                        path.write_text(json.dumps(changed))
                        with self.assertRaises(ValueError):
                            cache.validate_cache(folder, selection, expected)
                path.write_text(json.dumps(manifest))
                with (folder / 'raw_B03_10m.tif').open('ab') as stream:
                    stream.write(b'corrupt')
                with self.assertRaises(ValueError):
                    cache.validate_cache(folder, selection, expected)

    def test_missing_or_invalid_cache_requests_recalculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'output'
            with patch.object(cache, 'provenance', return_value={}), \
                    patch.object(cache, 'validate_cache', side_effect=ValueError('bad cache')), \
                    patch.dict('os.environ', {'GITHUB_OUTPUT': str(output)}), \
                    patch('sys.argv', ['cache', '--check', tmp, '--selection', str(Path(tmp) / 'selection')]):
                cache.main()
            self.assertEqual(output.read_text(), 'usable=false\n')


if __name__ == '__main__':
    unittest.main()
