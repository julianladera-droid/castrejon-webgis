"""Reusable metric pixel-centre masks and validity for parcel analyses.

Areas from these masks describe sampled cells, not exact clipped cadastral area.
Future water percentages must intersect boundary cells with parcel geometry.
"""
import json
import numpy as np
from osgeo import gdal, ogr


def sample_parcel(ds, geometry, resolution):
    gt = ds.GetGeoTransform()
    if (ds.GetSpatialRef().GetAuthorityCode(None) != '25830' or
            (gt[1], gt[2], gt[4], gt[5]) != (resolution, 0, 0, -resolution)):
        raise ValueError('Unexpected original metric grid')
    geom = ogr.CreateGeometryFromJson(json.dumps(geometry))
    if (geom is None or geom.IsEmpty() or not geom.IsValid() or
            ogr.GT_Flatten(geom.GetGeometryType()) not in (ogr.wkbPolygon, ogr.wkbMultiPolygon)):
        raise ValueError('Invalid metric parcel geometry')
    xmin, xmax, ymin, ymax = geom.GetEnvelope()
    c0, c1 = int(np.floor((xmin-gt[0])/resolution)), int(np.ceil((xmax-gt[0])/resolution))
    r0, r1 = int(np.floor((gt[3]-ymax)/resolution)), int(np.ceil((gt[3]-ymin)/resolution))
    width, height = max(1, c1-c0), max(1, r1-r0)
    if width*height > 4_000_000:
        raise ValueError('Unexpected parcel extent')
    mask = gdal.GetDriverByName('MEM').Create('', width, height, 1, gdal.GDT_Byte)
    mask.SetGeoTransform((gt[0]+c0*resolution, resolution, 0, gt[3]-r0*resolution, 0, -resolution))
    mask.SetProjection(ds.GetProjection())
    vector = ogr.GetDriverByName('Memory').CreateDataSource('')
    layer = vector.CreateLayer('parcel', ds.GetSpatialRef(), ogr.wkbUnknown)
    feature = ogr.Feature(layer.GetLayerDefn()); feature.SetGeometry(geom); layer.CreateFeature(feature)
    gdal.RasterizeLayer(mask, [1], layer, burn_values=[1])
    inside = mask.ReadAsArray() == 1
    total = int(inside.sum())
    x0, x1 = max(c0, 0), min(c0+width, ds.RasterXSize)
    y0, y1 = max(r0, 0), min(r0+height, ds.RasterYSize)
    values = np.full((height, width), np.nan, dtype=np.float64)
    if x1 > x0 and y1 > y0:
        values[y0-r0:y1-r0, x0-c0:x1-c0] = ds.GetRasterBand(1).ReadAsArray(x0,y0,x1-x0,y1-y0)
    return values, inside


def valid_pixels(ds, values, inside, valid_range):
    valid = inside & np.isfinite(values)
    nodata = ds.GetRasterBand(1).GetNoDataValue()
    if nodata is not None:
        valid &= values != nodata
    if valid_range is not None:
        valid &= (values >= valid_range[0]) & (values <= valid_range[1])
    return valid


def require_same_grid(a, b):
    if (a.GetSpatialRef().GetAuthorityCode(None) != '25830' or
            not a.GetSpatialRef().IsSame(b.GetSpatialRef()) or
            a.GetGeoTransform() != b.GetGeoTransform() or
            (a.RasterXSize,a.RasterYSize) != (b.RasterXSize,b.RasterYSize)):
        raise ValueError('Comparison requires identical original metric grids')
