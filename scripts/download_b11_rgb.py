"""Fetch original B02 only, on the preserved study grid, for dated RGB figures."""
import argparse
import hashlib
import json
from pathlib import Path
from osgeo import gdal
from sentinel_pipeline import write_raster
from parcel_grid import require_same_grid


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('raw',type=Path); parser.add_argument('products',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    gdal.UseExceptions(); gdal.SetConfigOption('GDAL_DISABLE_READDIR_ON_OPEN','EMPTY_DIR')
    gdal.SetConfigOption('GDAL_HTTP_TIMEOUT','90')
    for mirror in sorted(args.raw.glob('*/mirror.json')):
        identity=mirror.parent.name; source=json.loads(mirror.read_text())
        assert source['mirror_identity']['productName'].removesuffix('.SAFE')==identity
        asset=source['source']['assets']['blue-jp2'].copy()
        assert asset['href'].startswith('s3://sentinel-s2-l2a/tiles/') and '..' not in asset['href']
        base=asset['href'].rsplit('/',1)[0]
        if base.endswith(('/R10m','/R20m','/R60m')): base=base.rsplit('/',1)[0]
        href=base.replace('s3://sentinel-s2-l2a/','https://sentinel-s2-l2a.s3.eu-central-1.amazonaws.com/')+'/R10m/B02.jp2'
        ref=gdal.Open(str(args.products/identity/'raw_B03_10m.tif')); gt=ref.GetGeoTransform()
        bounds=[gt[0],gt[3]-ref.RasterYSize*10,gt[0]+ref.RasterXSize*10,gt[3]]
        file=args.output/(identity+'.tif')
        if not file.exists():
            ds=gdal.Warp('', '/vsicurl/'+href,format='MEM',dstSRS='EPSG:25830',outputBounds=bounds,
                xRes=10,yRes=10,srcNodata=0,dstNodata=-9999,outputType=gdal.GDT_Float32,resampleAlg='near')
            write_raster(file,ds.ReadAsArray(),ds,'raw_B02',identity)
        existing=gdal.Open(str(file)); require_same_grid(ref,existing)
        assert existing.GetMetadataItem('SOURCE_ITEM')==identity
        asset.update(downloaded_href=href,sha256=hashlib.sha256(file.read_bytes()).hexdigest())
        file.with_suffix('.json').write_text(json.dumps(asset,indent=2)+'\n')
        print(identity,flush=True)


if __name__=='__main__': main()
