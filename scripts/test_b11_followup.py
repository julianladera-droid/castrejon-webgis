import hashlib
import csv
import json
from pathlib import Path
import unittest
try:
    import numpy as np
    from b11_followup import guides, detector, ahash
except ImportError:
    raise unittest.SkipTest('GDAL/NumPy required')

ROOT=Path(__file__).resolve().parents[1]


class FollowupTests(unittest.TestCase):
    def test_negative_child_can_have_positive_aggregate(self):
        a=np.array([[-.02,.08],[.08,.08]]);b=np.full((2,2),.02);q=np.ones((1,1),bool)
        self.assertTrue(np.isfinite(guides(a,b,q,'aggregate',.01)).all())
        self.assertTrue(np.isnan(guides(a,b,q,'all_children',.01)).all())
        self.assertEqual(a[0,0],-.02)

    def test_nodata_is_not_a_negative_observation(self):
        a=np.array([[np.nan,.08],[.08,.08]]);b=np.full((2,2),.02)
        for policy in ['aggregate','all_children']:
            self.assertTrue(np.isnan(guides(a,b,np.ones((1,1),bool),policy,.01)).all())

    def test_child_low_signal_and_shared_guide_values(self):
        a=np.array([[.001,.08],[.08,.08]]);b=np.full((2,2),.001);q=np.ones((1,1),bool)
        self.assertTrue(np.isfinite(guides(a,b,q,'aggregate',.01)).all())
        self.assertTrue(np.isnan(guides(a,b,q,'all_children',.01)).all())
        np.testing.assert_array_equal(guides(a,b,q,'aggregate',0),guides(a,b,q,'all_children',0))

    def test_detector_quality_and_reconstruction_immutable(self):
        a=lambda x:np.full((2,2),x,dtype=float)
        swir=a(.03);before=ahash(swir);scl=np.array([[4,8],[4,4]])
        ndwi=a(-.1);ndwi[1,0]=-9999
        args=(a(.04),a(.05),swir,a(.04),ndwi,a(.2),a(.1),scl)
        current=detector(*args,'current');h1=detector(*args,'H1_residual');h2=detector(*args,'H2_strict')
        self.assertEqual(current[0,0],2);self.assertEqual(h1[0,0],4);self.assertEqual(h2[0,0],1)
        self.assertEqual(h2[0,1],3);self.assertEqual(h2[1,0],3);self.assertEqual(before,ahash(swir))

    def test_no_global_or_and_no_loss_of_existing_water(self):
        a=lambda x:np.full((1,1),x,dtype=float)
        # Positive MNDWI alone does not overcome bright NIR/SWIR.
        args=(a(.2),a(.3),a(.2),a(.3),a(-.2),a(.3),a(.5),a(4))
        self.assertEqual(detector(*args,'H1_residual')[0,0],2)
        args=(a(.1),a(.01),a(.01),a(.01),a(.8),a(.8),a(0),a(6))
        for method in ['current','H1_residual','H2_strict']:self.assertEqual(detector(*args,method)[0,0],1)

    def test_reservation_scope_metadata(self):
        data=json.loads((ROOT/'docs/b11-cycles/inventory.json').read_text())
        for c in data['cases']:
            self.assertNotIn('reconstruction_role',c)
            self.assertIn('no spatial holdout',c['experiment_roles']['full_20_to_10'])
            self.assertIn('80m',c['experiment_roles']['reduced_40_to_20'])
            self.assertIn('development',c['experiment_roles']['detector_followup'])

    def test_previous_results_preserved(self):
        baseline=json.loads((ROOT/'docs/b11-followup/preserved-results.json').read_text())
        for name,expected in baseline['canonical_sha256'].items():
            path=ROOT/'docs/b11-cycles'/name
            payload=path.read_bytes() if path.suffix=='.jpg' else path.read_text(encoding='utf-8').encode('utf-8')
            self.assertEqual(hashlib.sha256(payload).hexdigest(),expected,name)
        before=json.loads((ROOT/'docs/b11-followup/previous-frozen.json').read_text())
        after=json.loads((ROOT/'docs/b11-cycles/frozen.json').read_text())
        for b,a in zip(before,after):
            a.pop('fit_scope_correction');self.assertEqual(a,b)

    def test_safe_separation_and_fixed_masks(self):
        records=json.loads((ROOT/'docs/b11-followup/frozen.json').read_text())
        ids=[r['product'] for r in records]
        self.assertEqual(len(ids),len(set(ids)))
        august=[r for r in records if '20230816T' in r['product']]
        self.assertEqual({r['product'].split('_')[3] for r in august},{'N0509','N0510'})
        self.assertNotEqual(august[0]['arrays_sha256']['D'],august[1]['arrays_sha256']['D'])
        previous=json.loads((ROOT/'docs/b11-followup/previous-frozen.json').read_text())
        for old in previous:
            new=next(r for r in records if r['product']==old['product'])
            for k in ['D','E']:self.assertEqual(old['guidance'][k],new['coefficients'][k])
        with (ROOT/'docs/b11-followup/detectors.csv').open() as stream:rows=list(csv.DictReader(stream))
        supports={}
        for row in rows:
            if row['detector']=='gate_diagnostic':continue
            key=row['product'],row['zone']
            common=float(row['common_m2'])
            self.assertLessEqual(common,float(row['own_m2'])+.001)
            if key in supports:self.assertEqual(common,supports[key])
            supports[key]=common


if __name__=='__main__':unittest.main()
