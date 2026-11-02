"""Field-visit approximation: preserve baseline water; guided additions stay candidates."""
import numpy as np
from parcel_grid import repeat_2x2
from spectral_quality import normalized_difference, interpretable
from water_detection import detect, PARAMETERS as BASE_PARAMETERS, QUALITY_BITS as BASE_BITS
from water_sharpening import guided_b11

PARAMETERS={**BASE_PARAMETERS,'guides':['NDWI','NDVI'],'candidate_swir_max':.08,
            'candidate_nir_max':.15,'candidate_b8a_max':.15,'preserve_baseline_water':True}
QUALITY_BITS={**BASE_BITS,'residual_candidate':64}


def add_candidates(base, flags, nir, narrow, ndwi, estimate, guided_mndwi):
    result=base.copy();quality=flags.copy()
    eligible=(base!=3)&(base!=1)&interpretable(ndwi)&interpretable(guided_mndwi)
    signal=eligible&(guided_mndwi>0)
    result[signal]=2
    residual=(signal&(ndwi<=0)&np.isfinite(estimate)&(estimate>=0)&(estimate<=.08)&
              (nir>=0)&(nir<=.15)&np.isfinite(narrow)&(narrow>=0)&(narrow<=.15))
    result[residual]=4
    quality &= np.uint8(255-32)
    quality[result==2] |= 32
    quality[residual] |= 64
    return result,quality


def assess(green,nir,swir,ndwi,mndwi20,ndvi,scl20,narrow):
    base,quality=detect(green,nir,repeat_2x2(swir),ndwi,repeat_2x2(mndwi20),ndvi,repeat_2x2(scl20))
    try:
        estimate,metadata=guided_b11(swir,ndwi,ndvi,np.isin(scl20,[4,5,6]))
    except ValueError as error:
        if 'Insufficient complete blocks' not in str(error):raise
        return base,quality,{'status':'baseline_fallback','reason':'insufficient_complete_guide_blocks'}
    mndwi=normalized_difference(green,estimate,np.isin(repeat_2x2(scl20),[4,5,6]))
    result,quality=add_candidates(base,quality,nir,repeat_2x2(narrow),ndwi,estimate,mndwi)
    return result,quality,{'status':'guided_candidates_available','fit_scope':'global_per_acquisition_without_labels',
        'model':metadata,'candidate_pixels':int((result==4).sum()),
        'added_ambiguous_pixels':int(((result==2)&(base==0)).sum())}
