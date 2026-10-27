"""Paired-pixel changes, incompatible grids, and coverage regressions."""
import unittest
try:
    import numpy as np
    from osgeo import gdal
    from parcel_comparison import compare_parcel
    import test_parcel_ndvi as fixtures
except ImportError:
    if __name__ == '__main__':
        raise SystemExit('GDAL and NumPy required')
    raise unittest.SkipTest('GDAL required in publication job')


class ComparisonTests(unittest.TestCase):
    def raster(self, values):
        return fixtures.ParcelNdviTests().raster([values])

    def test_means_use_exact_same_observations(self):
        a = self.raster([0, .2, .4, .6, 1])
        b = self.raster([.1, .3, .5, .7, -9999])
        row = compare_parcel(a, b, fixtures.polygon(0,20,50,30), 'NDVI')
        self.assertEqual(row, [.3, .4, .1, 4, 5])

    def test_individual_80_percent_does_not_imply_common_80(self):
        a = self.raster([-9999, .2, .4, .6, .8])
        b = self.raster([.1, .3, .5, .7, -9999])
        self.assertEqual(compare_parcel(a,b,fixtures.polygon(0,20,50,30),'NDVI'), [None,None,None,3,5])

    def test_zero_negative_and_evi2_above_one(self):
        a = self.raster([1.5, 1.5]); b = self.raster([1.25, 1.25])
        self.assertEqual(compare_parcel(a,b,fixtures.polygon(0,20,20,30),'EVI2'), [1.5,1.25,-.25,2,2])
        z = self.raster([0,0])
        self.assertEqual(compare_parcel(z,z,fixtures.polygon(0,20,20,30),'NDVI'), [0,0,0,2,2])

    def test_native_20m_and_missing_centres(self):
        a = self.raster([-.2, .2]); b = self.raster([.2, .6])
        for ds in (a,b): ds.SetGeoTransform((0,20,0,40,0,-20))
        self.assertEqual(compare_parcel(a,b,fixtures.polygon(0,20,40,40),'NDMI'), [0,.4,.4,2,2])
        self.assertEqual(compare_parcel(a,b,fixtures.polygon(0,20,2,22),'NDMI'), [None,None,None,0,0])

    def test_reject_shifted_grid_instead_of_silent_resampling(self):
        a = self.raster([.1,.2]); b = self.raster([.2,.3])
        b.SetGeoTransform((1,10,0,30,0,-10))
        with self.assertRaises(ValueError): compare_parcel(a,b,fixtures.polygon(),'NDVI')

    def test_nan_nodata_and_outside_parcel_are_unknown(self):
        a = self.raster([np.nan,-9999]); b = self.raster([0,0])
        self.assertEqual(compare_parcel(a,b,fixtures.polygon(0,20,30,30),'EVI2'),[None,None,None,0,3])


if __name__ == '__main__': unittest.main()
