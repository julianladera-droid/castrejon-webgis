"""One-off download proposal: ten original JP2 files, no processing or publication."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

from osgeo import gdal

SCENES = (
    'S2A_MSIL2A_20260924T110721_N0513_R137_T30TUK_20260924T174754',
    'S2A_MSIL2A_20261014T110941_N0513_R137_T30TUK_20261014T173008',
)
BANDS = ('B04_10m', 'B08_10m', 'B8A_20m', 'B11_20m', 'SCL_20m')


def validate_sources(document):
    if [s['id'] for s in document['scenes']] != list(SCENES):
        raise ValueError('Unexpected acquisition pair')
    for scene in document['scenes']:
        if set(scene['assets']) != set(BANDS):
            raise ValueError('Expected exactly five original bands per acquisition')
        stamp = scene['id'].split('_')[2]
        prefix = ('s3://eodata/Sentinel-2/MSI/L2A/'
                  f'{stamp[:4]}/{stamp[4:6]}/{stamp[6:8]}/{scene["id"]}.SAFE/')
        for band, asset in scene['assets'].items():
            pattern = (re.escape(prefix) + r'GRANULE/L2A_T30TUK_A\d{6}_\d{8}T\d{6}/'
                       + f'IMG_DATA/R{band[-3:]}/T30TUK_{stamp}_{band}\\.jp2')
            if not re.fullmatch(pattern, asset['href']):
                raise ValueError('Unexpected original band location')
            if type(asset['file:size']) is not int or asset['file:size'] <= 0:
                raise ValueError('Missing original byte count')
            # STAC multihash: 0x16 is SHA3-256; 0x20 is its 32-byte digest length.
            if not re.fullmatch(r'1620[0-9a-f]{64}', asset['file:checksum']):
                raise ValueError('Expected provider SHA3-256 multihash')
    return document['scenes']


def copy_verified(source, destination, expected_size, checksum):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination.name)
    provider_hash, local_hash = hashlib.sha3_256(), hashlib.sha256()
    total = 0
    partial = destination.with_suffix(destination.suffix + '.part')
    # Exclusive creation preserves prior files, including incomplete downloads.
    with partial.open('xb') as output:
        stream = gdal.VSIFOpenL(source, 'rb')
        if stream is None:
            raise OSError('Cannot open original band')
        try:
            while True:
                block = gdal.VSIFReadL(1, 8 * 1024 * 1024, stream)
                if not block:
                    break
                total += len(block)
                if total > expected_size:
                    raise ValueError('Original band exceeds provider byte count')
                output.write(block)
                provider_hash.update(block)
                local_hash.update(block)
        finally:
            gdal.VSIFCloseL(stream)
    if total != expected_size or '1620' + provider_hash.hexdigest() != checksum:
        raise ValueError('Original band size/checksum mismatch')
    partial.rename(destination)
    return {'bytes': total, 'sha256': local_hash.hexdigest(), 'provider_checksum': checksum}


def main():
    root = Path(__file__).resolve().parents[1]
    source_file = root / 'data/m4-originals-sources.json'
    sources = json.loads(source_file.read_text(encoding='utf-8'))
    scenes = validate_sources(sources)
    output = root / 'm4-original-bands'
    if output.exists():
        raise FileExistsError('Output must be new')
    for env, config in [('CDSE_S3_ACCESS_KEY', 'AWS_ACCESS_KEY_ID'),
                        ('CDSE_S3_SECRET_KEY', 'AWS_SECRET_ACCESS_KEY')]:
        value = os.environ.get(env)
        if not value:
            raise ValueError('CDSE environment credential missing')
        gdal.SetConfigOption(config, value)
    for key, value in {'AWS_S3_ENDPOINT': 'eodata.dataspace.copernicus.eu',
                       'AWS_REGION': 'default', 'AWS_VIRTUAL_HOSTING': 'FALSE',
                       'AWS_HTTPS': 'YES', 'GDAL_HTTP_MAX_RETRY': '3',
                       'GDAL_HTTP_RETRY_DELAY': '30', 'GDAL_HTTP_TIMEOUT': '120',
                       'CPL_CURL_VERBOSE': 'NO', 'CPL_DEBUG': 'OFF'}.items():
        gdal.SetConfigOption(key, value)
    output.mkdir()
    records = []
    for scene in scenes:
        folder = output / scene['id']
        folder.mkdir()
        for band in BANDS:
            asset = scene['assets'][band]
            result = copy_verified('/vsis3/' + asset['href'].removeprefix('s3://'),
                                   folder / (band + '.jp2'),
                                   asset['file:size'], asset['file:checksum'])
            records.append({'scene': scene['id'], 'band': band, 'href': asset['href'],
                            'path': f'{scene["id"]}/{band}.jp2', **result})
            print('Verified original:', scene['id'], band, result['bytes'], flush=True)
    (output / 'sources.json').write_bytes(source_file.read_bytes())
    (output / 'download.json').write_text(json.dumps({
        'status': 'original_bytes_verified', 'processing_performed': False,
        'downloaded_at': datetime.now(timezone.utc).isoformat(),
        'github_run_id': os.environ.get('GITHUB_RUN_ID'),
        'github_sha': os.environ.get('GITHUB_SHA'),
        'sources_sha256': hashlib.sha256(source_file.read_bytes()).hexdigest(),
        'files': records}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    gdal.UseExceptions()
    gdal.PushErrorHandler('CPLQuietErrorHandler')
    try:
        main()
    except Exception as error:
        # Never include provider response bodies or credentials in logs.
        print(f'Original band download failed ({type(error).__name__}).', file=sys.stderr)
        sys.exit(1)
