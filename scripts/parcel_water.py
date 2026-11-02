"""Current optical surface water and optional transitions, with exact metric areas."""
import hashlib
import json
import numpy as np
from osgeo import gdal, ogr, osr
from parcel_grid import require_same_grid
from sentinel_contract import WATER_METHOD

METHOD = WATER_METHOD
MIN_VALID_PERCENT = 80
COLUMNS = ['water_m2', 'ambiguous_m2', 'unknown_m2', 'evaluated_m2', 'parcel_m2',
           'appeared_m2', 'both_observations_m2', 'disappeared_m2', 'common_evaluated_m2', 'residual_m2']


def transitions(a, b):
    """0 unchanged dry, 1 appearance, 2 both, 3 disappearance, 4 incomparable."""
    common = np.isin(a, [0, 1]) & np.isin(b, [0, 1])
    values = np.full(b.shape, 4, dtype=np.uint8)
    values[common] = 0
    values[common & (a == 0) & (b == 1)] = 1
    values[common & (a == 1) & (b == 1)] = 2
    values[common & (a == 1) & (b == 0)] = 3
    return values


def regions(reference, values=None):
    """Polygonize full cells, including unknown; all clipping happens in EPSG:25830."""
    gt = reference.GetGeoTransform()
    if (reference.GetSpatialRef().GetAuthorityCode(None) != '25830' or
            gt[1] not in (10, 20) or (gt[2], gt[4], gt[5]) != (0, 0, -gt[1])):
        raise ValueError('Expected original metric grid')
    values = reference.ReadAsArray() if values is None else values
    if values.shape != (reference.RasterYSize, reference.RasterXSize) or not np.all(np.isin(values, range(5))):
        raise ValueError('Invalid water classes')
    ds = gdal.GetDriverByName('MEM').Create('', reference.RasterXSize, reference.RasterYSize, 1, gdal.GDT_Byte)
    ds.SetProjection(reference.GetProjection()); ds.SetGeoTransform(gt)
    ds.GetRasterBand(1).WriteArray(values)
    vector = ogr.GetDriverByName('Memory').CreateDataSource('')
    layer = vector.CreateLayer('regions', reference.GetSpatialRef(), ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn('class', ogr.OFTInteger))
    gdal.Polygonize(ds.GetRasterBand(1), None, layer, 0, [])
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
    areas, shapes = [0.] * 5, []
    layer.SetSpatialFilter(parcel); layer.ResetReading()
    for feature in layer:
        intersection = polygon_parts(parcel.Intersection(feature.GetGeometryRef()))
        area = intersection.GetArea()
        if area <= 0:
            continue
        kind = feature.GetField('class')
        areas[kind] += area
        if kind in (1, 2, 3, 4):
            shapes.append((kind, intersection))
    layer.SetSpatialFilter(None)
    if sum(areas) > total + .01:
        raise ValueError('Overlapping classified regions')
    missing = max(0., total - sum(areas))
    if missing > .001:
        xmin, xmax, ymin, ymax = layer.GetExtent()
        extent = ogr.CreateGeometryFromWkt(f'POLYGON(({xmin} {ymin},{xmax} {ymin},{xmax} {ymax},{xmin} {ymax},{xmin} {ymin}))')
        outside = polygon_parts(parcel.Difference(extent))
        if outside.GetArea() > .001:
            shapes.append((3, outside))
    return areas, total, missing, shapes


def build_water(after, entry, master_path, destination, before=None, previous=None):
    current = gdal.Open(str(after/'WATER.tif'))
    if not np.all(np.isin(current.ReadAsArray(), range(5))):
        raise ValueError('Invalid current water classes')
    vector = regions(current)
    change = None
    if before is not None and previous is not None:
        old = gdal.Open(str(before/'WATER.tif'))
        if previous['datetime'] >= entry['datetime']:
            raise ValueError('Water reference must precede observation')
        try:
            require_same_grid(old, current)
        except ValueError:
            previous = None
        else:
            change = regions(current, transitions(old.ReadAsArray(), current.ReadAsArray()))
    master_bytes = master_path.read_bytes()
    master = json.loads(master_bytes)
    if master['crs'] != 'EPSG:25830' or master['web_sha256'] != entry['parcel_indices']['parcel_web_sha256']:
        raise ValueError('Water parcel provenance mismatch')
    source = osr.SpatialReference(); source.ImportFromEPSG(25830)
    target = osr.SpatialReference(); target.ImportFromEPSG(4326)
    for crs in (source, target): crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(source, target)
    table, features = {}, []
    for feature in master['features']:
        ref = feature['refcat']
        areas, total, missing, shapes = parcel_areas(vector.GetLayer(), feature['geometry'])
        row = [areas[1], areas[2], areas[3] + missing, areas[0] + areas[1], total]
        if change is not None:
            temporal, _, _, _ = parcel_areas(change.GetLayer(), feature['geometry'])
            row += [temporal[1], temporal[2], temporal[3], sum(temporal[:4])]
        else:
            row += [None] * 4
        row += [areas[4]]
        table[ref] = [round(v, 3) if v is not None else None for v in row]
        for kind, shape in shapes:
            # GEOS can produce sub-mm² numerical slivers along shared edges.
            # Keep exact area accounting above, but never emit a category rounded
            # to zero in the compact table (the client checks this invariant).
            if table[ref][9 if kind==4 else kind-1] <= 0:
                continue
            shape.Transform(transform)
            features.append({'type': 'Feature', 'properties': {'refcat': ref, 'class': kind},
                             'geometry': json.loads(shape.ExportToJson())})
    data = {'version': 3, 'method': METHOD, 'status': 'field_visit_estimate', 'resolution_m': 10,
        'support_resolution_m': 20, 'min_valid_percent': MIN_VALID_PERCENT,
        'area_method': 'fractional_cell_intersection_25830',
        'observation': {k: entry[k] for k in ('id', 'datetime')},
        'previous': {k: previous[k] for k in ('id', 'datetime')} if change is not None else None,
        'source_sha256': entry['water_raster_sha256'],
        'previous_sha256': previous['water_raster_sha256'] if change is not None else None,
        'parcel_web_sha256': master['web_sha256'],
        'master_sha256': hashlib.sha256(master_bytes).hexdigest(), 'columns': COLUMNS, 'parcels': table}
    descriptor = {'method': METHOD, 'parcel_web_sha256': master['web_sha256']}
    for key, filename, payload in [('table', 'parcel-water.json', data),
            ('zones', 'water-zones.geojson', {'type': 'FeatureCollection', 'features': features})]:
        content = (json.dumps(payload, separators=(',', ':'), allow_nan=False) + '\n').encode()
        (destination/filename).write_bytes(content)
        descriptor[key] = {'path': f"sentinel/{entry['id']}/{filename}",
                           'sha256': hashlib.sha256(content).hexdigest()}
    print(f"Water {entry['datetime']}: {len(table)} parcels, {len(features)} polygons")
    return descriptor
