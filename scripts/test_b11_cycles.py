import unittest
from pathlib import Path
try:
    import numpy as np
    from b11_cycles import fit_reconstruct, errors, area, inventory
    from parcel_grid import mean_2x2, repeat_2x2
    from spectral_quality import normalized_difference
    import test_parcel_ndvi as parcel_fixture
except ImportError:
    raise unittest.SkipTest('GDAL/NumPy required')


class B11CyclesTests(unittest.TestCase):
    def fixture(self):
        guide=np.random.default_rng(21).uniform(-.8,.8,(40,40))
        swir=.12+.06*mean_2x2(guide)
        train=np.ones((20,20),bool); train[5:10,5:10]=False
        return guide,swir,train

    def test_heldout_truth_does_not_fit_coefficients(self):
        guide,swir,train=self.fixture()
        first,meta=fit_reconstruct(swir,[guide],train,np.ones_like(train))
        altered=swir.copy(); altered[~train]+=.2
        second,other=fit_reconstruct(altered,[guide],train,np.ones_like(train))
        self.assertEqual(meta,other)
        np.testing.assert_allclose(mean_2x2(first),swir,atol=1e-12)
        np.testing.assert_allclose(mean_2x2(second),altered,atol=1e-12)

    def test_reproducibility_and_missing_block(self):
        guide,swir,train=self.fixture(); guide[0,0]=-9999
        a,m=fit_reconstruct(swir,[guide],train,np.ones_like(train))
        b,n=fit_reconstruct(swir,[guide],train,np.ones_like(train))
        np.testing.assert_array_equal(a,b); self.assertEqual(m,n)
        self.assertTrue(np.isnan(a[:2,:2]).all())
        self.assertGreaterEqual(np.nanmin(a),-1e-12)

    def test_compute_guide_after_reflectance_aggregation(self):
        g=np.array([[.1,.2],[.3,.4]]); n=np.array([[.05,.5],[.1,.8]])
        a=mean_2x2(normalized_difference(g,n,np.ones((2,2),bool)))
        b=normalized_difference(mean_2x2(g),mean_2x2(n),np.ones((1,1),bool))
        self.assertFalse(np.allclose(a,b))

    def test_exact_fractional_area_and_common_support(self):
        ds=parcel_fixture.ParcelNdviTests().raster([[1,1],[1,1]])
        ds.SetGeoTransform((0,10,0,20,0,-10))
        geom={'type':'Polygon','coordinates':[[[5,0],[15,0],[15,20],[5,20],[5,0]]]}
        self.assertEqual(area(ds,geom,np.array([[1,0],[1,0]],bool)),100)
        self.assertEqual(area(ds,geom,np.zeros((2,2),bool)),0)

    def test_metrics_empty_and_bias(self):
        self.assertIsNone(errors(np.ones((2,2)),np.zeros((2,2)),np.zeros((2,2),bool))['rmse'])
        self.assertEqual(errors(np.ones((2,2)),np.zeros((2,2)),np.ones((2,2),bool))['bias'],1)

    def test_references_preserve_date_and_spatial_uncertainty(self):
        root=Path(__file__).resolve().parents[1]
        products=[Path('S2A_MSIL2A_'+day+'T110121_N0513_R094_T30TUK_20261031T173605')
                  for day in ['20230816','20261014','20261031']]
        cases={(c['zone'],c['date']):c for c in inventory(root,products)['cases']}
        self.assertEqual(cases['45137A00700014','2026-10-31']['observed_class'],'water_present_somewhere')
        self.assertEqual(cases['45137A00700014','2026-10-14']['observed_class'],'unlabelled_acquisition_context')
        self.assertEqual(cases['45137A03300074','2023-08-16']['observed_class'],'unlabelled_acquisition_context')
        self.assertIn('invalid_ndwi',cases['45137A00900059','2023-08-16']['observed_class'])
        self.assertEqual(cases['45137A01200001','2026-10-31']['observed_class'],'reported_false_positive_on_buildings_and_solar_panels')


if __name__=='__main__': unittest.main()
