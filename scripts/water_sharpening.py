"""Research-only, mean-preserving regression detail injection for B11.

Fit B11_20 = intercept + beta*mean(NDWI_10) [+ gamma*mean(NDVI_10)]
on this acquisition's valid blocks. Inject only within-block predictor residuals.
Scale the detail uniformly per block if needed to preserve nonnegative B11.
The mean remains exactly B11_20. This is not additional observed SWIR detail,
nor an implementation/validation of Yang et al.'s complete sharpening procedure.
"""
import numpy as np
from parcel_grid import mean_2x2, repeat_2x2
from spectral_quality import interpretable


def guided_b11(swir, ndwi, ndvi=None, quality=None):
    guides = [ndwi] + ([] if ndvi is None else [ndvi])
    fine = [np.where(interpretable(x), x, np.nan) for x in guides]
    coarse = [mean_2x2(x) for x in fine]
    valid = np.isfinite(swir) & (swir >= 0)
    for x in coarse:
        valid &= np.isfinite(x)
    if quality is not None:
        valid &= quality
    if valid.sum() < 100:
        raise ValueError('Insufficient complete blocks for experimental reconstruction')
    matrix = np.column_stack([np.ones(int(valid.sum())), *[x[valid] for x in coarse]])
    ridge = np.eye(matrix.shape[1])*1e-6
    ridge[0, 0] = 0
    coefficients = np.linalg.solve(matrix.T@matrix+ridge, matrix.T@swir[valid])
    prediction = coefficients[0] + sum(c*x for c, x in zip(coefficients[1:], fine))
    detail = prediction-repeat_2x2(mean_2x2(prediction))
    h, w = detail.shape
    minimum = detail.reshape(h//2, 2, w//2, 2).min(axis=(1, 3))
    alpha = np.ones(swir.shape)
    np.divide(swir, -minimum, out=alpha, where=valid & (minimum < 0))
    alpha = np.minimum(alpha, 1)
    estimate = repeat_2x2(swir) + repeat_2x2(alpha)*detail
    estimate[~repeat_2x2(valid)] = np.nan
    error = mean_2x2(estimate)[valid]-swir[valid]
    return estimate, {'method': 'within_date_ridge_mean_preserving_detail_v1',
        'guides': ['NDWI'] + ([] if ndvi is None else ['NDVI']),
        'coefficients': coefficients.tolist(), 'training_blocks': int(valid.sum()),
        'max_abs_reaggregation_error': float(np.max(np.abs(error))),
        'rmse_reaggregation': float(np.sqrt(np.mean(error**2))),
        'status': 'experimental_not_operational', 'original_B11_resolution_m': 20, 'estimated_grid_m': 10}
