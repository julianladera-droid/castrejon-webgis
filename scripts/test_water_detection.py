import unittest
try:
    import numpy as np
    from osgeo import gdal
    from water_detection import detect
    from spectral_quality import normalized_difference, interpretable
    from sentinel_pipeline import reflectance
    from parcel_grid import mean_2x2, repeat_2x2, require_nested_grid
    from water_sharpening import guided_b11
    from test_parcel_ndvi import ParcelNdviTests
except ImportError:
    raise unittest.SkipTest('GDAL/NumPy required in geospatial CI')


class WaterDetectionTests(unittest.TestCase):
    def test_soil_scl_and_positive_ndvi_can_be_water(self):
        g, n, sw, red = [np.array([[x]]) for x in (.08, .03, .02, .02)]
        q = np.array([[True]])
        ndwi = normalized_difference(g, n, q)
        mndwi = normalized_difference(g, sw, q)
        ndvi = normalized_difference(n, red, q)
        self.assertGreater(ndvi.item(), 0)
        self.assertEqual(detect(g, n, sw, ndwi, mndwi, ndvi, np.array([[5]]))[0].item(), 1)

    def test_negative_low_signal_and_masked_ratios_never_water(self):
        a = np.array([[-.001, .002, .05, np.nan, .1]])
        b = np.array([[.0011, .002, .03, .02, .03]])
        scl = np.array([[5, 6, 3, 5, 9]])
        index = normalized_difference(a, b, np.isin(scl, [4, 5, 6]))
        self.assertFalse(interpretable(index).any())
        water, flags = detect(a, b, b, index, index, index, scl)
        self.assertEqual(water.tolist(), [[3]*5])
        self.assertTrue(flags[0,0] & 4)
        self.assertTrue(flags[0,1] & 8)
        self.assertTrue(flags[0,2] & 1)
        self.assertTrue(flags[0,3] & 2)

    def test_disagreement_and_darkness_are_ambiguous(self):
        g, n, s, r = [np.array([[x]]) for x in (.03, .04, .05, .03)]
        q = np.array([[True]])
        result, flags = detect(g,n,s,normalized_difference(g,n,q),normalized_difference(g,s,q),
                                normalized_difference(n,r,q),np.array([[5]]))
        self.assertEqual(result.item(), 2)
        self.assertTrue(flags.item() & 32)

    def test_scale_offset_nodata_and_negative_values_preserved(self):
        ds = ParcelNdviTests().raster([[0, 999, 2000, -9999]])
        ds.GetRasterBand(1).SetScale(.0001); ds.GetRasterBand(1).SetOffset(-.1)
        values = reflectance(ds, {'raster:scale': .0001, 'raster:offset': -.1, 'nodata': 0})
        self.assertTrue(np.isnan(values[0,0]) and np.isnan(values[0,3]))
        self.assertAlmostEqual(values[0,1], -.0001)
        self.assertAlmostEqual(values[0,2], .1)  # GDAL scale is not applied twice.

    def test_mean_alignment_and_incomplete_blocks(self):
        values = np.arange(16.).reshape(4,4)
        self.assertEqual(mean_2x2(values).tolist(), [[2.5,4.5],[10.5,12.5]])
        values[0,0] = np.nan
        self.assertTrue(np.isnan(mean_2x2(values)[0,0]))
        f = ParcelNdviTests().raster(np.ones((4,4)))
        c = ParcelNdviTests().raster(np.ones((2,2)))
        f.SetGeoTransform((0,10,0,40,0,-10)); c.SetGeoTransform((0,20,0,40,0,-20))
        require_nested_grid(f,c)
        c.SetGeoTransform((10,20,0,40,0,-20))
        with self.assertRaises(ValueError): require_nested_grid(f,c)

    def test_experiment_preserves_each_original_block_and_uses_own_guide(self):
        rng = np.random.default_rng(4)
        guide = rng.uniform(-.8,.8,(40,40))
        swir = .1-.05*mean_2x2(guide)
        result, meta = guided_b11(swir,guide)
        np.testing.assert_allclose(mean_2x2(result),swir,atol=1e-12)
        self.assertLess(meta['max_abs_reaggregation_error'],1e-12)
        self.assertFalse(np.allclose(result,repeat_2x2(swir)))
        changed, _ = guided_b11(swir,np.flip(guide,axis=1))
        self.assertFalse(np.allclose(result,changed))


if __name__ == '__main__': unittest.main()
