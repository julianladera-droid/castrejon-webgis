import hashlib
import json
from pathlib import Path
import tempfile
import unittest
try:
    import numpy as np
    from osgeo import gdal
    from parcel_water import regions, parcel_areas, transitions, build_water
    import test_parcel_ndvi as fixtures
    polygon = fixtures.polygon
except ImportError:
    if __name__ == '__main__': raise SystemExit('GDAL and NumPy required')
    raise unittest.SkipTest('GDAL required in geospatial CI')


class WaterTests(unittest.TestCase):
    def raster(self, values):
        ds = fixtures.ParcelNdviTests().raster(values)
        ds.SetGeoTransform((0,10,0,20,0,-10))
        return ds

    def test_temporal_comparison_only_uses_classifiable_cells(self):
        a=np.array([0,1,1,3,2,0]); b=np.array([1,1,0,1,1,3])
        self.assertEqual(transitions(a,b).tolist(), [1,2,3,4,4,4])
        self.assertEqual(int((b==1).sum()),4)  # previous unknown cannot erase current water

    def test_fractional_borders_holes_parts_and_outside(self):
        v=regions(self.raster([[1,0,3]]))
        areas,total,missing,shapes=parcel_areas(v.GetLayer(),polygon(5,10,25,20))
        self.assertEqual(areas[:4], [100,50,0,50])
        self.assertEqual(total,200); self.assertEqual(missing,0)
        self.assertEqual(areas[1]/total*100,25)
        v=regions(self.raster([[1,1],[1,1]]))
        geometry=polygon(0,0,20,20)
        geometry['coordinates'].append(polygon(5,5,15,15)['coordinates'][0])
        self.assertEqual(parcel_areas(v.GetLayer(),geometry)[0][1],300)
        multi={'type':'MultiPolygon','coordinates':[polygon(0,0,2,2)['coordinates'],polygon(15,15,20,20)['coordinates']]}
        self.assertEqual(parcel_areas(v.GetLayer(),multi)[0][1],29)
        areas,total,missing,shapes=parcel_areas(v.GetLayer(),polygon(-10,0,10,20))
        self.assertEqual((areas[1],total,missing),(200,400,200))
        self.assertAlmostEqual(sum(g.GetArea() for k,g in shapes if k==3),200)

    def test_current_water_without_previous_and_with_previous_unknown_or_water(self):
        for old in (None,3,1):
            with self.subTest(old=old), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); after=root/'after';after.mkdir();before=root/'before';before.mkdir()
                dest=root/'web';dest.mkdir();master=root/'master.json';webhash='a'*64
                master.write_text(json.dumps({'crs':'EPSG:25830','web_sha256':webhash,
                    'features':[{'refcat':'test','geometry':polygon(0,0,20,20)}]}))
                current=self.raster([[1,1],[1,1]])
                gdal.GetDriverByName('GTiff').CreateCopy(str(after/'WATER.tif'),current)
                entry={'id':'B','datetime':'2025-01-02T00:00:00Z','parcel_indices':{'parcel_web_sha256':webhash},'water_raster_sha256':'b'*64}
                previous=None
                if old is not None:
                    gdal.GetDriverByName('GTiff').CreateCopy(str(before/'WATER.tif'),self.raster([[old,old],[old,old]]))
                    previous={**entry,'id':'A','datetime':'2025-01-01T00:00:00Z'}
                build_water(after,entry,master,dest,before if previous else None,previous)
                result=json.loads((dest/'parcel-water.json').read_text());row=result['parcels']['test']
                self.assertEqual(row[:5],[400,0,0,400,400])
                self.assertEqual(row[6],None if old is None else 400 if old==1 else 0)
                zones=json.loads((dest/'water-zones.geojson').read_text())
                self.assertTrue(any(f['properties']['class']==1 for f in zones['features']))

    def test_ambiguity_and_unknown_are_separate(self):
        v=regions(self.raster([[1,2],[3,0]]))
        self.assertEqual(parcel_areas(v.GetLayer(),polygon(0,0,20,20))[0][:4],[100]*4)

    def test_submillimetre_edge_category_cannot_break_zone_table_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);master=root/'master.json';webhash='a'*64
            master.write_text(json.dumps({'crs':'EPSG:25830','web_sha256':webhash,
                'features':[{'refcat':'edge','geometry':polygon(9.999999,0,20,20)}]}))
            gdal.GetDriverByName('GTiff').CreateCopy(str(root/'WATER.tif'),self.raster([[3,1],[3,1]]))
            entry={'id':'B','datetime':'2025-01-02T00:00:00Z','parcel_indices':{'parcel_web_sha256':webhash},'water_raster_sha256':'b'*64}
            build_water(root,entry,master,root)
            table=json.loads((root/'parcel-water.json').read_text())
            zones=json.loads((root/'water-zones.geojson').read_text())
            self.assertEqual(table['parcels']['edge'][2],0)
            self.assertTrue(zones['features'])
            self.assertTrue(all(table['parcels'][f['properties']['refcat']][f['properties']['class']-1]>0 for f in zones['features']))

    def test_residual_area_is_separate_and_never_a_temporal_water_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);after=root/'after';after.mkdir();before=root/'before';before.mkdir()
            master=root/'master.json';webhash='a'*64
            master.write_text(json.dumps({'crs':'EPSG:25830','web_sha256':webhash,
                'features':[{'refcat':'mixed','geometry':polygon(5,0,20,20)}]}))
            gdal.GetDriverByName('GTiff').CreateCopy(str(after/'WATER.tif'),self.raster([[4,1],[2,3]]))
            gdal.GetDriverByName('GTiff').CreateCopy(str(before/'WATER.tif'),self.raster([[1,4],[0,0]]))
            entry={'id':'B','datetime':'2025-01-02T00:00:00Z','parcel_indices':{'parcel_web_sha256':webhash},'water_raster_sha256':'b'*64}
            previous={**entry,'id':'A','datetime':'2025-01-01T00:00:00Z'}
            build_water(after,entry,master,root,before,previous)
            data=json.loads((root/'parcel-water.json').read_text());row=data['parcels']['mixed']
            self.assertEqual(row,[100,50,100,100,300,0,0,0,0,50])
            self.assertEqual(sum(row[i] for i in [1,2,3,9]),row[4])
            zones=json.loads((root/'water-zones.geojson').read_text())
            self.assertEqual({f['properties']['class'] for f in zones['features']},{1,2,3,4})

    def test_invalid_class_and_nonmetric_grid_rejected(self):
        with self.assertRaises(ValueError): regions(self.raster([[12]]))
        a=self.raster([[1]]);a.SetGeoTransform((0,11,0,20,0,-10))
        with self.assertRaises(ValueError): regions(a)


if __name__ == '__main__': unittest.main()
