"""Migrate preserved v2 DN to field-visit v3 before publication, without network."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from osgeo import gdal
from sentinel_contract import compatible, upgradeable, PRODUCT_FILES, RAW_BANDS
from sentinel_pipeline import process_rasters
from build_sentinel_web import validate_product


def upgrade(source,destination):
    if source.resolve()==destination.resolve():raise ValueError('Migration must preserve its input')
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status')!='quality_passed':raise ValueError('Input quality not passed')
    if compatible(manifest):
        validate_product(source);destination.mkdir(parents=True,exist_ok=True)
        for name in PRODUCT_FILES:shutil.copyfile(source/name,destination/name)
        return manifest
    if not upgradeable(manifest):raise ValueError('Unsupported legacy product')
    identity=manifest['source_item']['id']
    for key in RAW_BANDS:
        path=source/f'raw_{key}.tif'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['raw_bands'][key]['sha256']:
            raise ValueError('Original DN checksum mismatch before migration')
        ds=gdal.Open(str(path))
        if ds.GetMetadataItem('SOURCE_ITEM')!=identity:raise ValueError('Raw SAFE mismatch')
        ds=None
    destination.mkdir(parents=True,exist_ok=True)
    for key in RAW_BANDS:shutil.copyfile(source/f'raw_{key}.tif',destination/f'raw_{key}.tif')
    rasters={key:gdal.Open(str(destination/f'raw_{key}.tif')) for key in RAW_BANDS}
    result=process_rasters(rasters,manifest['source_item'],manifest['aoi'],destination,manifest.get('query',{}),
        {'migration':'v2_to_field_visit_v3','original_manifest_sha256':hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),
         'previous_water_method':manifest['water']['method']})
    rasters.clear();validate_product(destination)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('inputs',nargs='+',type=Path)
    args=parser.parse_args();gdal.UseExceptions();count=0
    for source in args.inputs:
        folders=[source] if (source/'manifest.json').exists() else sorted(p.parent for p in source.glob('*/manifest.json'))
        for folder in folders:
            m=upgrade(folder,args.output/folder.name);count+=1;print('Prepared v3',m['source_item']['id'],flush=True)
    if not count:raise ValueError('No preserved products to migrate')


if __name__=='__main__':main()
