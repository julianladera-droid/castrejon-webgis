"""Numerical and selection regressions; requires QGIS/GDAL Python or CI runtime."""
import unittest

try:
    import numpy as np
    from sentinel_pipeline import aligned_bounds, indices, select_scene, BANDS
except ImportError:
    if __name__ == '__main__':
        raise SystemExit('Run these tests with GDAL and NumPy installed')
    raise unittest.SkipTest('GDAL/NumPy tests run separately in Sentinel workflow')


class SentinelTests(unittest.TestCase):
    def test_grid_encloses_source_and_aligns(self):
        self.assertEqual(aligned_bounds([3.5, 22.1, 48.2, 65.8], 20), [0, 20, 60, 80])

    def test_known_reflectance_and_cloud_mask(self):
        red = np.array([[0.2, 0.2, np.nan]])
        nir = np.array([[0.6, 0.6, 0.6]])
        scl = np.array([[4, 9, 5]])
        out = indices(red, nir, nir, red, scl, scl)
        self.assertAlmostEqual(float(out['NDVI'][0, 0]), 0.5, places=6)
        self.assertAlmostEqual(float(out['EVI2'][0, 0]), 1/2.08, places=6)
        self.assertEqual(out['NDVI'][0, 1], -9999)
        self.assertEqual(out['NDVI'][0, 2], -9999)
        self.assertAlmostEqual(float(out['NDMI'][0, 0]), 0.5, places=6)

    def test_zero_denominator_is_nodata(self):
        zero = np.zeros((1, 1))
        quality = np.full((1, 1), 5)
        out = indices(zero, zero, zero, zero, quality, quality)
        self.assertEqual(out['NDVI'][0, 0], -9999)
        self.assertEqual(out['NDMI'][0, 0], -9999)
        self.assertEqual(out['EVI2'][0, 0], 0)

    def test_selection_requires_full_coverage_and_quality(self):
        def item(name, date, cloud, extent=2):
            return {'id': name, 'properties': {'datetime': date, 'eo:cloud_cover': cloud},
                    'assets': dict.fromkeys(BANDS), 'geometry': {'type': 'Polygon',
                    'coordinates': [[[-2,-2],[extent,-2],[extent,extent],[-2,extent],[-2,-2]]]}}
        good = item('good', '2026-09-24T11:07:21Z', 1)
        cloudy = item('cloudy', '2026-10-04T11:07:21Z', 94)
        partial = item('partial', '2026-10-02T11:07:21Z', 0, 0.5)
        self.assertEqual(select_scene([good, cloudy, partial], [0,0,1,1])['id'], 'good')
        with self.assertRaises(ValueError):
            select_scene([cloudy, partial], [0,0,1,1])


if __name__ == '__main__':
    unittest.main()
