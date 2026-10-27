"""Known-grid parcel means, including missing coverage and geometric edge cases."""
import unittest
try:
    import numpy as np
    from osgeo import gdal, osr
    from parcel_ndvi import summarize
except ImportError:
    if __name__ == '__main__': raise SystemExit('GDAL and NumPy required')
    raise unittest.SkipTest('GDAL required; mandatory in publication job')


def polygon(x0=0, y0=0, x1=30, y1=30):
    return {'type':'Polygon','coordinates':[[[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]]]}


class ParcelNdviTests(unittest.TestCase):
    def raster(self, values):
        values = np.array(values, dtype=np.float32)
        ds = gdal.GetDriverByName('MEM').Create('', values.shape[1], values.shape[0], 1, gdal.GDT_Float32)
        crs=osr.SpatialReference(); crs.ImportFromEPSG(25830)
        ds.SetProjection(crs.ExportToWkt()); ds.SetGeoTransform((0,10,0,30,0,-10))
        ds.GetRasterBand(1).SetNoDataValue(-9999); ds.GetRasterBand(1).WriteArray(values)
        return ds

    def test_known_mean_and_hole(self):
        ds=self.raster([[.2,.2,.2],[.2,1,.2],[.2,.2,.2]])
        row=summarize(ds,polygon()); self.assertEqual(row['total_pixels'],9)
        self.assertAlmostEqual(row['mean'],.2889)
        hole=polygon(); hole['coordinates'].append(polygon(10,10,20,20)['coordinates'][0])
        row=summarize(ds,hole); self.assertEqual(row['total_pixels'],8); self.assertEqual(row['mean'],.2)

    def test_nodata_extremes_and_nan_not_zero_or_clipped(self):
        for invalid in [-9999, np.nan, np.inf, 2, -2]:
            ds=self.raster([[.4,.4,.4],[.4,invalid,.4],[.4,.4,.4]])
            row=summarize(ds,polygon()); self.assertEqual(row['valid_pixels'],8)
            self.assertEqual(row['mean'],.4); self.assertEqual(row['valid_percent'],88.89)

    def test_quality_boundary_and_zero_is_valid(self):
        ds=self.raster([[0,0,0,0,-9999]])
        row=summarize(ds,polygon(0,20,50,30)); self.assertEqual(row['mean'],0)
        self.assertEqual(row['valid_percent'],80)
        row=summarize(ds,polygon(0,20,60,30)); self.assertIsNone(row['mean'])
        self.assertEqual(row['status'],'insufficient'); self.assertEqual(row['total_pixels'],6)

    def test_small_outside_and_multipolygon(self):
        ds=self.raster([[.1,.2,.3],[.4,.5,.6],[.7,.8,.9]])
        self.assertEqual(summarize(ds,polygon(0,0,2,2))['status'],'no_pixels')
        self.assertEqual(summarize(ds,polygon(100,100,110,110))['status'],'insufficient')
        geom={'type':'MultiPolygon','coordinates':[polygon(0,20,10,30)['coordinates'],polygon(20,0,30,10)['coordinates']]}
        row=summarize(ds,geom); self.assertEqual(row['total_pixels'],2); self.assertEqual(row['mean'],.5)

    def test_crs_and_grid_required(self):
        ds=self.raster([[.5]])
        ds.SetGeoTransform((0,20,0,30,0,-20))
        with self.assertRaises(ValueError): summarize(ds,polygon())

    def test_evi2_not_clipped_to_display_range(self):
        ds=self.raster([[1.5,-.5,2],[1.5,-.5,2],[1.5,-.5,2]])
        row=summarize(ds,polygon(),'EVI2')
        self.assertEqual(row['valid_pixels'],9); self.assertEqual(row['mean'],1)
        ds=self.raster([[1.5,1.5,1.5]])
        self.assertEqual(summarize(ds,polygon(0,20,30,30),'EVI2')['mean'],1.5)

    def test_ndmi_native_grid_and_independent_coverage(self):
        ds=self.raster([[.2,.4],[.6,.8]])
        ds.SetGeoTransform((0,20,0,40,0,-20))
        row=summarize(ds,polygon(0,0,40,40),'NDMI')
        self.assertEqual(row['total_pixels'],4);self.assertEqual(row['mean'],.5)
        ds.GetRasterBand(1).WriteArray(np.array([[.2,.4],[.6,-9999]]))
        self.assertEqual(summarize(ds,polygon(0,0,40,40),'NDMI')['status'],'insufficient')
        self.assertEqual(summarize(ds,polygon(0,0,8,8),'NDMI')['status'],'no_pixels')
        with self.assertRaises(ValueError): summarize(self.raster([[.5]]),polygon(),'NDMI')


if __name__ == '__main__': unittest.main()
