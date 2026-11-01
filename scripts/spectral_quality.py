"""Interpretability of optical ratios, not a correction of original reflectance.

Negative BOA values can be real retrieval outputs. Preserve them in raw crops;
exclude them from normalized-difference interpretation, never clip or zero-fill.
The 0.01 reflectance-sum floor is a versioned conservative hypothesis.
"""
import numpy as np

NODATA = -9999
MIN_SUM = 0.01


def normalized_difference(a, b, quality):
    valid = (quality & np.isfinite(a) & np.isfinite(b) &
             (a >= 0) & (b >= 0) & (a + b > MIN_SUM))
    out = np.full(a.shape, NODATA, dtype=np.float32)
    np.divide(a - b, a + b, out=out, where=valid)
    return out


def interpretable(array):
    return np.isfinite(array) & (array != NODATA) & (array >= -1) & (array <= 1)


def quality_counts(a, b, quality):
    finite = np.isfinite(a) & np.isfinite(b)
    return {'quality_excluded': int((~quality).sum()),
            'missing': int((~finite).sum()),
            'negative_reflectance': int((finite & ((a < 0) | (b < 0))).sum()),
            'low_sum': int((finite & (a + b <= MIN_SUM)).sum())}
