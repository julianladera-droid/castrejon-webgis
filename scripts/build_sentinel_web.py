"""Validate an Actions product and prepare same-origin static Sentinel layers."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from datetime import datetime, timezone

import numpy as np
from osgeo import gdal

PALETTES = {
    'NDVI': {'label': 'NDVI · vigor vegetal', 'range': [-1, 1],
             'colors': ['#314b91', '#d8c496', '#ffffbf', '#73b554', '#006837']},
    'EVI2': {'label': 'EVI2 · vegetación', 'range': [0, 1],
             'colors': ['#fff7bc', '#fec44f', '#78c679', '#238443', '#004529']},
    'NDMI': {'label': 'NDMI · humedad de la vegetación', 'range': [-1, 1],
             'colors': ['#8c510a', '#dfc27d', '#f5f5f5', '#80cdc1', '#01665e']},
}


def colorize(values, valid, spec):
    """Fixed scales; invalid values stay fully transparent, never zero-filled."""
    colors = np.array([[int(c[i:i+2], 16) for i in (1, 3, 5)] for c in spec['colors']])
    lo, hi = spec['range']
    position = np.clip((np.where(valid, values, lo)-lo)/(hi-lo), 0, 1)
    channels = [np.interp(position, np.linspace(0, 1, len(colors)), colors[:, i])
                for i in range(3)]
    return np.array(channels + [np.where(valid, 255, 0)], dtype=np.uint8)


def validate_product(folder):
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status') != 'quality_passed':
        raise ValueError('Product has not passed quality checks')
    item = manifest['source_item']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,150}', item['id']):
        raise ValueError('Invalid product identifier')
    date = datetime.fromisoformat(item['properties']['datetime'].replace('Z', '+00:00'))
    if date.tzinfo is None or date > datetime.now(timezone.utc):
        raise ValueError('Invalid acquisition date')
    rasters = {}
    bounds = manifest['aoi']['bounds']
    if manifest['aoi']['crs'] != 'EPSG:25830':
        raise ValueError('Unexpected AOI CRS')
    for name in PALETTES:
        path = folder/f'{name}.tif'
        info = manifest['indices'][name]
        if hashlib.sha256(path.read_bytes()).hexdigest() != info['sha256']:
            raise ValueError('Product checksum mismatch')
        ds = gdal.Open(str(path))
        res = 20 if name == 'NDMI' else 10
        expected = [np.floor(bounds[0]/res)*res, res, 0,
                    np.ceil(bounds[3]/res)*res, 0, -res]
        if (ds.RasterCount != 1 or ds.GetSpatialRef().GetAuthorityCode(None) != '25830'
                or not np.allclose(ds.GetGeoTransform(), expected)
                or ds.RasterXSize != int(np.ceil(bounds[2]/res)-np.floor(bounds[0]/res))
                or ds.RasterYSize != int(np.ceil(bounds[3]/res)-np.floor(bounds[1]/res))
                or ds.GetRasterBand(1).GetNoDataValue() != -9999):
            raise ValueError('Unexpected technical raster grid')
        array = ds.ReadAsArray()
        valid = np.isfinite(array) & (array != -9999)
        percent = float(valid.mean()*100)
        if percent < 80 or abs(percent-info['valid_percent_rectangle']) > .001:
            raise ValueError('Product quality mismatch')
        rasters[name] = ds
    return manifest, rasters


def build(folder, output):
    gdal.UseExceptions()
    manifest, rasters = validate_product(folder)
    item = manifest['source_item']
    acquisition = {'id': item['id'], 'datetime': item['properties']['datetime'],
                   'indices': {}, 'source': 'Copernicus Sentinel-2 L2A',
                   'quality_scope': 'rectángulo envolvente', 'kind': 'ESTIMADO'}
    destination = output/item['id']
    destination.mkdir(parents=True, exist_ok=True)
    for name, ds in rasters.items():
        warped = gdal.Warp('', ds, format='MEM', dstSRS='EPSG:3857',
                           resampleAlg='near', srcNodata=-9999, dstNodata=-9999)
        values = warped.ReadAsArray()
        rgba = colorize(values, np.isfinite(values) & (values != -9999), PALETTES[name])
        mem = gdal.GetDriverByName('MEM').Create('', warped.RasterXSize, warped.RasterYSize, 4, gdal.GDT_Byte)
        for i in range(4):
            mem.GetRasterBand(i+1).WriteArray(rgba[i])
            mem.GetRasterBand(i+1).SetColorInterpretation([gdal.GCI_RedBand, gdal.GCI_GreenBand,
                gdal.GCI_BlueBand, gdal.GCI_AlphaBand][i])
        gdal.GetDriverByName('PNG').CreateCopy(str(destination/f'{name}.png'), mem)
        shutil.copyfile(folder/f'{name}.tif', destination/f'{name}.tif')
        x, dx, _, y, _, dy = warped.GetGeoTransform()
        acquisition['indices'][name] = {
            **PALETTES[name], **manifest['indices'][name], 'projection': 'EPSG:3857',
            'extent': [x, y+dy*warped.RasterYSize, x+dx*warped.RasterXSize, y],
            'image': f"sentinel/{item['id']}/{name}.png",
            'download': f"sentinel/{item['id']}/{name}.tif"}
    # Public provenance is deliberately minimal: no full provider catalogue or credentials.
    catalog = {'version': 1, 'acquisitions': [acquisition]}
    (output/'catalog.json').write_text(json.dumps(catalog, indent=2)+'\n', encoding='utf-8')
    print(f"Prepared {item['id']}: three overlays and technical GeoTIFF downloads")
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build(args.input, args.output)
