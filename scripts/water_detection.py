"""Exploratory optical rule; thresholds and limitations in docs/water-assessment.md."""
import numpy as np
from spectral_quality import interpretable, MIN_SUM

PARAMETERS = {'ndwi_min': 0.0, 'mndwi_min': 0.0, 'nir_max': 0.15,
              'dark_nir_max': 0.06, 'dark_swir_max': 0.08, 'dark_ndvi_max': 0.4,
              'normalized_sum_min': MIN_SUM}
QUALITY_BITS = {'scl_excluded': 1, 'missing_green_nir': 2, 'negative_green_nir': 4,
                'low_green_nir_sum': 8, 'mndwi_unavailable': 16, 'ambiguous': 32}


def detect(green, nir, swir_parent, ndwi, mndwi_parent, ndvi, scl):
    """0 dry/no detection, 1 estimated water, 2 ambiguous, 3 not evaluable."""
    shape = green.shape
    if any(x.shape != shape for x in (nir, swir_parent, ndwi, mndwi_parent, ndvi, scl)):
        raise ValueError('Water inputs must share a checked grid')
    quality = np.zeros(shape, dtype=np.uint8)
    quality[~np.isin(scl, [4, 5, 6])] |= 1
    finite = np.isfinite(green) & np.isfinite(nir)
    quality[~finite] |= 2
    quality[finite & ((green < 0) | (nir < 0))] |= 4
    quality[finite & (green + nir <= MIN_SUM)] |= 8
    mvalid = interpretable(mndwi_parent)
    quality[~mvalid] |= 16
    valid = np.isin(scl, [4, 5, 6]) & interpretable(ndwi) & ((quality & 15) == 0)
    water = valid & (nir <= PARAMETERS['nir_max']) & (
        (scl == 6) | ((ndwi > PARAMETERS['ndwi_min']) & mvalid &
                      (mndwi_parent > PARAMETERS['mndwi_min'])))
    dark = ((nir < PARAMETERS['dark_nir_max']) & np.isfinite(swir_parent) &
            (swir_parent >= 0) & (swir_parent < PARAMETERS['dark_swir_max']) &
            interpretable(ndvi) & (ndvi < PARAMETERS['dark_ndvi_max']))
    ambiguous = valid & ~water & ((ndwi > 0) | (mvalid & (mndwi_parent > 0)) | (scl == 6) | dark)
    result = np.full(shape, 3, dtype=np.uint8)
    result[valid] = 0
    result[water] = 1
    result[ambiguous] = 2
    quality[ambiguous] |= 32
    return result, quality
