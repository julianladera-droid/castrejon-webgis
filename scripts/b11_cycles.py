"""Offline B11 cycles 0–3. Research only; never called by publication workflows."""
import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path
import numpy as np
from osgeo import gdal, ogr
from parcel_grid import mean_2x2, repeat_2x2, require_nested_grid, require_same_grid
from parcel_water import regions, parcel_areas
from sentinel_pipeline import reflectance
from spectral_quality import normalized_difference, interpretable
from water_detection import detect
from water_sharpening import guided_b11


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mask(ds, geometry):
    out = gdal.GetDriverByName('MEM').Create('', ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Byte)
    out.SetGeoTransform(ds.GetGeoTransform()); out.SetProjection(ds.GetProjection())
    vector = ogr.GetDriverByName('Memory').CreateDataSource('')
    layer = vector.CreateLayer('zone', ds.GetSpatialRef(), ogr.wkbUnknown)
    f = ogr.Feature(layer.GetLayerDefn()); f.SetGeometry(ogr.CreateGeometryFromJson(json.dumps(geometry)))
    layer.CreateFeature(f); gdal.RasterizeLayer(out, [1], layer, burn_values=[1])
    return out.ReadAsArray().astype(bool)


def area(ds, geometry, condition):
    vector = regions(ds, np.where(condition, 1, 0))
    areas, total, _, _ = parcel_areas(vector.GetLayer(), geometry)
    return round(areas[1], 3)


def fit_reconstruct(swir, guides, training, quality):
    """Held-out ridge: training mask is defined on whole parent cells."""
    fine = [np.where(interpretable(x), x, np.nan) for x in guides]
    coarse = [mean_2x2(x) for x in fine]
    valid = quality & np.isfinite(swir) & (swir >= 0)
    for x in coarse: valid &= np.isfinite(x)
    train = valid & training
    if train.sum() < 100: raise ValueError('Insufficient independent training blocks')
    x = np.column_stack([np.ones(train.sum()), *[c[train] for c in coarse]])
    penalty = np.eye(x.shape[1])*1e-6; penalty[0,0] = 0
    beta = np.linalg.solve(x.T@x+penalty, x.T@swir[train])
    prediction = beta[0]+sum(b*g for b,g in zip(beta[1:],fine))
    detail = prediction-repeat_2x2(mean_2x2(prediction))
    h,w=detail.shape
    minimum=detail.reshape(h//2,2,w//2,2).min(axis=(1,3))
    alpha=np.ones(swir.shape)
    np.divide(swir,-minimum,out=alpha,where=valid & (minimum<0))
    result=repeat_2x2(swir)+repeat_2x2(np.minimum(alpha,1))*detail
    result[~repeat_2x2(valid)]=np.nan
    return result, {'coefficients':beta.tolist(),'training_blocks':int(train.sum())}


def errors(pred, truth, valid):
    ok=valid & np.isfinite(pred) & np.isfinite(truth)
    e=pred[ok]-truth[ok]
    return {'n':int(e.size),'bias':float(e.mean()) if e.size else None,
            'mae':float(np.abs(e).mean()) if e.size else None,
            'rmse':float(np.sqrt((e*e).mean())) if e.size else None}


def inventory(root, products):
    master=json.loads((root/'data/parcel-master.json').read_text(encoding='utf-8'))
    controls=json.loads((root/'docs/water-evidence/controls.json').read_text())['features']
    references=json.loads((root/'docs/b11-cycles/references.json').read_text(encoding='utf-8'))
    refs={x['zone']:x for x in references['references']}
    if not set(refs).issubset({f['refcat'] for f in master['features']}):
        raise ValueError('Reference missing from parcel master')
    features=[f for f in master['features'] if f['refcat'] in refs]+controls
    cases=[]
    for p in products:
        day=p.name.split('_')[2][:8]
        for f in features:
            ref=f['refcat']; date=f'{day[:4]}-{day[4:6]}-{day[6:]}'
            reference=refs.get(ref,{})
            observed=reference.get('observations',{}).get(date)
            cases.append({'zone':ref,'acquisition':p.name,'date':date,
                'geometry':f['geometry'],'crs':'EPSG:25830',
                'source':'user parcel observation' if reference else 'existing RGB context / exploratory control',
                'observed_class':observed or 'unlabelled_acquisition_context',
                'spatial_precision':reference.get('spatial_precision','context polygon; no independent class label'),
                'uncertainty':'No water contour; undated context does not label this acquisition',
                'reference_notes':reference.get('notes','Exploratory RGB context, not a confirmed negative control'),
                'role':reference.get('role','selection_already_explored'),
                'experiment_roles':{'full_20_to_10': 'global_unsupervised_scene_fit; no spatial holdout', 'reduced_40_to_20': 'whole zone plus 80m excluded from coefficient fit', 'detector_followup': 'development_already_inspected; independent labelled evaluation pending'}})
    pending=references['pending']
    return {'version':3,'master_sha256':digest(root/'data/parcel-master.json'),
            'references_sha256':digest(root/'docs/b11-cycles/references.json'),'cases':cases,'pending':pending,
            'trend':'User reports less water 10–31 October; no 10 October acquisition or area/volume trend inferred.'}


def run(folder, cases, output):
    manifest=json.loads((folder/'manifest.json').read_text())
    item=manifest['source_item']; day=item['properties']['datetime'][:10]
    raw={k:gdal.Open(str(folder/f'raw_{k}.tif')) for k in manifest['raw_bands']}
    for k in raw: assert digest(folder/f'raw_{k}.tif')==manifest['raw_bands'][k]['sha256']
    fine,coarse=raw['B03_10m'],raw['B11_20m']; require_nested_grid(fine,coarse)
    if fine.GetSpatialRef().GetAuthorityCode(None)!='25830': raise ValueError('Expected EPSG:25830')
    for k in ('B04_10m','B08_10m'): require_same_grid(fine,raw[k])
    for k in ('B8A_20m','SCL_20m'): require_same_grid(coarse,raw[k])
    rho={k:reflectance(ds,item['assets'][k]) for k,ds in raw.items() if not k.startswith('SCL')}
    g,n,r,s=[rho[k] for k in ('B03_10m','B08_10m','B04_10m','B11_20m')]
    scl=raw['SCL_20m'].ReadAsArray(); q=np.isin(scl,[4,5,6]); q10=repeat_2x2(q)
    ndwi=normalized_difference(g,n,q10); ndvi=normalized_difference(n,r,q10)
    original=normalized_difference(mean_2x2(g),s,q)
    for name,values in [('NDWI',ndwi),('MNDWI',original)]:
        saved=gdal.Open(str(folder/(name+'.tif'))).ReadAsArray()
        np.testing.assert_array_equal(values,saved)
    estimates={'C':repeat_2x2(s)}; metadata={}
    for name,aux in [('D',None),('E',ndvi)]:
        estimates[name],metadata[name]=guided_b11(s,ndwi,aux,q)
    indices={'A':ndwi,'B':repeat_2x2(original)}
    indices.update({k:normalized_difference(g,v,q10) for k,v in estimates.items()})
    own={k:interpretable(v) for k,v in indices.items()}
    common=np.logical_and.reduce([own[k] for k in 'BCDE'])
    allcommon=common & own['A']
    detector={k:detect(g,n,estimates.get(k,repeat_2x2(s)),v if k=='A' else ndwi,
                       repeat_2x2(original) if k=='A' else v,ndvi,repeat_2x2(scl))[0]
              for k,v in indices.items() if k!='A'}
    np.testing.assert_array_equal(detector['B'],gdal.Open(str(folder/'WATER.tif')).ReadAsArray())
    gt=coarse.GetGeoTransform(); h,w=s.shape; hh,ww=h-h%2,w-w%2
    # Box low-pass + decimation, preserving complete original-cell footprints.
    s20=s[:hh,:ww]; s40=mean_2x2(s20); q20=q[:hh,:ww]
    q40=mean_2x2(q20.astype(float))==1
    g20,n20,r20=[mean_2x2(x)[:hh,:ww] for x in (g,n,r)]
    guide20=normalized_difference(g20,n20,q20)
    aux20=normalized_difference(n20,r20,q20)
    excluded=np.zeros((hh,ww),dtype=bool)
    for case in cases:
        geom=ogr.CreateGeometryFromJson(json.dumps(case['geometry'])).Buffer(80)
        excluded |= mask(coarse,json.loads(geom.ExportToJson()))[:hh,:ww]
    train=mean_2x2(excluded.astype(float))==0
    reduced={'nearest':repeat_2x2(s40)}; fits={}
    for name,guides in [('D',[guide20]),('E',[guide20,aux20])]:
        reduced[name],fits[name]=fit_reconstruct(s40,guides,train,q40)
    validreduced=q20 & (s20>=0) & np.logical_and.reduce([np.isfinite(x) for x in reduced.values()])
    # Edge stratum fixed at |adjacent B11 contrast| > .03 reflectance, no threshold tuning.
    edge=np.zeros(s20.shape,dtype=bool)
    dx=np.abs(np.diff(s20,axis=1))>.03; dy=np.abs(np.diff(s20,axis=0))>.03
    edge[:,:-1]|=dx; edge[:,1:]|=dx; edge[:-1,:]|=dy; edge[1:,:]|=dy
    rows=[]; audit=[]; reconstruction=[]
    for case in cases:
        geometry=case['geometry']; ref=case['zone']; inside=mask(fine,geometry)
        reasons={'scl_excluded':~q10,'missing_green_nir':~(np.isfinite(g)&np.isfinite(n)),
                 'negative_green_nir':(g<0)|(n<0),'low_sum_green_nir':np.isfinite(g+n)&(g+n<=.01),
                 'mndwi20_unavailable':~own['B']}
        for key,values in [('green',g),('nir',n),('red',r),('swir',repeat_2x2(s))]:
            reasons['negative_'+key]=values<0
            reasons['missing_'+key]=~np.isfinite(values)
        record={'zone':ref,'date':day,'reasons_m2_overlapping':{k:area(fine,geometry,v) for k,v in reasons.items()},'floor_sensitivity':{}}
        record['scl_classes_m2']={str(int(c)):area(coarse,geometry,scl==c) for c in np.unique(scl)}
        for floor in (0,.005,.01,.02):
            valid=q10 & np.isfinite(g+n)&(g>=0)&(n>=0)&(g+n>floor)
            record['floor_sensitivity'][str(floor)]={'valid_m2':area(fine,geometry,valid),
                                                   'ndwi_positive_m2':area(fine,geometry,valid&(g>n))}
            g20full=mean_2x2(g)
            mv=q & np.isfinite(g20full+s)&(g20full>=0)&(s>=0)&(g20full+s>floor)
            record['floor_sensitivity'][str(floor)]['mndwi_valid_m2']=area(coarse,geometry,mv)
            record['floor_sensitivity'][str(floor)]['mndwi_positive_m2']=area(coarse,geometry,mv&(g20full>s))
        audit.append(record)
        for name,index in indices.items():
            row={'zone':ref,'date':day,'method':name,'own_valid_m2':area(fine,geometry,own[name]),
                 'common_B_E_m2':area(fine,geometry,common),'common_A_E_m2':area(fine,geometry,allcommon),
                 'positive_own_m2':area(fine,geometry,own[name]&(index>0)),
                 'positive_common_m2':area(fine,geometry,common&own[name]&(index>0)),
                 'positive_allcommon_m2':area(fine,geometry,allcommon&(index>0))}
            if name in detector:
                row['operational_water_m2']=area(fine,geometry,detector[name]==1)
                row['operational_water_common_m2']=area(fine,geometry,common&(detector[name]==1))
                row['operational_ambiguous_m2']=area(fine,geometry,detector[name]==2)
                row['operational_ambiguous_common_m2']=area(fine,geometry,common&(detector[name]==2))
                row['operational_not_evaluable_m2']=area(fine,geometry,detector[name]==3)
            total=ogr.CreateGeometryFromJson(json.dumps(geometry)).GetArea()
            row['total_m2']=round(total,3)
            row['own_valid_percent']=round(100*row['own_valid_m2']/total,3)
            rows.append(row)
        zone=mask(coarse,geometry)[:hh,:ww]
        for name,pred in reduced.items():
            for coverage,subset in [('all',zone),('edge',zone&edge),('interior',zone&~edge),
                ('SCL4',zone&(scl[:hh,:ww]==4)),('SCL5',zone&(scl[:hh,:ww]==5)),('SCL6',zone&(scl[:hh,:ww]==6))]:
                reconstruction.append({'zone':ref,'date':day,'method':name,'stratum':coverage,
                    'own_n':errors(pred,s20,q20&subset)['n'],**errors(pred,s20,validreduced&subset)})
            for dy,dx in [(0,1),(0,-1),(1,0),(-1,0)]:
                shifted=np.roll(pred,(dy,dx),(0,1)); eligible=validreduced&zone
                eligible[:1,:]=False; eligible[-1:,:]=False; eligible[:,:1]=False; eligible[:,-1:]=False
                reconstruction.append({'zone':ref,'date':day,'method':name,'stratum':f'shift_{dy}_{dx}',
                                       **errors(shifted,s20,eligible)})
        plot(folder,output,case,fine,indices,common,raw,item)
    artifacts={}
    for name,value in estimates.items():
        finite=np.isfinite(value); parent=repeat_2x2(s)
        # Overshoots outside neighbouring observed parent range: diagnostic, not proof of halos.
        padded=np.pad(s,1,constant_values=np.nan)
        neighbours=np.stack([padded[i:i+h,j:j+w] for i in range(3) for j in range(3)])
        lo=repeat_2x2(np.nanmin(neighbours,axis=0)); hi=repeat_2x2(np.nanmax(neighbours,axis=0))
        artifacts[name]={'negative_pixels':int((finite&(value< -1e-12)).sum()),
            'neighbour_range_overshoots':int((finite&((value<lo-1e-8)|(value>hi+1e-8))).sum()),
            'reaggregation':errors(mean_2x2(value),s,q),
            'mean_abs_detail':float(np.nanmean(np.abs(value-parent)))}
        dx=np.abs(np.diff(value,axis=1)); dy=np.abs(np.diff(value,axis=0))
        artifacts[name]['jump_across_parent_boundary']=float(np.nanmean(np.r_[dx[:,1::2].ravel(),dy[1::2,:].ravel()]))
        artifacts[name]['jump_within_parent']=float(np.nanmean(np.r_[dx[:,::2].ravel(),dy[::2,:].ravel()]))
    stability={'D_E_sign_disagreement_pixels':int((common&((indices['D']>0)!=(indices['E']>0))).sum()),
        'D_E_common_pixels':int(common.sum()),'D_E_B11_rmse':errors(estimates['D'],estimates['E'],common)['rmse']}
    frozen={'product':item['id'],'baseline':item['id'].split('_')[3], 'datetime':item['properties']['datetime'],
        'manifest_sha256':digest(folder/'manifest.json'),'raw_bands':manifest['raw_bands'],
        'grid10':fine.GetGeoTransform(),'grid20':coarse.GetGeoTransform(),'size10':[fine.RasterXSize,fine.RasterYSize],
        'fit_scope':{'full_20_to_10': 'global_unsupervised_scene_fit; no spatial holdout', 'reduced_40_to_20': 'whole zone plus 80m excluded from coefficient fit', 'detector_followup': 'development_already_inspected; independent labelled evaluation pending'},'reduced_fit':fits,'guidance':metadata,'diagnostics':artifacts,'stability':stability,
        'reduced_model':'2x2 area box, no calibrated instrument MTF; crop last row/column if odd; 80m holdout buffer'}
    return rows,audit,reconstruction,frozen


def plot(folder,output,case,ds,indices,common,raw,item):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    geom=ogr.CreateGeometryFromJson(json.dumps(case['geometry'])); xmin,xmax,ymin,ymax=geom.GetEnvelope()
    gt=ds.GetGeoTransform(); c0=max(0,int((xmin-gt[0])/10)-3); c1=min(ds.RasterXSize,int((xmax-gt[0])/10)+4)
    r0=max(0,int((gt[3]-ymax)/10)-3); r1=min(ds.RasterYSize,int((gt[3]-ymin)/10)+4)
    if c1<=c0 or r1<=r0: return
    sl=np.s_[r0:r1,c0:c1]; extent=[gt[0]+c0*10,gt[0]+c1*10,gt[3]-r1*10,gt[3]-r0*10]
    fig,axes=plt.subplots(2,6,figsize=(18,6),layout='constrained')
    ratio_colors=plt.get_cmap('BrBG').copy(); ratio_colors.set_bad('#aaaaaa')
    water_colors=ListedColormap(['#ffffff','#1677b8']); water_colors.set_bad('#aaaaaa')
    for ax in axes.flat: ax.set_xticks([]); ax.set_yticks([])
    rgbfile=folder.parent.parent/'rgb'/(folder.name+'.tif')
    if rgbfile.exists():
        blue=gdal.Open(str(rgbfile)); require_same_grid(ds,blue)
        meta=json.loads(rgbfile.with_suffix('.json').read_text())['raster:bands'][0]
        b=reflectance(blue,{'raster:scale':meta['scale'],'raster:offset':meta['offset'],'nodata':meta['nodata']})
        red=reflectance(raw['B04_10m'],item['assets']['B04_10m']); green=reflectance(ds,item['assets']['B03_10m'])
        rgb=np.clip(np.stack([red[sl],green[sl],b[sl]],axis=-1)/.3,0,1)**(1/1.3)
        axes[0,0].imshow(rgb,extent=extent,interpolation='nearest')
    else: axes[0,0].text(.1,.5,'RGB pendiente')
    axes[0,0].set_title('RGB 0–0,30 · gamma 1,3')
    axes[1,0].imshow(common[sl],vmin=0,vmax=1,cmap='Greys',extent=extent,interpolation='nearest')
    axes[1,0].set_title('Soporte común B–E')
    for j,(name,index) in enumerate(indices.items(),1):
        axes[0,j].imshow(np.where(interpretable(index[sl]),index[sl],np.nan),vmin=-1,vmax=1,cmap=ratio_colors,extent=extent,interpolation='nearest')
        axes[0,j].set_title(name+' · índice [-1,1]')
        axes[1,j].imshow(np.where(common[sl]&interpretable(index[sl]),(index[sl]>0).astype(float),np.nan),vmin=0,vmax=1,cmap=water_colors,extent=extent,interpolation='nearest')
        axes[1,j].set_title('>0 · soporte común B–E')
    from plot_water_reference import outline
    for ax in axes.flat: outline(ax,geom,'#dd00dd')
    fig.suptitle(case['zone']+' · '+case['date']+' · EPSG:25830 · gris: excluido; blanco: sin candidato; azul: >0; no verdad espacial')
    fig.savefig(output/(case['zone']+'-'+case['date']+'.jpg'),dpi=110); plt.close(fig)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('products',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args(); gdal.UseExceptions(); args.output.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1]
    products=sorted(p.parent for p in args.products.glob('*/manifest.json'))
    if not products: raise ValueError('No product manifests found')
    days=[json.loads((p/'manifest.json').read_text())['source_item']['properties']['datetime'][:10] for p in products]
    if len(days)!=len(set(days)): raise ValueError('Do not mix products/baselines for the same observation day')
    inv=inventory(root,products); (args.output/'inventory.json').write_text(json.dumps(inv,indent=2)+'\n')
    rows=[]; audits=[]; recon=[]; frozen=[]
    for product in products:
        a,b,c,d=run(product,[x for x in inv['cases'] if x['acquisition']==product.name],args.output)
        rows+=a; audits+=b; recon+=c; frozen.append(d)
        print('Completed',product.name,flush=True)
    for f in frozen:
        rgb=args.products.parent/'rgb'/(f['product']+'.json')
        if rgb.exists(): f['rgb_blue_provenance']=json.loads(rgb.read_text())
    for name,data in [('quality',audits),('reconstruction',recon),('frozen',frozen)]:
        (args.output/(name+'.json')).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    protocol={'python':platform.python_version(),'gdal':gdal.VersionInfo(),'numpy':np.__version__,
              'signal_floor':.01,'sensitivity_floors':[0,.005,.01,.02],
              'ridge':1e-6,'heldout_buffer_m':80,'edge_contrast':.03,
              'code_sha256':{name:digest(root/'scripts'/name) for name in
                  ['b11_cycles.py','water_sharpening.py','water_detection.py','spectral_quality.py','parcel_grid.py','sentinel_pipeline.py']}}
    (args.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    for name,records in [('comparison',rows),('reconstruction',recon)]:
        with (args.output/(name+'.csv')).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(dict.fromkeys(k for row in records for k in row)))
            writer.writeheader(); writer.writerows(records)


if __name__=='__main__': main()
