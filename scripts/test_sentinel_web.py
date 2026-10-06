"""Publication regressions: integrity, nodata, CRS and display scales."""
import unittest
import tempfile
from pathlib import Path
import json
import hashlib

try:
    import numpy as np
    from osgeo import gdal, osr
    from build_sentinel_web import build, colorize, validate_product, PALETTES
except ImportError:
    if __name__ == '__main__':
        raise SystemExit('GDAL and NumPy required')
    raise unittest.SkipTest('GDAL tests run in Pages publication job')


class PublicationTests(unittest.TestCase):
    def test_fixed_scale_and_transparent_nodata(self):
        a = np.array([[-1, 0, 1, -9999, np.nan]])
        rgba = colorize(a, np.isfinite(a) & (a != -9999), PALETTES['NDVI'])
        self.assertEqual(rgba[:, 0, 0].tolist(), [49, 75, 145, 255])
        self.assertEqual(rgba[:, 0, 2].tolist(), [0, 104, 55, 255])
        self.assertEqual(rgba[3, 0].tolist(), [255, 255, 255, 0, 0])

    def fixture(self, path):
        manifest = {'status': 'quality_passed', 'source_item': {'id': 'TEST_20250101',
                    'properties': {'datetime': '2025-01-01T11:00:00Z'}},
                    'aoi': {'crs': 'EPSG:25830', 'bounds': [380000, 4400000, 380040, 4400040]}, 'indices': {}}
        srs = osr.SpatialReference(); srs.ImportFromEPSG(25830)
        for name in PALETTES:
            resolution = 20 if name == 'NDMI' else 10
            size = 40//resolution
            file = path/f'{name}.tif'
            ds = gdal.GetDriverByName('GTiff').Create(str(file), size, size, 1, gdal.GDT_Float32)
            ds.SetProjection(srs.ExportToWkt()); ds.SetGeoTransform([380000, resolution, 0, 4400040, 0, -resolution])
            ds.GetRasterBand(1).SetNoDataValue(-9999)
            ds.GetRasterBand(1).WriteArray(np.full((size, size), .5)); ds = None
            manifest['indices'][name] = {'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
                'valid_percent_rectangle': 100, 'resolution_m': resolution}
        (path/'manifest.json').write_text(json.dumps(manifest))
        return manifest

    def test_publication_and_reject_tampered_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); product = root/'input'; product.mkdir()
            manifest = self.fixture(product)
            result = build(product, root/'web')
            entry = result['acquisitions'][0]['indices']['NDVI']
            self.assertEqual(entry['projection'], 'EPSG:3857')
            self.assertLess(entry['extent'][0], entry['extent'][2])
            png = gdal.Open(str(root/'web/TEST_20250101/NDVI.png'))
            self.assertEqual(png.RasterCount, 4)
            self.assertEqual(png.GetRasterBand(4).GetColorInterpretation(), gdal.GCI_AlphaBand)
            png = None
            self.assertEqual((root/'web/TEST_20250101/NDVI.tif').read_bytes(), (product/'NDVI.tif').read_bytes())
            manifest['indices']['NDVI']['valid_percent_rectangle'] = 90
            (product/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'quality mismatch'): validate_product(product)
            manifest['indices']['NDVI']['valid_percent_rectangle'] = 100
            (product/'manifest.json').write_text(json.dumps(manifest))
            with (product/'NDVI.tif').open('ab') as stream: stream.write(b'tampered')
            with self.assertRaisesRegex(ValueError, 'checksum'): validate_product(product)


if __name__ == '__main__':
    unittest.main()
