import json
from pathlib import Path
import tempfile
import unittest
try:
    import numpy as np
    from osgeo import gdal
    from field_water import add_candidates, assess
    from spectral_quality import normalized_difference
    from sentinel_contract import compatible, upgradeable, RAW_BANDS
    from sentinel_pipeline import process_rasters
    from upgrade_sentinel_products import upgrade
    import test_sentinel_web as fixtures
except ImportError:
    raise unittest.SkipTest('GDAL and NumPy required')


class FieldWaterTests(unittest.TestCase):
    def test_baseline_water_unknown_and_dark_candidate_remain_distinct(self):
        base=np.array([[1,3,0,2,0]],dtype=np.uint8);flags=np.array([[0,4,0,32,0]],dtype=np.uint8)
        a=lambda values:np.array([values],dtype=float)
        sw=a([.01,.01,.02,.02,.2]);before=sw.copy()
        result,quality=add_candidates(base,flags,a([.02,.02,.05,.3,.3]),a([.03]*5),a([-.1]*5),sw,a([-.1,.4,.4,.4,.4]))
        self.assertEqual(result.tolist(),[[1,3,4,2,2]])
        self.assertEqual(quality[0,2],64);self.assertEqual(quality[0,3],32)
        np.testing.assert_array_equal(sw,before);self.assertEqual(base.tolist(),[[1,3,0,2,0]])

    def test_invalid_guidance_never_creates_candidates(self):
        base=np.zeros((1,4),np.uint8);v=np.full((1,4),.03)
        result,_=add_candidates(base,base,v,v,np.array([[-9999,-.1,-.1,-.1]]),v,
            np.array([[.5,-9999,np.nan,-.1]]))
        self.assertFalse(result.any())

    def test_small_scene_fallback_preserves_base_water(self):
        g=np.full((2,2),.08);n=np.full((2,2),.03);q=np.ones((2,2),bool)
        water,flags,meta=assess(g,n,np.array([[.02]]),normalized_difference(g,n,q),np.array([[.6]]),
             np.full((2,2),.1),np.array([[5]]),np.array([[.04]]))
        self.assertTrue((water==1).all());self.assertEqual(meta['status'],'baseline_fallback')

    def legacy(self,root):
        current=root/'fixture';current.mkdir();manifest=fixtures.PublicationTests().fixture(current)
        raw={key:gdal.Open(str(current/f'raw_{key}.tif')) for key in RAW_BANDS}
        source=root/'v2'
        process_rasters(raw,manifest['source_item'],manifest['aoi'],source,{},legacy_water=True)
        return source

    def test_migration_preserves_dn_and_indices_and_is_versioned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.legacy(root);old=json.loads((source/'manifest.json').read_text())
            self.assertTrue(upgradeable(old));self.assertFalse(compatible(old))
            result=upgrade(source,root/'v3');self.assertTrue(compatible(result));self.assertFalse(upgradeable(result))
            self.assertEqual(result['source_item']['id'],old['source_item']['id'])
            for key in RAW_BANDS:self.assertEqual((source/f'raw_{key}.tif').read_bytes(),(root/'v3'/f'raw_{key}.tif').read_bytes())
            for key in ['NDWI','MNDWI','NDVI']:
                np.testing.assert_array_equal(gdal.Open(str(source/(key+'.tif'))).ReadAsArray(),gdal.Open(str(root/'v3'/(key+'.tif'))).ReadAsArray())
            upgrade(root/'v3',root/'copy')
            self.assertEqual((root/'v3/WATER.tif').read_bytes(),(root/'copy/WATER.tif').read_bytes())

    def test_migration_rejects_corrupt_raw_and_preserves_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.legacy(root)
            with self.assertRaisesRegex(ValueError,'preserve'):upgrade(source,source)
            with (source/'raw_B03_10m.tif').open('ab') as stream:stream.write(b'corrupted')
            with self.assertRaisesRegex(ValueError,'checksum'):upgrade(source,root/'v3')


if __name__=='__main__':unittest.main()
