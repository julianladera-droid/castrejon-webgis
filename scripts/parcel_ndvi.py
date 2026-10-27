"""Build parcel NDVI summaries on the original 10 m metric grid, never in browser."""
import hashlib
import json
from pathlib import Path
import numpy as np
from osgeo import gdal, ogr, osr

MIN_VALID_PERCENT = 80


def summarize(ds, geometry):
    """Pixel-centre arithmetic mean; holes excluded, outside raster counted invalid."""
    gt = ds.GetGeoTransform()
    if (ds.GetSpatialRef().GetAuthorityCode(None) != '25830' or
            (gt[1], gt[2], gt[4], gt[5]) != (10.0, 0.0, 0.0, -10.0)):
        raise ValueError('Expected north-up 10 m EPSG:25830 grid')
    geom = ogr.CreateGeometryFromJson(json.dumps(geometry))
    if (geom is None or geom.IsEmpty() or not geom.IsValid() or
            ogr.GT_Flatten(geom.GetGeometryType()) not in (ogr.wkbPolygon, ogr.wkbMultiPolygon)):
        raise ValueError('Invalid metric parcel geometry')
    xmin, xmax, ymin, ymax = geom.GetEnvelope()
    c0, c1 = int(np.floor((xmin-gt[0])/10)), int(np.ceil((xmax-gt[0])/10))
    r0, r1 = int(np.floor((gt[3]-ymax)/10)), int(np.ceil((gt[3]-ymin)/10))
    width, height = max(1, c1-c0), max(1, r1-r0)
    if width*height > 4_000_000:
        raise ValueError('Unexpected parcel extent')
    mask = gdal.GetDriverByName('MEM').Create('', width, height, 1, gdal.GDT_Byte)
    mask.SetGeoTransform((gt[0]+c0*10, 10, 0, gt[3]-r0*10, 0, -10))
    mask.SetProjection(ds.GetProjection())
    vector = ogr.GetDriverByName('Memory').CreateDataSource('')
    layer = vector.CreateLayer('parcel', ds.GetSpatialRef(), ogr.wkbUnknown)
    feature = ogr.Feature(layer.GetLayerDefn()); feature.SetGeometry(geom); layer.CreateFeature(feature)
    gdal.RasterizeLayer(mask, [1], layer, burn_values=[1])
    inside = mask.ReadAsArray() == 1
    total = int(inside.sum())
    x0, x1 = max(c0, 0), min(c0+width, ds.RasterXSize)
    y0, y1 = max(r0, 0), min(r0+height, ds.RasterYSize)
    valid_count = 0; mean = None
    if x1 > x0 and y1 > y0:
        values = ds.GetRasterBand(1).ReadAsArray(x0, y0, x1-x0, y1-y0)
        selected = inside[y0-r0:y1-r0, x0-c0:x1-c0]
        valid = selected & np.isfinite(values) & (values >= -1) & (values <= 1)
        nodata = ds.GetRasterBand(1).GetNoDataValue()
        if nodata is not None: valid &= values != nodata
        valid_count = int(valid.sum())
        if total and valid_count/total*100 >= MIN_VALID_PERCENT:
            mean = round(float(np.mean(values[valid], dtype=np.float64)), 4)
    percent = round(valid_count/total*100, 2) if total else 0
    return {'mean': mean, 'valid_pixels': valid_count, 'total_pixels': total,
            'valid_percent': percent,
            'status': 'ok' if mean is not None else 'no_pixels' if not total else 'insufficient'}


def build_parcel_ndvi(ds, manifest, master_path, web_folder):
    master_bytes = master_path.read_bytes()
    master = json.loads(master_bytes)
    meta = json.loads((web_folder/'metadata.json').read_text(encoding='utf-8'))
    web_hash = hashlib.sha256((web_folder/'parcelas.geojson').read_bytes()).hexdigest()
    if (master['version'] != 1 or master['crs'] != 'EPSG:25830' or
            master['web_sha256'] != web_hash or meta['web_sha256'] != web_hash or
            master['source_sha256'] != meta['source_sha256']):
        raise ValueError('Metric parcel provenance mismatch')
    refs = {f['id'] for f in json.loads((web_folder/'parcelas.geojson').read_text(encoding='utf-8'))['features']}
    features = master['features']
    if len(features) != 919 or len(refs) != 919 or {f['refcat'] for f in features} != refs:
        raise ValueError('Metric parcel identity mismatch')
    return {'version': 1, 'acquisition_id': manifest['source_item']['id'],
            'datetime': manifest['source_item']['properties']['datetime'],
            'ndvi_sha256': manifest['indices']['NDVI']['sha256'],
            'parcel_web_sha256': web_hash, 'master_sha256': hashlib.sha256(master_bytes).hexdigest(),
            'resolution_m': 10, 'method': 'pixel_center_mean', 'min_valid_percent': MIN_VALID_PERCENT,
            'parcels': {f['refcat']: summarize(ds, f['geometry']) for f in features}}
