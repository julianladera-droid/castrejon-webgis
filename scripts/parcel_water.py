"""Exploratory new surface water, not confirmed soil waterlogging.

All area calculations intersect native 20 m cells with metric parcel geometries.
Fractional borders improve geometric accounting, not physical sensor resolution.
"""
import hashlib
import json
import numpy as np
from osgeo import gdal, ogr, osr
from parcel_grid import require_same_grid

METHOD = 'scl_new_surface_water_v1'
MIN_VALID_PERCENT = 80


def classify(a, b):
    """0: evaluated non-new water; 1: new water; 2: water both dates; 3: unknown."""
    valid = np.isin(a, [4, 5, 6]) & np.isin(b, [4, 5, 6])
    result = np.full(a.shape, 3, dtype=np.uint8)
    result[valid] = 0
    result[(b == 6) & np.isin(a, [4, 5])] = 1
    result[(a == 6) & (b == 6)] = 2
    return result


def regions(a, b):
    require_same_grid(a, b)
    if (a.GetGeoTransform()[1:3] != (20, 0) or a.GetGeoTransform()[4:] != (0, -20)):
        raise ValueError('Expected native 20m SCL grid')
    arrays = [ds.ReadAsArray() for ds in (a, b)]
    if any(not np.all(np.isin(v, [-9999, *range(12)])) for v in arrays):
        raise ValueError('Invalid scene classification')
    values = classify(*arrays)
    ds = gdal.GetDriverByName('MEM').Create('', a.RasterXSize, a.RasterYSize, 2, gdal.GDT_Byte)
    ds.SetProjection(a.GetProjection()); ds.SetGeoTransform(a.GetGeoTransform())
    ds.GetRasterBand(1).WriteArray(values)
    ds.GetRasterBand(2).WriteArray(values != 3)
    vector = ogr.GetDriverByName('Memory').CreateDataSource('')
    layer = vector.CreateLayer('regions', a.GetSpatialRef(), ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn('class', ogr.OFTInteger))
    gdal.Polygonize(ds.GetRasterBand(1), ds.GetRasterBand(2), layer, 0, [])
    return vector


def polygon_parts(geometry):
    result = ogr.Geometry(ogr.wkbMultiPolygon)
    def add(g):
        if ogr.GT_Flatten(g.GetGeometryType()) == ogr.wkbPolygon:
            result.AddGeometry(g)
        else:
            for child in g:
                add(child)
    add(geometry)
    return result


def parcel_areas(layer, geometry):
    parcel = ogr.CreateGeometryFromJson(json.dumps(geometry))
    if (not parcel or parcel.IsEmpty() or not parcel.IsValid() or
            ogr.GT_Flatten(parcel.GetGeometryType()) not in (ogr.wkbPolygon, ogr.wkbMultiPolygon)):
        raise ValueError('Invalid parcel geometry')
    total = parcel.GetArea()
    if total <= 0:
        raise ValueError('Empty parcel area')
    areas = [0., 0., 0.]
    new_geometries = []
    layer.SetSpatialFilter(parcel); layer.ResetReading()
    for feature in layer:
        intersection = polygon_parts(parcel.Intersection(feature.GetGeometryRef()))
        area = intersection.GetArea()
        if area <= 0:
            continue
        kind = feature.GetField('class')
        areas[kind] += area
        if kind == 1:
            new_geometries.append(intersection)
    layer.SetSpatialFilter(None)
    known = sum(areas)
    if known > total + .01:
        raise ValueError('Overlapping classified regions')
    return [areas[1], areas[2], min(known, total), total], new_geometries


def build_water(before, after, entries, master_path, destination, pair_id):
    a, b = (gdal.Open(str(folder / 'SCL.tif')) for folder in (before, after))
    vector = regions(a, b)
    master_bytes = master_path.read_bytes()
    master = json.loads(master_bytes)
    if master['crs'] != 'EPSG:25830' or master['web_sha256'] != entries[0]['parcel_indices']['parcel_web_sha256']:
        raise ValueError('Water parcel provenance mismatch')
    if entries[0]['datetime'] >= entries[1]['datetime']:
        raise ValueError('Water assessment requires chronological dates')
    source = osr.SpatialReference(); source.ImportFromEPSG(25830)
    target = osr.SpatialReference(); target.ImportFromEPSG(4326)
    for crs in (source, target): crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(source, target)
    table, features = {}, []
    for feature in master['features']:
        ref = feature['refcat']
        row, shapes = parcel_areas(vector.GetLayer(), feature['geometry'])
        table[ref] = [round(value, 3) for value in row]
        for shape in shapes:
            shape.Transform(transform)
            features.append({'type': 'Feature', 'properties': {'refcat': ref},
                             'geometry': json.loads(shape.ExportToJson())})
    data = {'version': 1, 'method': METHOD, 'status': 'exploratory', 'resolution_m': 20,
        'min_valid_percent': MIN_VALID_PERCENT, 'area_method': 'fractional_cell_intersection_25830',
        'a': {k: entries[0][k] for k in ('id', 'datetime')},
        'b': {k: entries[1][k] for k in ('id', 'datetime')},
        'scl_sha256': [e['quality_mask']['sha256'] for e in entries],
        'parcel_web_sha256': master['web_sha256'],
        'master_sha256': hashlib.sha256(master_bytes).hexdigest(),
        'columns': ['new_water_m2', 'water_both_dates_m2', 'evaluated_m2', 'parcel_m2'],
        'parcels': table}
    descriptor = {'method': METHOD, 'parcel_web_sha256': master['web_sha256']}
    for key, filename, payload in [('table', 'parcel-water.json', data),
            ('zones', 'water-zones.geojson', {'type': 'FeatureCollection', 'features': features})]:
        content = (json.dumps(payload, separators=(',', ':'), allow_nan=False) + '\n').encode()
        (destination / filename).write_bytes(content)
        descriptor[key] = {'path': f'sentinel/{pair_id}/{filename}',
                           'sha256': hashlib.sha256(content).hexdigest()}
    print(f'Water estimate: {len(table)} parcels, {len(features)} clipped new-water polygons')
    return descriptor
