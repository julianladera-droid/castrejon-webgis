"""Shared version boundary; deliberately usable without the geospatial runtime."""
PRODUCT_VERSION = 2
RADIOMETRY = 'asset_scale_offset_nonnegative_sum_gt_0.01_v1'
WATER_METHOD = 'optical_surface_water_v2'
INDEX_RESOLUTIONS = {'NDVI': 10, 'EVI2': 10, 'NDMI': 20, 'NDWI': 10, 'MNDWI': 20}
RAW_BANDS = {'B03_10m': 10, 'B04_10m': 10, 'B08_10m': 10,
             'B8A_20m': 20, 'B11_20m': 20, 'SCL_20m': 20}
PRODUCT_FILES = ('manifest.json', *[name + '.tif' for name in INDEX_RESOLUTIONS],
                 'SCL.tif', 'WATER.tif', 'WATER_QUALITY.tif',
                 *['raw_' + name + '.tif' for name in RAW_BANDS])


def compatible(manifest):
    return (manifest.get('version') == PRODUCT_VERSION and
            manifest.get('radiometry') == RADIOMETRY and
            manifest.get('water', {}).get('method') == WATER_METHOD)
