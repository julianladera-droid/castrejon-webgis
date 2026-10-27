import unittest
try:
    import numpy as np
    from osgeo import gdal
    from parcel_water import classify, regions, parcel_areas
    import test_parcel_ndvi as fixtures
    polygon = fixtures.polygon
except ImportError:
    if __name__ == '__main__': raise SystemExit('GDAL and NumPy required')
    raise unittest.SkipTest('GDAL required in publication job')


class WaterTests(unittest.TestCase):
    def raster(self, values):
        ds = fixtures.ParcelNdviTests().raster(values)
        ds.SetGeoTransform((0, 20, 0, 40, 0, -20))
        return ds

    def test_transitions_exclude_clouds_shadows_ambiguous_and_old_water(self):
        a = np.array([4, 5, 6, 3, 7, 0, 4, 6, -9999, 4, 4])
        b = np.array([6, 6, 6, 6, 6, 6, 9, 4, 6, 5, 11])
        self.assertEqual(classify(a, b).tolist(), [1,1,2,3,3,3,3,0,3,0,3])

    def test_fractional_border_uses_whole_parcel_denominator(self):
        v = regions(self.raster([[4,4,9]]), self.raster([[6,5,6]]))
        # 10m of new water, 20m evaluated dry, 10m cloud; 40x20m parcel.
        row, shapes = parcel_areas(v.GetLayer(), polygon(10,20,50,40))
        self.assertEqual(row, [200,0,600,800])
        self.assertEqual(sum(x.GetArea() for x in shapes), 200)
        self.assertEqual(row[0]/row[3]*100, 25)  # not 33.3% of known area

    def test_holes_and_parts_preserved(self):
        geometry = polygon(0,0,40,40)
        geometry['coordinates'].append(polygon(10,10,30,30)['coordinates'][0])
        v = regions(self.raster([[4,4],[4,4]]), self.raster([[6,6],[6,6]]))
        row, shapes = parcel_areas(v.GetLayer(), geometry)
        self.assertEqual(row, [1200,0,1200,1200])
        self.assertEqual(sum(x.GetArea() for x in shapes), 1200)
        multi = {'type':'MultiPolygon','coordinates':[polygon(0,0,5,5)['coordinates'],polygon(30,30,40,40)['coordinates']]}
        self.assertEqual(parcel_areas(v.GetLayer(),multi)[0], [125,0,125,125])

    def test_water_both_dates_is_not_new(self):
        v = regions(self.raster([[6]]), self.raster([[6]]))
        row, shapes = parcel_areas(v.GetLayer(), polygon(0,20,20,40))
        self.assertEqual(row, [0,400,400,400]); self.assertFalse(shapes)

    def test_outside_is_unknown_and_small_parcels_are_not_lost(self):
        v = regions(self.raster([[4]]), self.raster([[6]]))
        self.assertEqual(parcel_areas(v.GetLayer(),polygon(-20,20,20,40))[0], [400,0,400,800])
        self.assertEqual(parcel_areas(v.GetLayer(),polygon(0,20,2,22))[0], [4,0,4,4])
        self.assertEqual(parcel_areas(v.GetLayer(),polygon(-20,20,-10,40))[0], [0,0,0,200])

    def test_no_observation_is_not_zero_water(self):
        v = regions(self.raster([[3]]), self.raster([[6]]))
        self.assertEqual(parcel_areas(v.GetLayer(),polygon(0,20,20,40))[0], [0,0,0,400])

    def test_invalid_class_and_grid_rejected(self):
        a=self.raster([[4]]); b=self.raster([[6]])
        b.SetGeoTransform((1,20,0,40,0,-20))
        with self.assertRaises(ValueError): regions(a,b)
        with self.assertRaises(ValueError): regions(a,self.raster([[12]]))


if __name__ == '__main__': unittest.main()
