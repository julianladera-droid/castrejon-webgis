"""Separate, offline follow-up. No change to production classification or reconstruction."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from osgeo import gdal, ogr
from b11_cycles import area, mask, digest, errors, fit_reconstruct
from parcel_grid import mean_2x2 as mean, repeat_2x2 as repeat, require_same_grid, require_nested_grid
from sentinel_pipeline import reflectance
from spectral_quality import interpretable, normalized_difference
from water_detection import detect
from water_sharpening import guided_b11

ROOT=Path(__file__).resolve().parents[1]
PRIORITY={'45137A00900001','45137A00900059','45137A00700014','45137A03300153','45137A03300155',
          '45137A01200109','45137A01200001','45137A01200080','45137A04000023'}
BUILT={'45137A01200109','45137A01200001','45137A01200080','45137A04000023'}


def save(path, value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def table(path, rows):
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader(); writer.writerows(rows)


def ahash(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def ratio(a,b,q,floor=.01):
    valid=q & np.isfinite(a+b) & (a>=0)&(b>=0)&(a+b>floor)
    out=np.full(a.shape,np.nan,dtype=np.float32)
    np.divide(a-b,a+b,out=out,where=valid)
    return out


def guides(a,b,q,policy,floor):
    """Both policies use ratio of averaged reflectances; missing remains missing."""
    qa=q.copy()
    if policy=='all_children':
        child=np.isfinite(a+b)&(a>=0)&(b>=0)&(a+b>floor)
        qa &= mean(child.astype(float))==1
    return ratio(mean(a),mean(b),qa,floor)


def load(folder, blue=None):
    manifest=json.loads((folder/'manifest.json').read_text()); item=manifest['source_item']
    identity=item['id']
    raw={k:gdal.Open(str(folder/f'raw_{k}.tif')) for k in manifest['raw_bands']}
    for k in raw:
        if digest(folder/f'raw_{k}.tif')!=manifest['raw_bands'][k]['sha256']: raise ValueError('Raw checksum mismatch')
        if raw[k].GetMetadataItem('SOURCE_ITEM')!=identity: raise ValueError('Mixed SAFE')
    fine,coarse=raw['B03_10m'],raw['B11_20m']; require_nested_grid(fine,coarse)
    for k,ds in raw.items(): require_same_grid(fine if k.endswith('10m') else coarse,ds)
    rho={k.split('_')[0]:reflectance(ds,item['assets'][k]) for k,ds in raw.items() if not k.startswith('SCL')}
    if blue:
        ds=gdal.Open(str(blue)); require_same_grid(fine,ds)
        if ds.GetMetadataItem('SOURCE_ITEM')!=identity: raise ValueError('B02 from another SAFE')
        info=json.loads(blue.with_suffix('.json').read_text())
        if digest(blue)!=info['sha256']: raise ValueError('B02 checksum mismatch')
        asset=info['raster:bands'][0]
        rho['B02']=reflectance(ds,{'raster:scale':asset['scale'],'raster:offset':asset['offset'],'nodata':asset['nodata']})
    scl=raw['SCL_20m'].ReadAsArray(); q=np.isin(scl,[4,5,6]); q10=repeat(q)
    ndwi=normalized_difference(rho['B03'],rho['B08'],q10)
    ndvi=normalized_difference(rho['B08'],rho['B04'],q10)
    mndwi=normalized_difference(mean(rho['B03']),rho['B11'],q)
    for name,value in [('NDWI',ndwi),('NDVI',ndvi),('MNDWI',mndwi)]:
        np.testing.assert_array_equal(value,gdal.Open(str(folder/(name+'.tif'))).ReadAsArray())
    return dict(id=identity,folder=folder,manifest=manifest,fine=fine,coarse=coarse,rho=rho,scl=scl,q=q,
                ndwi=ndwi,ndvi=ndvi,mndwi=mndwi,blue=None if blue is None else json.loads(blue.with_suffix('.json').read_text()))


def reconstruction(data, cache):
    s=data['rho']['B11']; out={'B':repeat(s)}; fits={}
    for name,aux in [('D',None),('E',data['ndvi'])]:
        out[name],fits[name]=guided_b11(s,data['ndwi'],aux,data['q'])
    path=cache/(data['id']+'.npz')
    if path.exists():
        with np.load(path) as saved:
            for k in out: np.testing.assert_array_equal(out[k],saved[k])
    else: np.savez_compressed(path,**out)
    return out,{'scope':'20_to_10_global_unsupervised_scene_fit_no_spatial_holdout',
                'arrays_sha256':{k:ahash(v) for k,v in out.items()},'coefficients':fits}


def detector(g,n,s,narrow,ndwi,mndwi,ndvi,scl,variant):
    """Predeclared hypotheses; class 4 is residual/mixed candidate, not confirmed water."""
    result=detect(g,n,s,ndwi,mndwi,ndvi,scl)[0]
    eligible=(result!=3)&interpretable(mndwi)&(mndwi>0)&(ndwi<=0)&np.isfinite(s+narrow)
    residual=eligible&(s>=0)&(s<=.08)&(n<=.15)&(narrow>=0)&(narrow<=.15)&(result!=1)
    if variant in ('H1_residual','H2_strict'):
        result[residual]=4
    if variant=='H2_strict':
        result[residual&(n<=.06)&(s<=.05)&(narrow<=.08)]=1
    return result


def roi(ds,geometry):
    """Exact intersection weights, computed once on a small bounding window."""
    geom=ogr.CreateGeometryFromJson(json.dumps(geometry)); xmin,xmax,ymin,ymax=geom.GetEnvelope(); gt=ds.GetGeoTransform(); res=gt[1]
    c0=max(0,int(np.floor((xmin-gt[0])/res))); c1=min(ds.RasterXSize,int(np.ceil((xmax-gt[0])/res)))
    r0=max(0,int(np.floor((gt[3]-ymax)/res))); r1=min(ds.RasterYSize,int(np.ceil((gt[3]-ymin)/res)))
    weights=np.zeros((max(0,r1-r0),max(0,c1-c0)))
    for r in range(r0,r1):
        for c in range(c0,c1):
            x=gt[0]+c*res; y=gt[3]-r*res
            cell=ogr.CreateGeometryFromWkt(f'POLYGON(({x} {y},{x+res} {y},{x+res} {y-res},{x} {y-res},{x} {y}))')
            if geom.Intersects(cell): weights[r-r0,c-c0]=geom.Intersection(cell).GetArea()
    sl=np.s_[r0:r1,c0:c1]
    return sl,weights


def measure(condition, spatial):
    sl,w=spatial
    return round(float(w[condition[sl]].sum()),3)


def quality(data,cases):
    g,n,r=[data['rho'][k] for k in ['B03','B08','B04']]; q=data['q']; s=data['rho']['B11']
    h,w=s.shape; hh,ww=h-h%2,w-w%2; truth=s[:hh,:ww]; q20=q[:hh,:ww]
    s40=mean(truth); q40=mean(q20.astype(float))==1
    excluded=np.zeros(s.shape,bool)
    for case in cases:
        geom=ogr.CreateGeometryFromJson(json.dumps(case['geometry'])).Buffer(80)
        excluded |= mask(data['coarse'],json.loads(geom.ExportToJson()))
    train=mean(excluded[:hh,:ww].astype(float))==0
    baseline={}; rows=[]; blocks=[]; fitting=[]
    zone_masks={c['zone']:mask(data['coarse'],c['geometry'])[:hh,:ww] for c in cases}
    for policy in ['aggregate','all_children']:
        for floor in [.01,0,.005,.02]:
            a=guides(g,n,q,policy,floor)[:hh,:ww]; b=guides(n,r,q,policy,floor)[:hh,:ww]
            for label,x,y,z in [('NDWI',g,n,a),('NDVI',n,r,b)]:
                agg=guides(x,y,q,'aggregate',floor)[:hh,:ww]
                neg=mean(((x<0)|(y<0)).astype(float))[:hh,:ww]>0
                missing=mean((~np.isfinite(x+y)).astype(float))[:hh,:ww]>0
                for case in cases:
                    inside=zone_masks[case['zone']]
                    blocks.append({'product':data['id'],'zone':case['zone'],'guide':label,'policy':policy,'floor':floor,
                        'sampled_20m_blocks':int(inside.sum()),'valid':int((inside&np.isfinite(z)).sum()),
                        'negative_child_aggregate_valid':int((inside&neg&np.isfinite(agg)).sum()),
                        'missing_child':int((inside&missing).sum()),
                        'eligibility_changes':int((inside&(np.isfinite(z)!=np.isfinite(agg))).sum()),
                        'value_rmse_on_shared':errors(z,agg,inside)['rmse']})
            for method,gg in [('D',[a]),('E',[a,b])]:
                pred,fit=fit_reconstruct(s40,gg,train,q40)
                fitting.append({'product':data['id'],'policy':policy,'floor':floor,'method':method,**fit})
                if policy=='aggregate' and floor==.01: baseline[method]=pred.copy()
                fixed=baseline[method]; shared=np.isfinite(fixed)&np.isfinite(pred)&q20&(truth>=0)
                for case in cases:
                    inside=zone_masks[case['zone']]
                    for mode,value,eligible in [('recomputed',pred,np.isfinite(pred)),('eligibility_only_fixed',fixed,np.isfinite(pred)&np.isfinite(fixed))]:
                        rows.append({'product':data['id'],'zone':case['zone'],'policy':policy,'floor':floor,'method':method,'mode':mode,
                            'own_n':errors(value,truth,inside&eligible&q20&(truth>=0))['n'],
                            'own_rmse':errors(value,truth,inside&eligible&q20&(truth>=0))['rmse'],
                            **errors(value,truth,inside&shared)})
    return blocks,rows,fitting


def signatures(data, rec, zones, output):
    import matplotlib.pyplot as plt
    waves={'B02':.49,'B03':.56,'B04':.665,'B08':.842,'B8A':.865,'B11':1.61}; rows=[]
    rho=data['rho']; observed={k:mean(v) if k in ['B02','B03','B04','B08'] else v for k,v in rho.items()}
    fine={k:v if k in ['B02','B03','B04','B08'] else repeat(v) for k,v in rho.items()}
    for zone in zones:
        fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
        for support,collection,ds,ax in [('observed20',{'observed':observed},data['coarse'],axes[0]),
                ('grid10', {k:{**fine,'B11':v} for k,v in rec.items()},data['fine'],axes[1])]:
            inside=mask(ds,zone['geometry']); common=inside & np.logical_and.reduce([np.isfinite(x) for band in collection.values() for x in band.values()])
            for method,band in collection.items():
                xs=[]; med=[]; low=[]; high=[]
                for k in waves:
                    if k not in band: continue
                    v=band[k]; vals=v[common]
                    stats=np.percentile(vals,[10,25,50,75,90]).tolist() if vals.size else [None]*5
                    rows.append({'product':data['id'],'zone':zone['zone'],'support':support,'method':method,'band':k,
                        'source':'reconstructed' if support=='grid10' and k=='B11' and method!='B' else 'parent20_repeated' if support=='grid10' and k in ['B8A','B11'] else 'observed_reflectance',
                        'inside_centres':int(inside.sum()),'common_finite_n':int(vals.size),'band_finite_n':int((inside&np.isfinite(v)).sum()),
                        'common_finite_percent':float(100*vals.size/inside.sum()) if inside.any() else None,
                        'band_nonnegative_n':int((inside&np.isfinite(v)&(v>=0)).sum()),
                        'common_scl_eligible_n':int((common&(data['q'] if support=='observed20' else repeat(data['q']))).sum()),
                        'negative_on_common':int((vals<0).sum()),'p10':stats[0],'p25':stats[1],'median':stats[2],'p75':stats[3],'p90':stats[4],
                        'role':'exploratory_not_labelled_truth'})
                    xs.append(waves[k]);low.append(stats[1]);med.append(stats[2]);high.append(stats[3])
                if common.any():
                    ax.plot(xs,med,'o-',label=f'{method}, n={int(common.sum())}');ax.fill_between(xs,low,high,alpha=.12)
            title='observed20' if support=='observed20' else 'grid10: B11 D/E reconstructed; B8A repeated'
            ax.set(title=title+'\nmedian / IQR · finite common',xlabel='Wavelength (µm)',ylabel='Signed reflectance',ylim=(-.1,.6));ax.grid(alpha=.2)
            if ax.lines: ax.legend(fontsize=8)
            else:
                ax.set_xlim(.45,1.7)
                ax.text(.5,.5,'n=0: no shared finite support',transform=ax.transAxes,ha='center',fontsize=10)
        fig.suptitle(zone['zone']+' · '+data['id'].split('_')[2][:8]+' '+data['id'].split('_')[3]+' · proposed / development')
        fig.savefig(output/(zone['zone']+'-'+data['id'].split('_')[2][:8]+'-'+data['id'].split('_')[3]+'-spectra.jpg'),dpi=110);plt.close(fig)
    return rows


def proposals(data,case,rec):
    from parcel_water import regions
    g,n,r=[data['rho'][k] for k in ['B03','B08','B04']]; s=rec['B']; inside=mask(data['fine'],case['geometry'])
    candidates={
        'dark_context':np.isfinite(n+s)&(n<.06)&(s<.08),
        'vegetation_context':interpretable(data['ndvi'])&(data['ndvi']>.4),
        'bright_context':np.isfinite(g+r)&((g+r)/2>.10)}
    if case['zone'] not in BUILT:
        md=[ratio(g,rec[k],repeat(data['q'])) for k in ['D','E']]
        candidates['recovered_index_candidate']=((md[0]>0)|(md[1]>0))&(repeat(data['mndwi'])<=0)
    result=[]; parcel=ogr.CreateGeometryFromJson(json.dumps(case['geometry']))
    for label,selection in candidates.items():
        vector=regions(data['fine'],np.where(selection&inside,1,0)); geoms=[]
        for f in vector.GetLayer():
            if f.GetField(0)==1:
                clipped=f.GetGeometryRef().Intersection(parcel)
                if not clipped.IsEmpty(): geoms.append(clipped.Clone())
        if not geoms: continue
        multi=ogr.Geometry(ogr.wkbMultiPolygon)
        for geom in geoms:
            if ogr.GT_Flatten(geom.GetGeometryType())==ogr.wkbPolygon: multi.AddGeometry(geom)
            else:
                for part in geom: multi.AddGeometry(part)
        result.append({'zone':case['zone']+'_'+label,'parcel':case['zone'],'geometry':json.loads(multi.ExportToJson()),
            'source':'automatic original reflectance / index selection; NOT independent truth',
            'date':data['id'].split('_')[2][:8],'product':data['id'],'precision':'10 m grid selection, boundary uncertainty >=10 m',
            'class':label,'role':'development_proposal_for_user_review','validity':'only this acquisition; physical class unconfirmed',
            'footprint_status':'not a building, panel or water footprint'})
    return result


def maps(data,case,classes,output):
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap,BoundaryNorm
    from plot_water_reference import outline
    ds=data['fine']; sl,weights=roi(ds,case['geometry']); gt=ds.GetGeoTransform()
    extent=[gt[0]+sl[1].start*10,gt[0]+sl[1].stop*10,gt[3]-sl[0].stop*10,gt[3]-sl[0].start*10]
    fig,axs=plt.subplots(2,3,figsize=(12,7),layout='constrained')
    rho=data['rho']; hasblue='B02' in rho
    rgb=np.stack([rho['B04'],rho['B03'],rho['B02']] if hasblue else [rho['B08'],rho['B04'],rho['B03']],axis=-1)[sl]
    axs[0,0].imshow(np.clip(rgb/.3,0,1)**(1/1.3),extent=extent);axs[0,0].set_title('RGB same SAFE' if hasblue else 'FALSE COLOUR NIR/red/green; B02 absent')
    invalid=(~interpretable(data['ndwi'])).astype(int)
    axs[0,1].imshow(invalid[sl],cmap=ListedColormap(['white','gray']),vmin=0,vmax=1,extent=extent);axs[0,1].set_title('NDWI excluded (gray)')
    scm=axs[0,2].imshow(repeat(data['scl'])[sl],vmin=0,vmax=11,cmap='tab20',extent=extent);axs[0,2].set_title('SCL classes 0–11')
    fig.colorbar(scm,ax=axs[0,2],ticks=[0,2,4,5,6,7,8,9,10,11],shrink=.7)
    cmap=ListedColormap(['white','#1677b8','#e8a838','#999999','#a754ca']); norm=BoundaryNorm(np.arange(-.5,5),5)
    for ax,(label,states) in zip(axs[1],classes.items()):
        ax.imshow(states[sl],cmap=cmap,norm=norm,extent=extent,interpolation='nearest');ax.set_title(label)
    for ax in axs.flat:
        outline(ax,ogr.CreateGeometryFromJson(json.dumps(case['geometry'])),'#ff00ee');ax.set_xticks([]);ax.set_yticks([])
    fig.suptitle(case['zone']+' '+data['id'].split('_')[2][:8]+' '+data['id'].split('_')[3]+' EPSG:25830\nwhite=no detection; blue=estimated water; orange=ambiguous; gray=excluded; purple=residual candidate; native own support')
    fig.savefig(output/(case['zone']+'-'+data['id'].split('_')[2][:8]+'-'+data['id'].split('_')[3]+'-map.jpg'),dpi=110);plt.close(fig)


def zone_map(data,case,proposed,out):
    import matplotlib.pyplot as plt
    from plot_water_reference import outline
    fig,ax=plt.subplots(figsize=(7,5),layout='constrained')
    ds=data['fine'];sl,_=roi(ds,case['geometry']);gt=ds.GetGeoTransform()
    extent=[gt[0]+sl[1].start*10,gt[0]+sl[1].stop*10,gt[3]-sl[0].stop*10,gt[3]-sl[0].start*10]
    rho=data['rho']; keys=['B04','B03','B02'] if 'B02' in rho else ['B08','B04','B03']
    ax.imshow(np.clip(np.stack([rho[k] for k in keys],-1)[sl]/.3,0,1)**(1/1.3),extent=extent)
    colors=['#00ffff','#55ff00','#ff8800','#ff00ff']
    from matplotlib.lines import Line2D
    handles=[]
    for z,col in zip(proposed,colors):
        outline(ax,ogr.CreateGeometryFromJson(json.dumps(z['geometry'])),col)
        handles.append(Line2D([0],[0],color=col,label=z['class']))
    if handles:ax.legend(handles=handles,fontsize=7,loc='upper left')
    ax.set_xticks([]);ax.set_yticks([])
    ax.set_title(case['zone']+' '+data['id'].split('_')[2][:8]+' '+data['id'].split('_')[3]+'\nProposals, NOT validated footprints · 10m · EPSG:25830\n'+('RGB same SAFE' if 'B02' in rho else 'False colour NIR/red/green (B02 unavailable)'))
    fig.savefig(out/(case['zone']+'-'+data['id'].split('_')[2][:8]+'-'+data['id'].split('_')[3]+'-zones.jpg'),dpi=110);plt.close(fig)


def detector_map(data,case,states,common,out):
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap,BoundaryNorm
    from plot_water_reference import outline
    sl,_=roi(data['fine'],case['geometry']);gt=data['fine'].GetGeoTransform()
    extent=[gt[0]+sl[1].start*10,gt[0]+sl[1].stop*10,gt[3]-sl[0].stop*10,gt[3]-sl[0].start*10]
    fig,axes=plt.subplots(3,3,figsize=(10,10),layout='constrained')
    cmap=ListedColormap(['white','#1677b8','#e8a838','#999999','#a754ca']);norm=BoundaryNorm(np.arange(-.5,5),5)
    for axs,(k,variants) in zip(axes,states.items()):
        for ax,(v,arr) in zip(axs,variants.items()):
            ax.imshow(np.where(common[sl],arr[sl],3),extent=extent,cmap=cmap,norm=norm,interpolation='nearest')
            outline(ax,ogr.CreateGeometryFromJson(json.dumps(case['geometry'])),'#ff00ee');ax.set_title(k+' '+v);ax.set_xticks([]);ax.set_yticks([])
    fig.suptitle(case['zone']+' '+data['id'].split('_')[2][:8]+' '+data['id'].split('_')[3]+' · common B/D/E support · EPSG:25830\nwhite=no detection; blue=estimated water; orange=ambiguous; gray=excluded; purple=residual candidate')
    fig.savefig(out/(case['zone']+'-'+data['id'].split('_')[2][:8]+'-'+data['id'].split('_')[3]+'-detectors.jpg'),dpi=110);plt.close(fig)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    import matplotlib
    matplotlib.use('Agg');gdal.UseExceptions();out=args.output;out.mkdir(parents=True,exist_ok=True)
    cache=ROOT/'artifacts/b11-followup/frozen';cache.mkdir(parents=True,exist_ok=True)
    inv=json.loads((ROOT/'docs/b11-cycles/inventory.json').read_text()); unique={c['zone']:c for c in inv['cases']}
    cases=list(unique.values()); inputs=list(sorted((ROOT/'artifacts/water-review/products').glob('*/manifest.json')))+[ROOT/'artifacts/b11-followup/n0510/manifest.json']
    allquality=[];allmetrics=[];allfits=[];detections=[];allzones=[];spectra=[];provenance=[];aug=[]
    for path in inputs:
        folder=path.parent; identity=json.loads(path.read_text())['source_item']['id']
        blue=ROOT/'artifacts/water-review/rgb'/(identity+'.tif')
        d=load(folder,blue if blue.exists() else None);rec,frozen=reconstruction(d,cache)
        if '_N0510_' in identity:
            catalog=json.loads((ROOT/'artifacts/b11-followup/published-catalog.json').read_text())
            published=next(x for x in catalog['acquisitions'] if x['id']==identity)
            for k in ['NDWI','MNDWI']:
                if digest(folder/(k+'.tif'))!=published['indices'][k]['sha256']:raise ValueError('Not the published raster')
        frozen.update(product=identity,manifest_sha256=digest(path),raw_bands=d['manifest']['raw_bands'],blue=d['blue'],
                      grid10=d['fine'].GetGeoTransform(),size10=[d['fine'].RasterXSize,d['fine'].RasterYSize],
                      source_item=d['manifest']['source_item'])
        provenance.append(frozen)
        b,m,f=quality(d,cases);allquality+=b;allmetrics+=m;allfits+=f
        previous=json.loads((ROOT/'docs/b11-cycles/frozen.json').read_text())
        prior=next((x for x in previous if x['product']==identity),None)
        if prior:
            for k in ['D','E']:
                base=next(x for x in f if x['policy']=='aggregate' and x['floor']==.01 and x['method']==k)
                np.testing.assert_array_equal(base['coefficients'],prior['reduced_fit'][k]['coefficients'])
        g,n,r,s8=[d['rho'][k] for k in ['B03','B08','B04','B8A']]
        mnd={'B':repeat(d['mndwi']),**{k:normalized_difference(g,rec[k],repeat(d['q'])) for k in ['D','E']}}
        own={k:interpretable(d['ndwi'])&interpretable(mnd[k])&np.isfinite(rec[k]) for k in rec}; common=np.logical_and.reduce(list(own.values()))
        states={k:{v:detector(g,n,rec[k],repeat(s8),d['ndwi'],mnd[k],d['ndvi'],repeat(d['scl']),v)
                   for v in ['current','H1_residual','H2_strict']} for k in rec}
        np.testing.assert_array_equal(states['B']['current'],gdal.Open(str(folder/'WATER.tif')).ReadAsArray())
        for case in cases:
            spatial=roi(d['fine'],case['geometry'])
            for k in rec:
                baseline=states[k]['current']
                for variant,classified in states[k].items():
                    row={'product':identity,'zone':case['zone'],'reconstruction':k,'detector':variant,
                         'own_m2':measure(own[k],spatial),'common_m2':measure(common,spatial),
                         'parcel_m2':round(float(spatial[1].sum()),3),
                         'discarded_own_m2':measure(~own[k],spatial),'discarded_common_m2':measure(~common,spatial),
                         'native_not_evaluable_m2':measure(classified==3,spatial)}
                    for support,eligible in [('own',own[k]),('common',common)]:
                        for label,cls in [('water',1),('ambiguous',2),('residual',4)]:row[label+'_'+support+'_m2']=measure(eligible&(classified==cls),spatial)
                        row['gains_'+support+'_m2']=measure(eligible&np.isin(classified,[1,4])&(baseline!=1),spatial)
                        row['losses_'+support+'_m2']=measure(eligible&~np.isin(classified,[1,4])&(baseline==1),spatial)
                    detections.append(row)
            if case['zone'] in PRIORITY:
                proposed=proposals(d,case,rec);allzones+=proposed
                spectra+=signatures(d,rec,[case,*proposed],out)
                maps(d,case,{k+' H1':states[k]['H1_residual'] for k in rec},out)
                zone_map(d,case,proposed,out)
                if '20261031T' in identity or case['zone']=='45137A00900059':detector_map(d,case,states,common,out)
                if case['zone'] in ['45137A00900001','45137A00700014']:
                    for k in rec:
                        candidate=own[k]&(mnd[k]>0)&(d['ndwi']<=0)
                        detections.append({'product':identity,'zone':case['zone'],'reconstruction':k,'detector':'gate_diagnostic',
                            'mndwi_candidate_m2':measure(candidate,spatial),'nir_gt_015_m2':measure(candidate&(n>.15),spatial),
                            'swir_gt_008_m2':measure(candidate&(rec[k]>.08),spatial),'b8a_gt_015_m2':measure(candidate&(repeat(s8)>.15),spatial)})
        if '20230816T' in identity: aug.append(d)
        if frozen['arrays_sha256']!={k:ahash(v) for k,v in rec.items()}:raise ValueError('Detector modified reconstruction')
        print('Completed',identity,flush=True)
    baseline_audit(aug,cases,out)
    table(out/'quality-blocks.csv',allquality);table(out/'quality-metrics.csv',allmetrics);save(out/'quality-fits.json',allfits)
    table(out/'detectors.csv',detections);table(out/'signatures.csv',spectra);save(out/'frozen.json',provenance)
    save(out/'proposed-zones.json',{'crs':'EPSG:25830','zones':allzones,'independent_evaluation':'none; all inspected references are development',
         'pending':['independent dated water/building/solar footprints','wet soil without sheet, shadow and unaffected crop labels','additional sharpening successes','other invalid river/lagoon coordinates','B02 N0510 absent from artifact; never substitute N0509']})
    save(out/'proposed-zones.geojson',{'type':'FeatureCollection','crs':{'type':'name','properties':{'name':'urn:ogc:def:crs:EPSG::25830'}},
         'features':[{'type':'Feature','geometry':z['geometry'],'properties':{k:v for k,v in z.items() if k!='geometry'}} for z in allzones]})


def baseline_audit(products,cases,out):
    old,new=sorted(products,key=lambda x:x['id'].split('_')[3]);require_same_grid(old['fine'],new['fine'])
    rows=[];deltas=[]
    for case in cases:
        spatial=roi(old['fine'],case['geometry']); inside=mask(old['fine'],case['geometry'])
        for d in [old,new]:
            g,n=d['rho']['B03'],d['rho']['B08'];scl=repeat(d['scl'])
            reasons={'missing':~np.isfinite(g+n),'negative':(g<0)|(n<0),'low_sum':np.isfinite(g+n)&(g+n<=.01),
                     'scl_excluded':~np.isin(scl,[4,5,6]),'ndwi_excluded':~interpretable(d['ndwi']),
                     'mndwi_excluded':~repeat(interpretable(d['mndwi']))}
            row={'product':d['id'],'zone':case['zone'],**{k+'_m2':measure(v,spatial) for k,v in reasons.items()}}
            dark=(old['rho']['B08']<.06)&(repeat(old['rho']['B11'])<.08)&np.isfinite(old['rho']['B08']+repeat(old['rho']['B11']))
            row['fixed_N0509_dark_proposal_m2']=measure(dark,spatial)
            row['ndwi_excluded_in_dark_proposal_m2']=measure(dark&reasons['ndwi_excluded'],spatial)
            for c in range(12):row['scl_'+str(c)+'_m2']=measure(scl==c,spatial)
            rows.append(row)
        for k in ['B03','B04','B08','B8A','B11']:
            a,b=old['rho'][k],new['rho'][k];coarse=k in ['B8A','B11'];z=mask(old['coarse'],case['geometry']) if coarse else inside
            deltas.append({'zone':case['zone'],'band':k,'comparison':'N0510 minus N0509; identical method',**errors(b,a,z)})
        row={'zone':case['zone'],'band':'validity_transitions','scl_changed_m2':measure(repeat(old['scl']!=new['scl']),spatial)}
        for k in ['ndwi','mndwi']:
            a,b=interpretable(old[k]),interpretable(new[k])
            if k=='mndwi':a,b=repeat(a),repeat(b)
            row[k+'_gained_m2']=measure(~a&b,spatial);row[k+'_lost_m2']=measure(a&~b,spatial)
        deltas.append(row)
        if case['zone'] in ['45137A00900059','45137A00900001','45137A00900013','45137A01000045','45137A00800001']:
            import matplotlib.pyplot as plt
            from matplotlib.colors import ListedColormap
            from plot_water_reference import outline
            sl,_=spatial;gt=old['fine'].GetGeoTransform()
            extent=[gt[0]+sl[1].start*10,gt[0]+sl[1].stop*10,gt[3]-sl[0].stop*10,gt[3]-sl[0].start*10]
            fig,axes=plt.subplots(2,5,figsize=(15,6),layout='constrained')
            for axs,d in zip(axes,[old,new]):
                g,n=d['rho']['B03'],d['rho']['B08']
                reasons={'NDWI excluded':~interpretable(d['ndwi']),'MNDWI excluded':~repeat(interpretable(d['mndwi'])),
                    'negative green/NIR':(g<0)|(n<0),'sum <= .01':np.isfinite(g+n)&(g+n<=.01),'SCL excluded':~repeat(d['q'])}
                for ax,(label,values) in zip(axs,reasons.items()):
                    ax.imshow(values[sl],vmin=0,vmax=1,cmap=ListedColormap(['white','#d43e3e']),extent=extent,interpolation='nearest')
                    outline(ax,ogr.CreateGeometryFromJson(json.dumps(case['geometry'])),'#222222')
                    ax.set_title(d['id'].split('_')[3]+' '+label);ax.set_xticks([]);ax.set_yticks([])
            fig.suptitle(case['zone']+' · 16/08/2023 · red=exclusion reason; white=not excluded for this reason\nEPSG:25830 · same 10m grid; MNDWI/SCL parent20 repeated · parcel boundary is NOT water contour')
            fig.savefig(out/(case['zone']+'-baseline-exclusions.jpg'),dpi=110);plt.close(fig)
    table(out/'baseline-quality.csv',rows);table(out/'baseline-deltas.csv',deltas)


if __name__=='__main__':main()
